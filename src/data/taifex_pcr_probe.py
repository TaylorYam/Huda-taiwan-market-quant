"""Read-only TAIFEX PCR window planning and audit helpers.

This module is intentionally a Phase 0 probe. It validates the official CSV
windows and produces coverage evidence; it does not write observations or
derive a factor score.
"""

from __future__ import annotations

import csv
import io
import math
from collections import Counter
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any

PCR_ENDPOINT = "https://www.taifex.com.tw/cht/3/pcRatioDown"
PCR_FIRST_VERIFIED_DATE = date(2001, 12, 24)


class PCRParseError(ValueError):
    """The official PCR response did not match the expected CSV shape."""


@dataclass(frozen=True)
class PCRWindow:
    """An inclusive date window accepted by the TAIFEX form."""

    start: date
    end: date

    def __post_init__(self) -> None:
        if self.start > self.end:
            raise ValueError("PCR window start must not be after end")
        if (self.end - self.start).days > 30:
            raise ValueError("PCR window must span at most 30 date differences")

    @property
    def label(self) -> str:
        return f"{self.start.isoformat()}..{self.end.isoformat()}"

    def form_values(self) -> dict[str, str]:
        return {
            "queryStartDate": self.start.strftime("%Y/%m/%d"),
            "queryEndDate": self.end.strftime("%Y/%m/%d"),
        }


@dataclass(frozen=True)
class PCRRecord:
    """One daily row returned by the TAIFEX PCR CSV."""

    observation_date: date
    put_volume: float
    call_volume: float
    volume_ratio: float
    put_oi: float
    call_oi: float
    oi_ratio: float
    # Keep the official date spelling for the observation envelope.  The
    # normalized ``observation_date`` remains the value used for filtering.
    source_date: str = ""


def iter_pcr_windows(start: date, end: date) -> Iterator[PCRWindow]:
    """Yield non-overlapping inclusive windows respecting the 30-day limit."""

    if start > end:
        raise ValueError("PCR audit start must not be after end")
    current = start
    while current <= end:
        window_end = min(current + timedelta(days=30), end)
        yield PCRWindow(current, window_end)
        current = window_end + timedelta(days=1)


def parse_pcr_csv(
    payload: bytes, window: PCRWindow
) -> tuple[tuple[str, ...], list[PCRRecord]]:
    """Decode and validate one official PCR CSV response."""

    text = _decode_payload(payload)
    rows = [
        _trim_trailing_empty(row)
        for row in csv.reader(io.StringIO(text))
        if any(cell.strip() for cell in row)
    ]
    if not rows:
        raise PCRParseError(f"{window.label}: response has no CSV rows")
    header = tuple(cell.strip() for cell in rows[0])
    if len(header) < 7:
        raise PCRParseError(
            f"{window.label}: expected at least 7 columns, got {len(header)}"
        )

    records: list[PCRRecord] = []
    seen_dates: set[date] = set()
    for row_number, row in enumerate(rows[1:], start=2):
        if len(row) < 7:
            raise PCRParseError(
                f"{window.label}: row {row_number} has {len(row)} columns"
            )
        values = row[:7]
        observation_date = _parse_date(values[0], window, row_number)
        if observation_date in seen_dates:
            raise PCRParseError(
                f"{window.label}: row {row_number} repeats {observation_date.isoformat()}"
            )
        seen_dates.add(observation_date)
        records.append(
            PCRRecord(
                observation_date=observation_date,
                source_date=values[0].strip(),
                put_volume=_parse_number(values[1], window, row_number),
                call_volume=_parse_number(values[2], window, row_number),
                volume_ratio=_parse_number(values[3], window, row_number),
                put_oi=_parse_number(values[4], window, row_number),
                call_oi=_parse_number(values[5], window, row_number),
                oi_ratio=_parse_number(values[6], window, row_number),
            )
        )
    return header, records


def audit_pcr_range(
    start: date,
    end: date,
    fetch: Callable[[PCRWindow], bytes],
) -> dict[str, Any]:
    """Audit every planned window and return JSON-serializable evidence."""

    started_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    windows: list[dict[str, Any]] = []
    all_dates: list[date] = []
    errors: list[dict[str, str]] = []
    planned = list(iter_pcr_windows(start, end))
    for window in planned:
        try:
            header, records = parse_pcr_csv(fetch(window), window)
            dates = [record.observation_date for record in records]
            all_dates.extend(dates)
            windows.append(
                {
                    "start": window.start.isoformat(),
                    "end": window.end.isoformat(),
                    "row_count": len(records),
                    "header": list(header),
                    "min_data_date": min(dates).isoformat() if dates else None,
                    "max_data_date": max(dates).isoformat() if dates else None,
                }
            )
        except Exception as exc:  # noqa: BLE001 - retain per-window probe errors
            errors.append({"window": window.label, "error": str(exc)})
            windows.append(
                {
                    "start": window.start.isoformat(),
                    "end": window.end.isoformat(),
                    "error": str(exc),
                }
            )

    duplicate_dates = sorted(
        observation_date.isoformat()
        for observation_date, count in Counter(all_dates).items()
        if count > 1
    )
    observed_dates = sorted(
        observation_date.isoformat() for observation_date in set(all_dates)
    )
    return {
        "audit_started_at": started_at,
        "requested_start": start.isoformat(),
        "requested_end": end.isoformat(),
        "planned_window_count": len(planned),
        "completed_window_count": len(planned) - len(errors),
        "error_window_count": len(errors),
        "total_rows": len(all_dates),
        "unique_dates": len(observed_dates),
        "observed_dates": observed_dates,
        "duplicate_dates": duplicate_dates,
        "min_data_date": min(all_dates).isoformat() if all_dates else None,
        "max_data_date": max(all_dates).isoformat() if all_dates else None,
        "errors": errors,
        "windows": windows,
    }


def _decode_payload(payload: bytes) -> str:
    for encoding in ("ms950", "utf-8-sig"):
        try:
            return payload.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise PCRParseError("response is neither MS950 nor UTF-8 CSV")


def _trim_trailing_empty(row: Sequence[str]) -> list[str]:
    values = list(row)
    while values and not values[-1].strip():
        values.pop()
    return values


def _parse_date(value: str, window: PCRWindow, row_number: int) -> date:
    try:
        parsed = date.fromisoformat(value.strip().replace("/", "-"))
    except ValueError as exc:
        raise PCRParseError(
            f"{window.label}: row {row_number} has invalid date {value!r}"
        ) from exc
    if parsed < window.start or parsed > window.end:
        raise PCRParseError(
            f"{window.label}: row {row_number} date {parsed.isoformat()} is outside window"
        )
    return parsed


def _parse_number(value: str, window: PCRWindow, row_number: int) -> float:
    try:
        parsed = float(value.strip().replace(",", ""))
    except ValueError as exc:
        raise PCRParseError(
            f"{window.label}: row {row_number} has invalid number {value!r}"
        ) from exc
    if not math.isfinite(parsed):
        raise PCRParseError(f"{window.label}: row {row_number} has non-finite number")
    return parsed


__all__ = [
    "PCR_ENDPOINT",
    "PCR_FIRST_VERIFIED_DATE",
    "PCRParseError",
    "PCRRecord",
    "PCRWindow",
    "audit_pcr_range",
    "iter_pcr_windows",
    "parse_pcr_csv",
]
