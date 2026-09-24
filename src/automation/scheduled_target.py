"""Resolve a scheduled workflow's intended Taiwan market date."""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from src.automation.twse_calendar import fetch_twse_closed_dates

TAIPEI = ZoneInfo("Asia/Taipei")


@dataclass(frozen=True)
class ScheduledPass:
    local_time: time
    occurrence_weekday: int | None = None
    previous_trading_date: bool = False


SCHEDULES = {
    "30 8 * * 1-5": ScheduledPass(time(16, 30)),
    "0 14 * * 1-5": ScheduledPass(time(22, 0)),
    # Individual UTC weekdays preserve the local scheduled date if a run is
    # delayed into the following Taipei day.
    **{
        f"30 16 * * {utc_weekday}": ScheduledPass(
            time(0, 30), occurrence_weekday=utc_weekday, previous_trading_date=True
        )
        for utc_weekday in range(1, 6)
    },
    # Later morning retry: 22:30 UTC is 06:30 on the following Taipei date.
    **{
        f"30 22 * * {utc_weekday}": ScheduledPass(
            time(6, 30), occurrence_weekday=utc_weekday, previous_trading_date=True
        )
        for utc_weekday in range(1, 6)
    },
}


def is_midnight_confirmation_schedule(schedule: str) -> bool:
    scheduled_pass = SCHEDULES.get(schedule)
    return bool(scheduled_pass and scheduled_pass.previous_trading_date)


def _previous_trading_date(candidate: date, closed_dates: frozenset[date]) -> date:
    while candidate.weekday() >= 5 or candidate in closed_dates:
        candidate -= timedelta(days=1)
    return candidate


def resolve_scheduled_target_date(
    *, now: datetime, schedule: str, closed_dates: frozenset[date] | None = None
) -> date:
    """Return the market date represented by a scheduled workflow run.

    The weekday-specific overnight cron identifies its scheduled Taipei date,
    even when execution crosses the next scheduled occurrence. Its target is
    the most recent Taiwan trading date before that occurrence date. Earlier
    scheduled passes retain their original local-time boundary behavior.
    """

    try:
        scheduled_pass = SCHEDULES[schedule]
    except KeyError as exc:
        raise ValueError(f"unsupported scheduled cron: {schedule!r}") from exc

    local_now = now.astimezone(TAIPEI)
    if scheduled_pass.previous_trading_date:
        if closed_dates is None:
            raise ValueError(
                "closed_dates must be provided for midnight confirmation schedules"
            )
        assert scheduled_pass.occurrence_weekday is not None
        days_since_occurrence = (
            local_now.date().weekday() - scheduled_pass.occurrence_weekday
        ) % 7
        occurrence_date = local_now.date() - timedelta(days=days_since_occurrence)
        if (
            days_since_occurrence == 0
            and local_now.timetz().replace(tzinfo=None) < scheduled_pass.local_time
        ):
            occurrence_date -= timedelta(days=7)
        return _previous_trading_date(occurrence_date - timedelta(days=1), closed_dates)

    target = local_now.date()
    if local_now.timetz().replace(tzinfo=None) < scheduled_pass.local_time:
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
    now = _parse_now(args.now)
    closed_dates = None
    if is_midnight_confirmation_schedule(args.schedule):
        local_year = now.astimezone(TAIPEI).year
        try:
            closed_dates = fetch_twse_closed_dates({local_year - 1, local_year})
        except (OSError, RuntimeError, ValueError) as exc:
            print(
                "Unable to verify the official TWSE trading calendar; "
                f"refusing to infer a target date ({type(exc).__name__}: {exc}).",
                file=sys.stderr,
            )
            return 1

    print(
        resolve_scheduled_target_date(
            now=now, schedule=args.schedule, closed_dates=closed_dates
        ).isoformat()
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
