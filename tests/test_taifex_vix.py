from __future__ import annotations

import json
from datetime import date

import pytest

from src.data import (
    SQLiteObservationStore,
    VIXParseError,
    build_vix_month_url,
    collect_vix_month,
    collect_vix_range,
    parse_vix_payload,
    parse_vix_range_payload,
)


def range_payload(*points: tuple[str, float]) -> bytes:
    trend = [{"Time": time, "Price": price} for time, price in points]
    inner = json.dumps(
        {
            "TrendData": trend,
            "CurrentPrice": 24.06,
            "ChangeToday": -0.39,
            "OpenPrice": 0.0,
            "Datadate": "2026/09/17",
            "startDate": "20231001",
            "endDate": "20231031",
        }
    )
    return json.dumps({"d": inner}).encode("utf-8")


def sample_payload() -> bytes:
    return (
        "DATE\tTIME\tCLOSE\tAVG\r\n"
        "--------\t--------\t--------\t--------\r\n"
        "20260915\t13450000\t\t\t27.29\t\t27.29\r\n"
        "20260914\t13450000\t\t\t26.10\t\t26.20\r\n"
    ).encode("cp950")


def test_build_vix_month_url_uses_verified_month_file_pattern():
    assert build_vix_month_url(2026, 9).endswith("202609new.txt")


def test_parser_creates_daily_observations_with_effective_time():
    records = parse_vix_payload(
        sample_payload(),
        source_url=build_vix_month_url(2026, 9),
        expected_month="2026-09",
    )

    assert [record.observation_date for record in records] == [
        "2026-09-15",
        "2026-09-14",
    ]
    assert records[0].values == {
        "close": 27.29,
        "close_1m_avg": 27.29,
        "source_time": "13450000",
        "unit": "index_points",
    }
    assert records[0].effective_at == "2026-09-15T13:45:00.000+08:00"
    assert records[0].source_date == "20260915"


def test_parser_rejects_duplicate_dates_and_out_of_month_rows():
    duplicate = sample_payload().replace(b"20260914", b"20260915")
    with pytest.raises(VIXParseError, match="repeats"):
        parse_vix_payload(
            duplicate,
            source_url="https://example.invalid/vix.txt",
            expected_month="2026-09",
        )

    with pytest.raises(VIXParseError, match="outside requested month"):
        parse_vix_payload(
            sample_payload(),
            source_url="https://example.invalid/vix.txt",
            expected_month="2026-08",
        )


def test_parser_rejects_unavailable_values_and_invalid_month():
    with pytest.raises(VIXParseError, match="unavailable"):
        parse_vix_payload(
            b"20260915\t13450000\t\t\t-\t\t27.29\n",
            source_url="https://example.invalid/vix.txt",
        )
    with pytest.raises(ValueError, match="between 2007-01"):
        build_vix_month_url(2006, 12)


def test_collector_writes_month_through_observation_store():
    with SQLiteObservationStore(":memory:") as store:
        results = collect_vix_month(
            store,
            2026,
            9,
            http_get=lambda url: sample_payload(),
        )

        assert [result.action for result in results] == ["inserted", "inserted"]
        observation = store.get_observation(results[0].observation_id)
        assert observation is not None
        assert observation.dataset_id == "taifex_taiwan_vix_close_v1"


def test_parse_vix_range_payload_creates_daily_observations_without_avg():
    payload = range_payload(("20231002", 13.99), ("20231003", 14.97))

    records = parse_vix_range_payload(payload)

    assert [record.observation_date for record in records] == [
        "2023-10-02",
        "2023-10-03",
    ]
    assert records[0].values == {"close": 13.99, "unit": "index_points"}
    assert records[0].source_date == "20231002"
    assert records[0].publication_label == "day:2023-10-02"
    assert records[0].quality_status == "available"


def test_parse_vix_range_payload_empty_series_returns_no_rows():
    assert parse_vix_range_payload(range_payload()) == []


def test_parse_vix_range_payload_rejects_duplicate_dates():
    payload = range_payload(("20231002", 13.99), ("20231002", 14.5))

    with pytest.raises(VIXParseError, match="repeats"):
        parse_vix_range_payload(payload)


def test_collect_vix_range_is_idempotent_and_links_revision():
    with SQLiteObservationStore(":memory:") as store:
        first = collect_vix_range(
            store,
            date(2023, 10, 2),
            date(2023, 10, 2),
            http_post=lambda url, body: range_payload(("20231002", 13.99)),
        )
        duplicate = collect_vix_range(
            store,
            date(2023, 10, 2),
            date(2023, 10, 2),
            http_post=lambda url, body: range_payload(("20231002", 13.99)),
        )
        revised = collect_vix_range(
            store,
            date(2023, 10, 2),
            date(2023, 10, 2),
            http_post=lambda url, body: range_payload(("20231002", 14.50)),
        )

    assert first[0].action == "inserted"
    assert duplicate[0].action == "duplicate"
    assert revised[0].action == "inserted"
