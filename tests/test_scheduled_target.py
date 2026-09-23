from datetime import datetime
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
    # The UTC cron is Monday-Friday, which runs at 00:30 Tuesday-Saturday in
    # Taipei. Its target is the date that just ended, including Saturday for
    # Friday's session.
    now = datetime(2026, 9, 21, 16, 35, tzinfo=ZoneInfo("UTC"))

    assert (
        resolve_scheduled_target_date(now=now, schedule="30 16 * * 1-5")
        == datetime(2026, 9, 21, tzinfo=TAIPEI).date()
    )


def test_delayed_midnight_confirmation_keeps_previous_date() -> None:
    now = datetime(2026, 9, 22, 4, 5, tzinfo=TAIPEI)

    assert (
        resolve_scheduled_target_date(now=now, schedule="30 16 * * 1-5")
        == datetime(2026, 9, 21, tzinfo=TAIPEI).date()
    )


def test_delayed_midnight_confirmation_before_next_occurrence_keeps_target() -> None:
    # If Tuesday's scheduled run starts shortly before Wednesday's 00:30
    # occurrence, it still belongs to Tuesday's run and targets Monday.
    now = datetime(2026, 9, 23, 0, 15, tzinfo=TAIPEI)

    assert (
        resolve_scheduled_target_date(now=now, schedule="30 16 * * 1-5")
        == datetime(2026, 9, 21, tzinfo=TAIPEI).date()
    )


def test_friday_midnight_confirmation_targets_friday_when_started_saturday() -> None:
    now = datetime(2026, 9, 26, 0, 45, tzinfo=TAIPEI)

    assert (
        resolve_scheduled_target_date(now=now, schedule="30 16 * * 1-5")
        == datetime(2026, 9, 25, tzinfo=TAIPEI).date()
    )


def test_unknown_schedule_is_rejected() -> None:
    with pytest.raises(ValueError, match="unsupported scheduled cron"):
        resolve_scheduled_target_date(
            now=datetime(2026, 9, 21, 23, 10, tzinfo=TAIPEI),
            schedule="0 0 * * *",
        )
