from __future__ import annotations

from datetime import date

import pytest

from src.data import (
    PCRParseError,
    PCRWindow,
    audit_pcr_range,
    iter_pcr_windows,
    parse_pcr_csv,
)


def sample_payload() -> bytes:
    return (
        "日期,賣權成交量,買權成交量,買賣權成交量比率%,賣權未平倉量,買權未平倉量,買賣權未平倉量比率%\r\n"
        "2026/09/16,375087,352656,106.36,31098,37215,83.56,\r\n"
        "2026/09/15,172547,162102,106.44,81556,94956,85.89,\r\n"
    ).encode("ms950")


def test_window_planner_is_non_overlapping_and_respects_limit():
    windows = list(iter_pcr_windows(date(2001, 12, 24), date(2002, 2, 1)))

    assert windows == [
        PCRWindow(date(2001, 12, 24), date(2002, 1, 23)),
        PCRWindow(date(2002, 1, 24), date(2002, 2, 1)),
    ]
    assert all((window.end - window.start).days <= 30 for window in windows)


def test_parser_decodes_ms950_and_preserves_daily_values():
    header, records = parse_pcr_csv(
        sample_payload(), PCRWindow(date(2026, 9, 15), date(2026, 9, 16))
    )

    assert header[0] == "日期"
    assert [record.observation_date.isoformat() for record in records] == [
        "2026-09-16",
        "2026-09-15",
    ]
    assert records[0].put_oi == 31098
    assert records[0].oi_ratio == 83.56


def test_parser_rejects_duplicate_dates():
    payload = sample_payload().replace(b"2026/09/15", b"2026/09/16")
    with pytest.raises(PCRParseError, match="repeats"):
        parse_pcr_csv(payload, PCRWindow(date(2026, 9, 15), date(2026, 9, 16)))


def test_audit_report_records_errors_without_filling_missing_dates():
    def fetch(window: PCRWindow) -> bytes:
        del window
        return b"not a CSV response"

    report = audit_pcr_range(date(2026, 9, 15), date(2026, 9, 17), fetch)

    assert report["planned_window_count"] == 1
    assert report["total_rows"] == 0
    assert report["error_window_count"] == 1
    assert report["duplicate_dates"] == []
