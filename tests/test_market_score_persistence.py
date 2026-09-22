from __future__ import annotations

from datetime import date

from test_daily_score_pipeline import _source_observations

from src.factors.contracts import (
    BASIS_FACTOR_ID,
    MOMENTUM_FACTOR_ID,
    PCR_FACTOR_ID,
    VIX_FACTOR_ID,
)
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


def test_market_score_record_retains_raw_factor_evidence_for_display() -> None:
    taiex, pcr, tx, vix = _source_observations(date(2026, 9, 17))
    result = calculate_daily_score(
        taiex_observations=taiex,
        pcr_observations=pcr,
        tx_observations=tx,
        vix_observations=vix,
        target_date="2026-09-17",
        historical_values={BASIS_FACTOR_ID: [-100, 0, 100]},
    )

    factor = MarketScoreRecord.from_result(result).factor_scores[BASIS_FACTOR_ID]
    assert factor["status"] == "available"
    assert factor["raw_value"] == 50
    assert factor["raw_values"] == {
        "tx_close": 20050,
        "taiex_close": 20000,
        "basis": 50,
    }
    assert factor["window_start"] == "2026-09-17"
    assert factor["window_end"] == "2026-09-17"


def test_market_score_record_retains_raw_evidence_for_each_available_factor() -> None:
    taiex, pcr, tx, vix = _source_observations(date(2026, 9, 17))
    result = calculate_daily_score(
        taiex_observations=taiex,
        pcr_observations=pcr,
        tx_observations=tx,
        vix_observations=vix,
        target_date="2026-09-17",
        historical_values={
            MOMENTUM_FACTOR_ID: [0.0, 0.01, 0.02],
            BASIS_FACTOR_ID: [-100, 0, 100],
            PCR_FACTOR_ID: [0.8, 1.0, 1.2],
            VIX_FACTOR_ID: [15, 20, 30],
        },
    )

    record = MarketScoreRecord.from_result(result)
    available = {
        factor_id: factor
        for factor_id, factor in record.factor_scores.items()
        if factor["status"] == "available"
    }
    assert available
    assert all(
        factor["raw_values"] or factor["raw_value"] is not None
        for factor in available.values()
    )
