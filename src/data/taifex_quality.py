"""Daily TAIFEX coverage and reconciliation quality gate.

The quality gate is deliberately read-only.  It summarizes dates and quality
statuses that a probe or collector actually returned.  It never infers a
trading calendar from weekdays, date spans, or neighbouring observations.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping
from datetime import date, datetime, timezone
from typing import Any

REPORT_VERSION = "0.1"
CALENDAR_STATUSES = frozenset({"available", "unknown", "unavailable"})
FAILURE_STATUSES = frozenset(
    {
        "fetch_failed",
        "parse_failed",
        "invalid",
        "not_published",
    }
)


def _date(value: date | str) -> date:
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"date must use YYYY-MM-DD: {value!r}") from exc


def _date_texts(values: Iterable[date | str] | None) -> list[str]:
    if values is None:
        return []
    return sorted({_date(value).isoformat() for value in values})


def _record_value(record: Any, *names: str, default: Any = None) -> Any:
    if isinstance(record, Mapping):
        for name in names:
            if name in record:
                return record[name]
        return default
    for name in names:
        if hasattr(record, name):
            return getattr(record, name)
    if isinstance(record, (date, str)) and names[0] in {
        "observation_date",
        "date",
    }:
        return record
    return default


def _records(records: Iterable[Any]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for record in records:
        value = _record_value(record, "observation_date", "date", "source_date")
        if value is None:
            raise ValueError("each daily record must include observation_date")
        normalized.append(
            {
                "date": _date(value),
                "status": str(
                    _record_value(
                        record, "quality_status", "status", default="available"
                    )
                ),
                "key": str(
                    _record_value(
                        record,
                        "source_record_key",
                        "record_key",
                        "key",
                        default="daily",
                    )
                ),
            }
        )
    return normalized


def _calendar_boundary(
    *,
    start: date | str | None,
    end: date | str | None,
    expected_dates: Iterable[date | str] | None,
    status: str,
    source: str | None,
) -> dict[str, Any]:
    if status not in CALENDAR_STATUSES:
        raise ValueError(
            f"calendar_status must be one of: {', '.join(sorted(CALENDAR_STATUSES))}"
        )
    if (start is None) != (end is None):
        raise ValueError("calendar start and end must be provided together")
    start_date = _date(start) if start is not None else None
    end_date = _date(end) if end is not None else None
    if start_date is not None and end_date is not None and start_date > end_date:
        raise ValueError("calendar start must not be after end")
    expected = _date_texts(expected_dates) if expected_dates is not None else None
    if expected is not None and status == "unknown":
        raise ValueError(
            "calendar_status cannot be unknown when expected_dates are supplied"
        )
    if expected is None and status == "available":
        raise ValueError("available calendar requires expected_dates")
    return {
        "status": status,
        "source": source,
        "requested_start": start_date.isoformat() if start_date else None,
        "requested_end": end_date.isoformat() if end_date else None,
        "expected_date_count": len(expected) if expected is not None else None,
        "expected_dates": expected,
    }


def build_dataset_report(
    dataset_id: str,
    records: Iterable[Any],
    *,
    empty_dates: Iterable[date | str] | None = None,
    duplicate_dates: Iterable[date | str] | None = None,
    calendar: Mapping[str, Any],
) -> dict[str, Any]:
    """Build a daily report for one TAIFEX dataset.

    ``records`` must contain dates that were actually returned by a parser or
    collector.  ``expected_dates`` is used only when an official calendar is
    explicitly supplied with ``calendar_status='available'``.
    """

    if not dataset_id.strip():
        raise ValueError("dataset_id must not be empty")
    normalized = _records(records)
    all_dates = [item["date"] for item in normalized]
    available_dates = [
        item["date"] for item in normalized if item["status"] == "available"
    ]
    statuses = Counter(item["status"] for item in normalized)
    by_identity = Counter((item["date"], item["key"]) for item in normalized)
    derived_duplicates = {
        item[0].isoformat() for item, count in by_identity.items() if count > 1
    }
    explicit_duplicates = set(_date_texts(duplicate_dates))
    duplicates = sorted(derived_duplicates | explicit_duplicates)
    explicit_empty = set(_date_texts(empty_dates))
    observed_empty = {
        item["date"].isoformat()
        for item in normalized
        if item["status"] == "source_empty"
    }
    empty = sorted(explicit_empty | observed_empty)

    expected = calendar["expected_dates"]
    expected_set = set(expected) if expected is not None else None
    available_set = {item.isoformat() for item in available_dates}
    missing = (
        sorted(expected_set - available_set)
        if expected_set is not None and calendar["status"] == "available"
        else None
    )
    unexpected = (
        sorted(available_set - expected_set)
        if expected_set is not None and calendar["status"] == "available"
        else None
    )
    gate_reasons: list[str] = []
    if duplicates:
        gate_reasons.append("duplicate daily identity")
    if any(status in FAILURE_STATUSES for status in statuses):
        gate_reasons.append("unavailable or failed source status")
    if missing:
        gate_reasons.append("missing official calendar dates")
    if calendar["status"] != "available":
        gate_reasons.append("official trading calendar boundary is unknown")
    if (
        gate_reasons
        and calendar["status"] != "available"
        and not duplicates
        and not any(status in FAILURE_STATUSES for status in statuses)
    ):
        gate_status = "unknown"
    elif gate_reasons:
        gate_status = "fail"
    else:
        gate_status = "pass"

    expected_count = len(expected_set) if expected_set is not None else None
    coverage_ratio = (
        len(available_set) / expected_count
        if expected_count is not None and expected_count > 0
        else None
    )
    return {
        "dataset_id": dataset_id,
        "earliest_date": min(all_dates).isoformat() if all_dates else None,
        "latest_date": max(all_dates).isoformat() if all_dates else None,
        "available_earliest_date": min(available_dates).isoformat()
        if available_dates
        else None,
        "available_latest_date": max(available_dates).isoformat()
        if available_dates
        else None,
        "row_count": len(normalized),
        "available_row_count": statuses.get("available", 0),
        "observed_date_count": len(set(all_dates)),
        "available_date_count": len(available_set),
        "coverage": {
            "available_date_count": len(available_set),
            "expected_date_count": expected_count,
            "ratio": coverage_ratio,
        },
        "quality_status_counts": dict(sorted(statuses.items())),
        "empty_dates": empty,
        "duplicate_dates": duplicates,
        "missing_dates": missing,
        "unexpected_dates": unexpected,
        "calendar_boundary": {
            "status": calendar["status"],
            "source": calendar["source"],
            "requested_start": calendar["requested_start"],
            "requested_end": calendar["requested_end"],
            "expected_date_count": calendar["expected_date_count"],
        },
        "gate_status": gate_status,
        "gate_reasons": gate_reasons,
    }


def build_taifex_quality_report(
    datasets: Mapping[str, Iterable[Any] | Mapping[str, Any]],
    *,
    requested_start: date | str | None = None,
    requested_end: date | str | None = None,
    expected_dates: Iterable[date | str] | None = None,
    calendar_status: str = "unknown",
    calendar_source: str | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Build a JSON-serializable daily coverage/reconciliation report."""

    calendar = _calendar_boundary(
        start=requested_start,
        end=requested_end,
        expected_dates=expected_dates,
        status=calendar_status,
        source=calendar_source,
    )
    reports: dict[str, dict[str, Any]] = {}
    for dataset_id, value in datasets.items():
        if isinstance(value, Mapping) and "records" in value:
            records = value["records"]
            empty_dates = value.get("empty_dates")
            duplicate_dates = value.get("duplicate_dates")
        else:
            records = value
            empty_dates = None
            duplicate_dates = None
        reports[dataset_id] = build_dataset_report(
            dataset_id,
            records,
            empty_dates=empty_dates,
            duplicate_dates=duplicate_dates,
            calendar=calendar,
        )
    statuses = [report["gate_status"] for report in reports.values()]
    if any(status == "fail" for status in statuses):
        gate_status = "fail"
    elif any(status == "unknown" for status in statuses):
        gate_status = "unknown"
    else:
        gate_status = "pass"
    return {
        "report_version": REPORT_VERSION,
        "generated_at": generated_at
        or datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "calendar_boundary": calendar,
        "gate_status": gate_status,
        "datasets": reports,
    }


__all__ = [
    "CALENDAR_STATUSES",
    "FAILURE_STATUSES",
    "REPORT_VERSION",
    "build_dataset_report",
    "build_taifex_quality_report",
]
