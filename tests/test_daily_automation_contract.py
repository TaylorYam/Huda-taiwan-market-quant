from __future__ import annotations

from typing import Any

from src.data.storage import Observation
from src.data.supabase_rest import MarketScoreWriteResult
from src.scoring.daily_runner import run_daily_score


class EmptyReader:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def load_score_observations(
        self, *, dataset_ids: tuple[str, ...], target_date: str, as_of: str
    ) -> list[Observation]:
        self.calls.append(
            {
                "dataset_ids": dataset_ids,
                "target_date": target_date,
                "as_of": as_of,
            }
        )
        return []


class RecordingWriter:
    def __init__(self) -> None:
        self.records: list[dict[str, Any]] = []

    def write_market_score(self, record: dict[str, Any]) -> MarketScoreWriteResult:
        self.records.append(record)
        return MarketScoreWriteResult(score_id=1, action="inserted")


def test_daily_runner_contract_preserves_explicit_window_and_unavailable_result() -> (
    None
):
    """The automation boundary is deterministic even when every source is absent."""

    reader = EmptyReader()
    writer = RecordingWriter()

    summary = run_daily_score(
        reader,
        writer,
        target_date="2026-09-17",
        # Equivalent UTC input must be canonicalized to the Taiwan boundary.
        as_of="2026-09-17T12:00:00Z",
    )

    assert reader.calls[0]["target_date"] == "2026-09-17"
    assert reader.calls[0]["as_of"] == "2026-09-17T20:00:00+08:00"
    assert summary["target_date"] == "2026-09-17"
    assert summary["as_of"] == "2026-09-17T20:00:00+08:00"
    assert summary["status"] == "unavailable"
    assert summary["score"] is None
    assert summary["action"] == "inserted"
    assert writer.records[0]["status"] == "unavailable"
    assert writer.records[0]["score"] is None
