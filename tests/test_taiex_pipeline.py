from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.data import WriteResult, current_taiwan_month, summarize_write_results


def test_current_taiwan_month_converts_runner_clock_before_selecting_month():
    assert current_taiwan_month(datetime(2026, 8, 31, 16, 30, tzinfo=timezone.utc)) == (
        2026,
        9,
    )


def test_current_taiwan_month_requires_timezone():
    with pytest.raises(ValueError, match="timezone-aware"):
        current_taiwan_month(datetime(2026, 9, 1, 0, 0))


def test_summarize_write_results_counts_actions():
    results = [WriteResult(1, "inserted"), WriteResult(2, "duplicate")]
    assert summarize_write_results(results) == {"duplicate": 1, "inserted": 1}
