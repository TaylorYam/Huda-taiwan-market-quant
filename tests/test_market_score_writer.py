from __future__ import annotations

from dataclasses import dataclass

from src.scoring import calculate_daily_score, persist_market_score


@dataclass
class FakeWriter:
    records: list[dict[str, object]]

    def write_market_score(self, record: dict[str, object]) -> dict[str, object]:
        self.records.append(record)
        return {"score_id": len(self.records), "action": "inserted"}


def test_persist_market_score_writes_canonical_record_without_recalculation() -> None:
    result = calculate_daily_score(
        taiex_observations=[],
        pcr_observations=[],
        tx_observations=[],
        vix_observations=[],
        target_date="2026-09-17",
    )
    writer = FakeWriter([])

    record, outcome = persist_market_score(writer, result)

    assert outcome == {"score_id": 1, "action": "inserted"}
    assert writer.records[0]["calculation_hash"] == record.calculation_hash
    assert writer.records[0]["status"] == "unavailable"
    assert writer.records[0]["score"] is None
