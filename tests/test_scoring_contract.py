from __future__ import annotations

import pytest

from src.factors.contracts import (
    FACTOR_AVAILABLE,
    TREND_FACTOR_ID,
    FactorInput,
    ObservationIdentity,
)
from src.scoring import (
    FACTOR_WEIGHTS,
    MODEL_VERSION,
    REQUIRED_FACTOR_IDS,
    STRONG_BEAR,
    STRONG_BULL,
    aggregate_scores,
    calculate_market_score,
    classify_score,
    score_factor,
)


def _factors(score: float = 50.0) -> dict[str, float]:
    return {factor_id: score for factor_id in REQUIRED_FACTOR_IDS}


@pytest.mark.parametrize(
    ("score", "label"),
    [
        (0, STRONG_BEAR),
        (19.999999, STRONG_BEAR),
        (20, "偏空"),
        (39.999999, "偏空"),
        (40, "中性／觀望"),
        (59.999999, "中性／觀望"),
        (60, "偏多"),
        (79.999999, "偏多"),
        (80, STRONG_BULL),
        (100, STRONG_BULL),
    ],
)
def test_v01_score_interval_endpoints(score: float, label: str) -> None:
    assert classify_score(score) == label
    result = calculate_market_score(_factors(score))
    assert result.score == pytest.approx(score)
    assert result.direction == label


def test_market_score_uses_all_fixed_weights_without_renormalizing() -> None:
    assert sum(FACTOR_WEIGHTS.values()) == pytest.approx(1.0)
    factors = _factors()
    factors.pop(REQUIRED_FACTOR_IDS[-1])

    result = calculate_market_score(factors)

    assert result.score is None
    assert result.status == "unavailable"
    assert result.direction is None
    assert REQUIRED_FACTOR_IDS[-1] in result.missing_factor_ids


def test_factor_score_applies_v01_trend_rules_and_keeps_evidence() -> None:
    identity = ObservationIdentity(
        dataset_id="twse_taiex_daily_v1",
        observation_date="2026-09-17",
        source_record_key="record",
        source_payload_hash="a" * 64,
    )
    input_value = FactorInput(
        factor_id=TREND_FACTOR_ID,
        observation_date="2026-09-17",
        status=FACTOR_AVAILABLE,
        values={"close": 110, "ma20": 105, "ma60": 100},
        observation_identities=(identity,),
    )

    result = score_factor(input_value)

    assert result.score == 100
    assert result.model_version == MODEL_VERSION
    assert result.evidence is input_value
    assert result.observation_identities == (identity,)


def test_market_score_retains_factor_evidence_and_model_version() -> None:
    identity = ObservationIdentity(
        dataset_id="twse_taiex_daily_v1",
        observation_date="2026-09-17",
        source_record_key="record",
    )
    factors: dict[str, FactorInput | float] = _factors()
    factors[TREND_FACTOR_ID] = FactorInput(
        factor_id=TREND_FACTOR_ID,
        observation_date="2026-09-17",
        status=FACTOR_AVAILABLE,
        values={"close": 110, "ma20": 105, "ma60": 100},
        observation_identities=(identity,),
    )

    result = aggregate_scores(factors)

    assert result.model_version == MODEL_VERSION
    assert result.evidence[TREND_FACTOR_ID] is factors[TREND_FACTOR_ID]
    assert result.observation_identities == (identity,)


def test_invalid_direction_score_is_rejected() -> None:
    with pytest.raises(ValueError):
        classify_score(100.01)
