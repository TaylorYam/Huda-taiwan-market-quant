"""Resolve a scheduled workflow's intended Taiwan market date."""

from __future__ import annotations

import argparse
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

TAIPEI = ZoneInfo("Asia/Taipei")

# GitHub Actions cron is UTC; these are the corresponding planned local times.
SCHEDULE_LOCAL_TIMES = {
    "30 8 * * 1-5": time(16, 30),
    "0 14 * * 1-5": time(22, 0),
    # 16:30 UTC Monday-Friday is 00:30 Asia/Taipei Tuesday-Saturday.
    "30 16 * * 1-5": time(0, 30),
}
PREVIOUS_LOCAL_DATE_SCHEDULES = {"30 16 * * 1-5"}


def resolve_scheduled_target_date(*, now: datetime, schedule: str) -> date:
    """Return the market date represented by a scheduled workflow run.

    GitHub may start a scheduled run hours after its nominal time. If the first
    pass is delayed past midnight in Taiwan, using ``today`` would incorrectly
    request a future market date. The schedule's planned local time is the
    stable boundary for deciding whether the run belongs to yesterday.
    """

    try:
        scheduled_time = SCHEDULE_LOCAL_TIMES[schedule]
    except KeyError as exc:
        raise ValueError(f"unsupported scheduled cron: {schedule!r}") from exc

    local_now = now.astimezone(TAIPEI)
    if schedule in PREVIOUS_LOCAL_DATE_SCHEDULES:
        # This confirmation cron runs after the Taiwan calendar date rolls
        # over. Use the latest scheduled local occurrence, then target its
        # preceding date. A late start before the next 00:30 occurrence remains
        # attached to the prior run. In weekends or exchange holidays,
        # source-date guards stop the run rather than relabeling older data.
        target = local_now.date() - timedelta(days=1)
        if local_now.timetz().replace(tzinfo=None) < scheduled_time:
            target -= timedelta(days=1)
        return target

    target = local_now.date()
    if local_now.timetz().replace(tzinfo=None) < scheduled_time:
        target -= timedelta(days=1)
    return target


def _parse_now(value: str | None) -> datetime:
    if value is None:
        return datetime.now(TAIPEI)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("--now must be an ISO timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("--now must include a timezone")
    return parsed


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--schedule", required=True)
    parser.add_argument("--now")
    args = parser.parse_args()
    print(
        resolve_scheduled_target_date(
            now=_parse_now(args.now), schedule=args.schedule
        ).isoformat()
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
