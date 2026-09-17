from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.data import (
    TAIEXParseError,
    build_taiex_month_url,
    collect_taiex_month,
    collect_taiex_range,
    parse_taiex_payload,
)
from src.data.storage import SQLiteObservationStore

FIXTURE = Path(__file__).parent / "fixtures" / "taiex_month.json"


def fixture_bytes() -> bytes:
    return FIXTURE.read_bytes()


def test_parser_normalizes_roc_dates_and_preserves_source_date():
    observations = parse_taiex_payload(
        fixture_bytes(),
        source_url="https://example.test/taiex",
        retrieved_at="2026-09-16T00:00:00+00:00",
        ingested_at="2026-09-16T00:01:00+00:00",
    )

    assert [item.observation_date for item in observations] == [
        "2024-01-02",
        "2024-01-03",
    ]
    assert observations[0].source_date == "113/01/02"
    assert observations[0].values == {
        "open": 17853.76,
        "high": 17853.76,
        "low": 17549.40,
        "close": 17853.76,
        "unit": "index_points",
    }
    assert len(observations[0].source_payload_hash) == 64


def test_collector_writes_observations_and_is_idempotent(tmp_path):
    with SQLiteObservationStore(tmp_path / "market.sqlite3") as store:
        first = collect_taiex_month(store, 2024, 1, http_get=lambda _: fixture_bytes())
        second = collect_taiex_month(store, 2024, 1, http_get=lambda _: fixture_bytes())

        assert [result.action for result in first] == ["inserted", "inserted"]
        assert [result.action for result in second] == ["duplicate", "duplicate"]


def test_parser_rejects_non_ok_or_missing_fields():
    document = json.loads(fixture_bytes())
    document["stat"] = "很抱歉，查無資料"
    with pytest.raises(TAIEXParseError, match="status"):
        parse_taiex_payload(
            json.dumps(document, ensure_ascii=False).encode(),
            source_url="https://example.test/taiex",
        )

    document = json.loads(fixture_bytes())
    document["data"] = []
    with pytest.raises(TAIEXParseError, match="no daily rows"):
        parse_taiex_payload(
            json.dumps(document, ensure_ascii=False).encode(),
            source_url="https://example.test/taiex",
        )

    with pytest.raises(TAIEXParseError, match="hash"):
        parse_taiex_payload(
            fixture_bytes(),
            source_url="https://example.test/taiex",
            source_payload_hash="0" * 64,
        )

    document = json.loads(fixture_bytes())
    document["fields"] = ["日期", "開盤指數"]
    with pytest.raises(TAIEXParseError, match="field 'high'"):
        parse_taiex_payload(
            json.dumps(document, ensure_ascii=False).encode(),
            source_url="https://example.test/taiex",
        )


def test_parser_rejects_wrong_month_duplicate_date_and_non_finite_values():
    document = json.loads(fixture_bytes())
    document["data"][1][0] = "113/02/01"
    with pytest.raises(TAIEXParseError, match="outside response month"):
        parse_taiex_payload(
            json.dumps(document, ensure_ascii=False).encode(),
            source_url="https://example.test/taiex",
        )

    document = json.loads(fixture_bytes())
    document["fields"] = [
        "開盤指數",
        "日期",
        "最高指數",
        "最低指數",
        "收盤指數",
    ]
    document["data"] = [
        ["17,853.76", "113/01/02", "17,853.76", "17,549.40", "17,853.76"],
        ["17,735.91", "113/01/03", "17,735.91", "17,609.72", "17,535.49"],
    ]
    observations = parse_taiex_payload(
        json.dumps(document, ensure_ascii=False).encode(),
        source_url="https://example.test/taiex",
    )
    assert observations[0].publication_label == "month:2024-01"

    document = json.loads(fixture_bytes())
    document["data"][1][0] = document["data"][0][0]
    with pytest.raises(TAIEXParseError, match="repeats date"):
        parse_taiex_payload(
            json.dumps(document, ensure_ascii=False).encode(),
            source_url="https://example.test/taiex",
        )

    document = json.loads(fixture_bytes())
    document["data"][0][1] = "NaN"
    with pytest.raises(TAIEXParseError, match="not finite"):
        parse_taiex_payload(
            json.dumps(document, ensure_ascii=False).encode(),
            source_url="https://example.test/taiex",
        )


def test_range_backfill_is_inclusive_and_chronological(tmp_path):
    calls = []

    def get(url):
        calls.append(url)
        document = json.loads(fixture_bytes())
        if "20240201" in url:
            document["date"] = "20240201"
            document["data"] = [
                ["113/02/01", "17,900", "18,000", "17,800", "17,950"],
                ["113/02/02", "17,950", "18,100", "17,900", "18,050"],
            ]
        return json.dumps(document, ensure_ascii=False).encode()

    with SQLiteObservationStore(tmp_path / "market.sqlite3") as store:
        results = collect_taiex_range(
            store,
            2024,
            1,
            2024,
            2,
            http_get=get,
        )

    assert len(results) == 4
    assert calls[0].endswith("date=20240101&response=json")
    assert calls[1].endswith("date=20240201&response=json")


def test_url_builder_rejects_invalid_month_and_uses_official_endpoint():
    assert build_taiex_month_url(2024, 1).startswith(
        "https://www.twse.com.tw/indicesReport/MI_5MINS_HIST?"
    )
    with pytest.raises(ValueError):
        build_taiex_month_url(1998, 12)


def test_fetch_rejects_response_for_a_different_requested_month():
    document = json.loads(fixture_bytes())
    document["date"] = "20240201"
    document["data"][0][0] = "113/02/01"
    document["data"][1][0] = "113/02/02"
    with pytest.raises(TAIEXParseError, match="requested month"):
        from src.data.twse_taiex import fetch_taiex_month

        fetch_taiex_month(
            2024,
            1,
            http_get=lambda _: json.dumps(document, ensure_ascii=False).encode(),
        )
