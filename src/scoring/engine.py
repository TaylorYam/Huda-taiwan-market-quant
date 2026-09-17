"""Aggregation of v0.1 factor scores into a Market Score."""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType
from typing import TypeAlias

from src.factors.contracts import FACTOR_AVAILABLE, FACTOR_UNAVAILABLE, FactorInput

from .contracts import (
    FACTOR_WEIGHTS,
    MODEL_VERSION,
    REQUIRED_FACTOR_IDS,
    FactorScore,
    MarketScore,
    classify_score,
    score_factor,
)

FactorScoreInput: TypeAlias = FactorInput | FactorScore | float | int


def _as_score(
    factor_id: str,
    value: FactorScoreInput,
    *,
    model_version: str,
) -> FactorScore:
    if isinstance(value, FactorScore):
        if value.factor_id != factor_id:
            raise ValueError(
                f"factor score key {factor_id!r} does not match {value.factor_id!r}"
            )
        if value.model_version != model_version:
            raise ValueError("factor score and requested model versions differ")
        return value
    if isinstance(value, FactorInput):
        if value.factor_id != factor_id:
            raise ValueError(
                f"factor input key {factor_id!r} does not match {value.factor_id!r}"
            )
        return score_factor(value, model_version=model_version)
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise TypeError(
            "factor values must be FactorInput, FactorScore, or numeric"
        ) from exc
    if result < 0 or result > 100:
        raise ValueError("factor scores must be within [0, 100]")
    return FactorScore(factor_id, result, FACTOR_AVAILABLE, model_version)


def calculate_market_score(
    factors: Mapping[str, FactorScoreInput],
    *,
    model_version: str = MODEL_VERSION,
) -> MarketScore:
    """Calculate a complete v0.1 weighted Market Score.

    The eight model factors are all required.  Missing or unavailable inputs
    therefore produce an explicit unavailable result and never trigger a
    re-normalized partial weight calculation.
    """

    factor_scores: dict[str, FactorScore] = {}
    missing: list[str] = []
    for factor_id in REQUIRED_FACTOR_IDS:
        if factor_id not in factors:
            missing.append(factor_id)
            continue
        result = _as_score(factor_id, factors[factor_id], model_version=model_version)
        factor_scores[factor_id] = result
        if not result.available:
            missing.append(factor_id)

    if missing:
        return MarketScore(
            score=None,
            direction=None,
            status=FACTOR_UNAVAILABLE,
            factor_scores=MappingProxyType(factor_scores),
            model_version=model_version,
            missing_factor_ids=tuple(missing),
            reason="missing_or_unavailable_required_factors",
        )

    total = sum(
        factor_scores[factor_id].score * FACTOR_WEIGHTS[factor_id]  # type: ignore[operator]
        for factor_id in REQUIRED_FACTOR_IDS
    )
    # A complete weighted average of validated [0, 100] inputs is already in
    # range.  Clamp only to protect the public contract from floating roundoff.
    total = min(100.0, max(0.0, total))
    return MarketScore(
        score=total,
        direction=classify_score(total),
        status=FACTOR_AVAILABLE,
        factor_scores=MappingProxyType(factor_scores),
        model_version=model_version,
    )


def aggregate_scores(*args, **kwargs) -> MarketScore:
    """Alias for :func:`calculate_market_score`."""

    return calculate_market_score(*args, **kwargs)


def score_market(*args, **kwargs) -> MarketScore:
    """Alias for :func:`calculate_market_score`."""

    return calculate_market_score(*args, **kwargs)


__all__ = [
    "FactorScoreInput",
    "aggregate_scores",
    "calculate_market_score",
    "score_market",
]
