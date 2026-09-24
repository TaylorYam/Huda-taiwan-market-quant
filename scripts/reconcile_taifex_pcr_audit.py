"""Compare a complete PCR window audit with an explicitly sourced calendar.

This is an offline, read-only step. A missing calendar leaves coverage unknown;
weekday assumptions and partial audit reports must never produce a pass.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Mapping, Sequence
from datetime import date
from pathlib import Path
from typing import Any

from src.data.taifex_pcr import PCR_DATASET_ID
from src.data.taifex_quality import build_taifex_quality_report


def _canonical_date(value: object, field: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field} must use YYYY-MM-DD")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{field} must use YYYY-MM-DD") from exc
    if parsed.isoformat() != value:
        raise ValueError(f"{field} must use YYYY-MM-DD")
    return value


def _count(audit: Mapping[str, Any], field: str) -> int:
    value = audit.get(field)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"PCR audit {field} must be a non-negative integer")
    return value


def _audit_dates(audit: Mapping[str, Any]) -> tuple[str, str, list[str]]:
    start = _canonical_date(audit.get("requested_start"), "requested_start")
    end = _canonical_date(audit.get("requested_end"), "requested_end")
    if start > end:
        raise ValueError("PCR audit requested_start is after requested_end")
    planned = _count(audit, "planned_window_count")
    completed = _count(audit, "completed_window_count")
    failed = _count(audit, "error_window_count")
    if planned == 0 or completed != planned or failed != 0 or audit.get("errors"):
        raise ValueError("PCR audit has incomplete or failed windows")
    raw_dates = audit.get("observed_dates")
    if not isinstance(raw_dates, list):
        raise TypeError(
            "PCR audit has no observed_dates; rerun with the new audit format"
        )
    observed = [_canonical_date(value, "observed_dates entry") for value in raw_dates]
    if observed != sorted(set(observed)):
        raise ValueError("PCR audit observed_dates must be sorted and unique")
    if any(value < start or value > end for value in observed):
        raise ValueError("PCR audit observed_dates fall outside the requested range")
    if len(observed) != _count(audit, "unique_dates"):
        raise ValueError("PCR audit observed_dates do not match unique_dates")
    total_rows = _count(audit, "total_rows")
    if total_rows < len(observed):
        raise ValueError("PCR audit total_rows is smaller than observed_dates")
    duplicates = audit.get("duplicate_dates")
    if not isinstance(duplicates, list):
        raise TypeError("PCR audit duplicate_dates must be a list")
    duplicate_dates = [
        _canonical_date(value, "duplicate_dates entry") for value in duplicates
    ]
    if duplicate_dates != sorted(set(duplicate_dates)):
        raise ValueError("PCR audit duplicate_dates must be sorted and unique")
    if not duplicates and total_rows != len(observed):
        raise ValueError("PCR audit row counts do not match observed_dates")
    if observed and (
        audit.get("min_data_date") != observed[0]
        or audit.get("max_data_date") != observed[-1]
    ):
        raise ValueError("PCR audit data boundaries do not match observed_dates")
    return start, end, observed


def _calendar_dates(
    calendar: Mapping[str, Any], start: str, end: str
) -> tuple[list[str], str]:
    source = calendar.get("source")
    if not isinstance(source, str) or not source.strip():
        raise ValueError("calendar source must identify the official evidence")
    calendar_start = _canonical_date(calendar.get("start_date"), "calendar start_date")
    calendar_end = _canonical_date(calendar.get("end_date"), "calendar end_date")
    if (calendar_start, calendar_end) != (start, end):
        raise ValueError("calendar boundaries must match the PCR audit boundaries")
    raw_dates = calendar.get("dates")
    if not isinstance(raw_dates, list):
        raise TypeError("calendar dates must be a list")
    dates = [_canonical_date(value, "calendar date") for value in raw_dates]
    if len(set(dates)) != len(dates):
        raise ValueError("calendar dates contain duplicates")
    if any(value < start or value > end for value in dates):
        raise ValueError("calendar dates fall outside the requested range")
    return dates, source.strip()


def reconcile_pcr_audit(
    audit: Mapping[str, Any], calendar: Mapping[str, Any] | None = None
) -> dict[str, Any]:
    """Build a quality report from complete PCR date evidence only."""

    start, end, observed = _audit_dates(audit)
    expected_dates, calendar_source = (
        _calendar_dates(calendar, start, end) if calendar is not None else (None, None)
    )
    report = build_taifex_quality_report(
        {
            PCR_DATASET_ID: {
                "records": observed,
                "duplicate_dates": audit["duplicate_dates"],
            }
        },
        requested_start=start,
        requested_end=end,
        expected_dates=expected_dates,
        calendar_status="available" if calendar is not None else "unknown",
        calendar_source=calendar_source,
    )
    report["pcr_audit"] = {
        "audit_started_at": audit.get("audit_started_at"),
        "requested_start": start,
        "requested_end": end,
        "planned_window_count": audit["planned_window_count"],
        "observed_date_count": len(observed),
    }
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Reconcile a complete TAIFEX PCR audit with an official calendar."
    )
    parser.add_argument("--audit", required=True, type=Path)
    parser.add_argument(
        "--calendar",
        type=Path,
        help="JSON with source, start_date, end_date, and official trading dates.",
    )
    parser.add_argument(
        "--output", type=Path, default=Path("pcr-calendar-reconciliation.json")
    )
    return parser


def _read_mapping(path: Path) -> Mapping[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise TypeError(f"{path} must contain a JSON object")
    return payload


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        report = reconcile_pcr_audit(
            _read_mapping(args.audit),
            _read_mapping(args.calendar) if args.calendar is not None else None,
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        dataset = report["datasets"][PCR_DATASET_ID]
        print(
            f"PCR reconciliation: status={report['gate_status']} "
            f"observed={dataset['available_date_count']} "
            f"missing={len(dataset['missing_dates']) if dataset['missing_dates'] is not None else 'unknown'} "
            f"unexpected={len(dataset['unexpected_dates']) if dataset['unexpected_dates'] is not None else 'unknown'}"
        )
        return 0 if report["gate_status"] == "pass" else 1
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        print(f"PCR reconciliation failed: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
