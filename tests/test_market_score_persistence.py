from __future__ import annotations

from src.scoring import MarketScoreRecord, calculate_daily_score


def test_market_score_record_is_deterministic_and_keeps_unavailable_state() -> None:
    result = calculate_daily_score(
        taiex_observations=[],
        pcr_observations=[],
        tx_observations=[],
        vix_observations=[],
        target_date="2026-09-17",
    )

    first = MarketScoreRecord.from_result(result)
    second = MarketScoreRecord.from_result(result)

    assert first.calculation_hash == second.calculation_hash
    assert len(first.calculation_hash) == 64
    assert first.status == "unavailable"
    assert first.score is None
    assert first.direction is None
    assert first.factor_scores["foreign_cash_5d"]["status"] == "unavailable"
    assert first.as_dict()["observation_identities_json"] == []


def test_market_score_record_hash_changes_when_as_of_changes() -> None:
    first_result = calculate_daily_score(
        taiex_observations=[],
        pcr_observations=[],
        tx_observations=[],
        vix_observations=[],
        target_date="2026-09-17",
        as_of="2026-09-17T14:00:00+08:00",
    )
    second_result = calculate_daily_score(
        taiex_observations=[],
        pcr_observations=[],
        tx_observations=[],
        vix_observations=[],
        target_date="2026-09-17",
        as_of="2026-09-17T16:00:00+08:00",
    )

    assert MarketScoreRecord.from_result(first_result).calculation_hash != (
        MarketScoreRecord.from_result(second_result).calculation_hash
    )
