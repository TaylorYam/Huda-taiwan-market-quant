from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.data import (
    TAIEXParseError,
    build_taiex_month_url,
    collect_taiex_month,
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
    document["fields"] = ["日期", "開盤指數"]
    with pytest.raises(TAIEXParseError, match="field 'high'"):
        parse_taiex_payload(
            json.dumps(document, ensure_ascii=False).encode(),
            source_url="https://example.test/taiex",
        )


def test_url_builder_rejects_invalid_month_and_uses_official_endpoint():
    assert build_taiex_month_url(2024, 1).startswith(
        "https://www.twse.com.tw/indicesReport/MI_5MINS_HIST?"
    )
    with pytest.raises(ValueError):
        build_taiex_month_url(1998, 12)
