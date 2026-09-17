"""Operational helpers for the verified TAIEX daily ingestion path."""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from .storage import WriteResult

TAIWAN_TIMEZONE = ZoneInfo("Asia/Taipei")


def current_taiwan_month(now: datetime | None = None) -> tuple[int, int]:
    """Return the calendar month used by the daily workflow.

    The default clock is UTC and is converted explicitly to Asia/Taipei so a
    runner crossing midnight cannot accidentally fetch the wrong month.
    """

    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None or current.utcoffset() is None:
        raise ValueError("now must be timezone-aware")
    local = current.astimezone(TAIWAN_TIMEZONE)
    return local.year, local.month


def summarize_write_results(results: list[WriteResult]) -> dict[str, int]:
    """Count inserted and duplicate observations for a workflow summary."""

    counts = Counter(result.action for result in results)
    return {action: counts[action] for action in sorted(counts)}


__all__ = ["TAIWAN_TIMEZONE", "current_taiwan_month", "summarize_write_results"]
