from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest

from src.automation.scheduled_target import resolve_scheduled_target_date

TAIPEI = ZoneInfo("Asia/Taipei")


def test_delayed_first_pass_after_midnight_keeps_previous_market_date() -> None:
    now = datetime(2026, 9, 22, 3, 5, tzinfo=TAIPEI)

    assert (
        resolve_scheduled_target_date(now=now, schedule="30 8 * * 1-5")
        == datetime(2026, 9, 21, tzinfo=TAIPEI).date()
    )


def test_confirmation_pass_keeps_same_date_after_planned_time() -> None:
    now = datetime(2026, 9, 21, 23, 10, tzinfo=TAIPEI)

    assert (
        resolve_scheduled_target_date(now=now, schedule="0 14 * * 1-5")
        == datetime(2026, 9, 21, tzinfo=TAIPEI).date()
    )


def test_midnight_confirmation_targets_previous_taipei_date() -> None:
    # Monday's UTC cron is Tuesday at 00:30 in Taipei and targets Monday.
    now = datetime(2026, 9, 21, 16, 35, tzinfo=ZoneInfo("UTC"))

    assert (
        resolve_scheduled_target_date(
            now=now, schedule="30 16 * * 1", closed_dates=frozenset()
        )
        == datetime(2026, 9, 21, tzinfo=TAIPEI).date()
    )


def test_delayed_midnight_confirmation_keeps_previous_date() -> None:
    now = datetime(2026, 9, 22, 4, 5, tzinfo=TAIPEI)

    assert (
        resolve_scheduled_target_date(
            now=now, schedule="30 16 * * 1", closed_dates=frozenset()
        )
        == datetime(2026, 9, 21, tzinfo=TAIPEI).date()
    )


def test_delayed_midnight_confirmation_after_next_occurrence_keeps_target() -> None:
    # The Tuesday-specific cron identifies Tuesday even after Wednesday's
    # 00:30 cron has also become eligible to run.
    now = datetime(2026, 9, 23, 0, 40, tzinfo=TAIPEI)

    assert (
        resolve_scheduled_target_date(
            now=now, schedule="30 16 * * 1", closed_dates=frozenset()
        )
        == datetime(2026, 9, 21, tzinfo=TAIPEI).date()
    )


def test_friday_midnight_confirmation_targets_friday_when_started_saturday() -> None:
    now = datetime(2026, 9, 26, 0, 45, tzinfo=TAIPEI)

    assert (
        resolve_scheduled_target_date(
            now=now, schedule="30 16 * * 5", closed_dates=frozenset()
        )
        == datetime(2026, 9, 25, tzinfo=TAIPEI).date()
    )


def test_delayed_saturday_confirmation_on_monday_still_targets_friday() -> None:
    # There is no Sunday or Monday 00:30 run; a delayed Saturday run must still
    # resolve to the latest scheduled occurrence rather than a weekend date.
    now = datetime(2026, 9, 28, 0, 15, tzinfo=TAIPEI)

    assert (
        resolve_scheduled_target_date(
            now=now, schedule="30 16 * * 5", closed_dates=frozenset()
        )
        == datetime(2026, 9, 25, tzinfo=TAIPEI).date()
    )


def test_midnight_confirmation_skips_official_twse_holiday() -> None:
    now = datetime(2026, 9, 28, 16, 40, tzinfo=ZoneInfo("UTC"))

    assert resolve_scheduled_target_date(
        now=now,
        schedule="30 16 * * 1",
        closed_dates=frozenset({date(2026, 9, 28)}),
    ) == date(2026, 9, 25)


def test_unknown_schedule_is_rejected() -> None:
    with pytest.raises(ValueError, match="unsupported scheduled cron"):
        resolve_scheduled_target_date(
            now=datetime(2026, 9, 21, 23, 10, tzinfo=TAIPEI),
            schedule="0 0 * * *",
        )


def test_midnight_confirmation_requires_validated_calendar() -> None:
    with pytest.raises(ValueError, match="closed_dates must be provided"):
        resolve_scheduled_target_date(
            now=datetime(2026, 9, 21, 16, 35, tzinfo=ZoneInfo("UTC")),
            schedule="30 16 * * 1",
        )
