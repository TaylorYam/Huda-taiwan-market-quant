"""Fetch and validate Taiwan Stock Exchange trading-calendar exceptions."""

from __future__ import annotations

import time
from datetime import date
from typing import Any

import requests

TWSE_HOLIDAY_CALENDAR_URL = (
    "https://www.twse.com.tw/rwd/zh/holidaySchedule/holidaySchedule"
)

_CLOSED_MARKERS = ("市場無交易", "休市", "放假", "補假", "無交易")
_OPEN_MARKERS = ("開始交易", "最後交易", "恢復交易", "補行交易")
_CALENDAR_REQUEST_ATTEMPTS = 3
_CALENDAR_RETRY_DELAYS_SECONDS = (1, 3)


def _request_error_category(exc: requests.RequestException) -> str:
    if isinstance(exc, requests.Timeout):
        return "timeout"
    if isinstance(exc, requests.ConnectionError):
        return "connection_error"
    if isinstance(exc, requests.HTTPError):
        status = exc.response.status_code if exc.response is not None else None
        return f"http_{status}" if status is not None else "http_error"
    return "request_error"


def _is_retryable_request_error(exc: requests.RequestException) -> bool:
    if isinstance(exc, requests.HTTPError):
        status = exc.response.status_code if exc.response is not None else None
        return status in {408, 429} or (status is not None and status >= 500)
    return True


def _parse_calendar_date(value: object) -> date:
    if not isinstance(value, str):
        raise TypeError("TWSE calendar date must be text")
    normalized = value.strip()
    if len(normalized) == 10 and normalized[4] == "-":
        try:
            return date.fromisoformat(normalized)
        except ValueError as exc:
            raise ValueError("TWSE calendar contains an invalid date") from exc
    if normalized.isdigit() and len(normalized) == 8:
        try:
            return date(int(normalized[:4]), int(normalized[4:6]), int(normalized[6:]))
        except ValueError as exc:
            raise ValueError("TWSE calendar contains an invalid date") from exc
    if normalized.isdigit() and len(normalized) == 7:
        try:
            return date(
                int(normalized[:3]) + 1911,
                int(normalized[3:5]),
                int(normalized[5:]),
            )
        except ValueError as exc:
            raise ValueError("TWSE calendar contains an invalid date") from exc
    raise ValueError("TWSE calendar date format is unsupported")


def _calendar_rows(payload: object) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        if not payload or not all(isinstance(row, dict) for row in payload):
            raise ValueError("TWSE calendar rows have an invalid shape")
        return payload
    if not isinstance(payload, dict) or payload.get("stat") != "ok":
        raise ValueError("TWSE calendar response is not successful")

    fields = payload.get("fields")
    data = payload.get("data")
    if not isinstance(fields, list) or not all(isinstance(k, str) for k in fields):
        raise ValueError("TWSE calendar fields are missing")
    if not isinstance(data, list) or not data:
        raise ValueError("TWSE calendar has no rows")
    rows: list[dict[str, Any]] = []
    for values in data:
        if not isinstance(values, list) or len(values) != len(fields):
            raise ValueError("TWSE calendar row has an invalid shape")
        rows.append(dict(zip(fields, values, strict=True)))
    return rows


def parse_twse_closed_dates(payload: object, *, year: int) -> frozenset[date]:
    """Return weekday closures from a TWSE holiday response for one year.

    The TWSE calendar also lists special open days such as the first or final
    trading day. Unknown weekday rows fail closed so new official labels cannot
    silently produce a wrong target date.
    """

    rows = _calendar_rows(payload)
    closed: set[date] = set()
    for row in rows:
        day = _parse_calendar_date(row.get("Date") or row.get("日期"))
        if day.year != year:
            raise ValueError(f"TWSE calendar returned a date outside {year}")
        if day.weekday() >= 5:
            continue

        label = " ".join(
            str(row.get(key, "")) for key in ("Name", "Description", "名稱", "說明")
        )
        is_closed = any(marker in label for marker in _CLOSED_MARKERS)
        is_open = any(marker in label for marker in _OPEN_MARKERS)
        if is_closed == is_open:
            raise ValueError("TWSE calendar contains an unknown weekday label")
        if is_closed:
            closed.add(day)
    return frozenset(closed)


def fetch_twse_closed_dates(
    years: set[int], *, session: Any | None = None
) -> frozenset[date]:
    """Read the official TWSE calendar for each requested Gregorian year."""

    http = session or requests.Session()
    owns_session = session is None
    closed: set[date] = set()
    try:
        for year in sorted(years):
            for attempt in range(1, _CALENDAR_REQUEST_ATTEMPTS + 1):
                try:
                    response = http.get(
                        TWSE_HOLIDAY_CALENDAR_URL,
                        params={"response": "json", "queryYear": year - 1911},
                        headers={
                            "Accept": "application/json",
                            "User-Agent": "HudaTaiwanQuant/0.1",
                        },
                        timeout=15,
                    )
                    response.raise_for_status()
                except requests.RequestException as exc:
                    retry = _is_retryable_request_error(exc)
                    if retry and attempt < _CALENDAR_REQUEST_ATTEMPTS:
                        time.sleep(_CALENDAR_RETRY_DELAYS_SECONDS[attempt - 1])
                        continue
                    category = _request_error_category(exc)
                    raise RuntimeError(
                        "TWSE holiday calendar request failed for "
                        f"{year} after {attempt} attempt(s) ({category})"
                    ) from exc

                try:
                    payload = response.json()
                except ValueError as exc:
                    if attempt < _CALENDAR_REQUEST_ATTEMPTS:
                        time.sleep(_CALENDAR_RETRY_DELAYS_SECONDS[attempt - 1])
                        continue
                    raise RuntimeError(
                        "TWSE holiday calendar returned invalid JSON for "
                        f"{year} after {attempt} attempts (invalid_json)"
                    ) from exc
                break
            closed.update(parse_twse_closed_dates(payload, year=year))
    finally:
        if owns_session:
            http.close()
    return frozenset(closed)


__all__ = [
    "TWSE_HOLIDAY_CALENDAR_URL",
    "fetch_twse_closed_dates",
    "parse_twse_closed_dates",
]
