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


def test_unknown_schedule_is_rejected() -> None:
    with pytest.raises(ValueError, match="unsupported scheduled cron"):
        resolve_scheduled_target_date(
            now=datetime(2026, 9, 21, 23, 10, tzinfo=TAIPEI),
            schedule="0 0 * * *",
        )
