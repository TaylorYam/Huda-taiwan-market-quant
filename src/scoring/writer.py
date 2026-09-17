"""Storage-neutral write boundary for calculated Market Scores."""

from __future__ import annotations

from typing import Any, Protocol

from .persistence import MarketScoreRecord
from .pipeline import DailyScoreResult


class MarketScoreWriter(Protocol):
    """Minimum store surface required by the score writer."""

    def write_market_score(self, record: dict[str, Any]) -> Any:
        """Insert a derived record or return an idempotent duplicate result."""


def persist_market_score(
    writer: MarketScoreWriter, result: DailyScoreResult
) -> tuple[MarketScoreRecord, Any]:
    """Materialize and persist one calculation without changing its result."""

    record = MarketScoreRecord.from_result(result)
    outcome = writer.write_market_score(record.as_dict())
    return record, outcome


__all__ = ["MarketScoreWriter", "persist_market_score"]
