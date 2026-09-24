from __future__ import annotations

import json
from datetime import date

import pytest

from scripts.reconcile_taifex_pcr_audit import main, reconcile_pcr_audit
from src.data.taifex_pcr import PCR_DATASET_ID
from src.data.taifex_pcr_probe import audit_pcr_range


def _audit() -> dict:
    payload = (
        "日期,賣權成交量,買權成交量,買賣權成交量比率%,賣權未平倉量,買權未平倉量,買賣權未平倉量比率%\r\n"
        "2026/09/16,1,2,50,3,4,75\r\n"
        "2026/09/15,1,2,50,3,4,75\r\n"
    ).encode("ms950")
    return audit_pcr_range(date(2026, 9, 15), date(2026, 9, 17), lambda _: payload)


def _calendar(dates: list[str]) -> dict:
    return {
        "source": "TAIFEX official calendar fixture",
        "start_date": "2026-09-15",
        "end_date": "2026-09-17",
        "dates": dates,
    }


def test_missing_calendar_keeps_coverage_unknown():
    report = reconcile_pcr_audit(_audit())
    dataset = report["datasets"][PCR_DATASET_ID]

    assert report["gate_status"] == "unknown"
    assert dataset["missing_dates"] is None
    assert dataset["unexpected_dates"] is None


def test_official_calendar_reports_missing_and_unexpected_dates():
    missing = reconcile_pcr_audit(
        _audit(), _calendar(["2026-09-15", "2026-09-16", "2026-09-17"])
    )
    unexpected = reconcile_pcr_audit(_audit(), _calendar(["2026-09-15"]))

    assert missing["gate_status"] == "fail"
    assert missing["datasets"][PCR_DATASET_ID]["missing_dates"] == ["2026-09-17"]
    assert unexpected["gate_status"] == "fail"
    assert unexpected["datasets"][PCR_DATASET_ID]["unexpected_dates"] == ["2026-09-16"]
    assert unexpected["datasets"][PCR_DATASET_ID]["coverage"]["ratio"] == 1.0


def test_complete_matching_calendar_passes():
    report = reconcile_pcr_audit(_audit(), _calendar(["2026-09-15", "2026-09-16"]))

    assert report["gate_status"] == "pass"
    assert report["datasets"][PCR_DATASET_ID]["missing_dates"] == []


def test_incomplete_or_old_audit_cannot_claim_calendar_coverage():
    old_report = _audit()
    del old_report["observed_dates"]
    with pytest.raises(TypeError, match="no observed_dates"):
        reconcile_pcr_audit(old_report, _calendar(["2026-09-15"]))

    failed_report = _audit()
    failed_report["error_window_count"] = 1
    with pytest.raises(ValueError, match="incomplete or failed"):
        reconcile_pcr_audit(failed_report, _calendar(["2026-09-15"]))


def test_calendar_must_explicitly_cover_the_audit_range():
    partial = _calendar(["2026-09-15", "2026-09-16"])
    partial["end_date"] = "2026-09-16"

    with pytest.raises(ValueError, match="boundaries must match"):
        reconcile_pcr_audit(_audit(), partial)


def test_offline_cli_writes_reconciliation_report(tmp_path):
    audit_path = tmp_path / "audit.json"
    calendar_path = tmp_path / "calendar.json"
    output_path = tmp_path / "reconciliation.json"
    audit_path.write_text(json.dumps(_audit()), encoding="utf-8")
    calendar_path.write_text(
        json.dumps(_calendar(["2026-09-15", "2026-09-16"])), encoding="utf-8"
    )

    assert (
        main(
            [
                "--audit",
                str(audit_path),
                "--calendar",
                str(calendar_path),
                "--output",
                str(output_path),
            ]
        )
        == 0
    )
    assert json.loads(output_path.read_text(encoding="utf-8"))["gate_status"] == "pass"
