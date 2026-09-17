from __future__ import annotations

import pytest

from src.data import (
    SQLiteObservationStore,
    VIXParseError,
    build_vix_month_url,
    collect_vix_month,
    parse_vix_payload,
)


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
