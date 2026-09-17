"""Versioned contracts for v0.1 factor and market scores.

The scoring layer is deliberately independent from a data store.  Inputs are
the point-in-time :class:`~src.factors.contracts.FactorInput` values produced
by the factor layer, and score results retain those inputs as evidence.  This
keeps a displayed score reproducible without asking the scoring layer to
re-fetch or infer source observations.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from math import isfinite
from types import MappingProxyType
from typing import Literal

from src.factors.contracts import (
    BASIS_FACTOR_ID,
    FACTOR_AVAILABLE,
    FACTOR_UNAVAILABLE,
    FOREIGN_CASH_FACTOR_ID,
    FOREIGN_TX_CHANGE_FACTOR_ID,
    FOREIGN_TX_POSITION_FACTOR_ID,
    MOMENTUM_FACTOR_ID,
    PCR_FACTOR_ID,
    TREND_FACTOR_ID,
    VIX_FACTOR_ID,
    FactorInput,
    ObservationIdentity,
)

MODEL_VERSION = "v0.1"

# Weights are fractions of the total (the model document expresses them as
# percentages).  A read-only mapping prevents callers from silently changing
# the model used to produce a persisted result.
FACTOR_WEIGHTS: Mapping[str, float] = MappingProxyType(
    {
        TREND_FACTOR_ID: 0.20,
        MOMENTUM_FACTOR_ID: 0.10,
        FOREIGN_CASH_FACTOR_ID: 0.15,
        FOREIGN_TX_POSITION_FACTOR_ID: 0.15,
        FOREIGN_TX_CHANGE_FACTOR_ID: 0.10,
        BASIS_FACTOR_ID: 0.05,
        PCR_FACTOR_ID: 0.10,
        VIX_FACTOR_ID: 0.15,
    }
)
REQUIRED_FACTOR_IDS = tuple(FACTOR_WEIGHTS)

STRONG_BEAR = "強空"
BEAR = "偏空"
NEUTRAL = "中性／觀望"
BULL = "偏多"
STRONG_BULL = "強多"
MarketDirection = Literal["強空", "偏空", "中性／觀望", "偏多", "強多"]
ScoreStatus = Literal["available", "unavailable"]


@dataclass(frozen=True)
class FactorScore:
    """A single factor's normalized score and its point-in-time evidence."""

    factor_id: str
    score: float | None
    status: ScoreStatus
    model_version: str = MODEL_VERSION
    evidence: FactorInput | None = None
    reason: str | None = None

    @property
    def available(self) -> bool:
        return self.status == FACTOR_AVAILABLE and self.score is not None

    @property
    def observation_identities(self) -> tuple[ObservationIdentity, ...]:
        """Source identities carried by the factor input."""

        if self.evidence is None:
            return ()
        return self.evidence.observation_identities

    @property
    def observations(self) -> tuple[ObservationIdentity, ...]:
        """Compatibility alias for callers using the factor contract name."""

        return self.observation_identities


@dataclass(frozen=True)
class MarketScore:
    """The aggregate score, state, component results, and retained evidence."""

    score: float | None
    direction: MarketDirection | None
    status: ScoreStatus
    factor_scores: Mapping[str, FactorScore]
    model_version: str = MODEL_VERSION
    missing_factor_ids: tuple[str, ...] = ()
    reason: str | None = None

    @property
    def available(self) -> bool:
        return self.status == FACTOR_AVAILABLE and self.score is not None

    @property
    def market_score(self) -> float | None:
        """Descriptive alias used by dashboard and persistence callers."""

        return self.score

    @property
    def label(self) -> MarketDirection | None:
        return self.direction

    @property
    def state(self) -> MarketDirection | None:
        return self.direction

    @property
    def evidence(self) -> Mapping[str, FactorInput | None]:
        """Factor evidence keyed by factor id, without losing unavailable inputs."""

        return MappingProxyType(
            {
                factor_id: result.evidence
                for factor_id, result in self.factor_scores.items()
            }
        )

    @property
    def observation_identities(self) -> tuple[ObservationIdentity, ...]:
        """Flattened, de-duplicated source identities for the aggregate result."""

        identities: list[ObservationIdentity] = []
        seen: set[ObservationIdentity] = set()
        for result in self.factor_scores.values():
            for identity in result.observation_identities:
                if identity not in seen:
                    seen.add(identity)
                    identities.append(identity)
        return tuple(identities)

    @property
    def observations(self) -> tuple[ObservationIdentity, ...]:
        return self.observation_identities


def classify_score(score: float) -> MarketDirection:
    """Map a valid score to the mutually exclusive v0.1 market state."""

    if not isfinite(score) or score < 0 or score > 100:
        raise ValueError("score must be finite and within [0, 100]")
    if score < 20:
        return STRONG_BEAR
    if score < 40:
        return BEAR
    if score < 60:
        return NEUTRAL
    if score < 80:
        return BULL
    return STRONG_BULL


# Names used by callers that describe this operation as bucketing rather than
# classification.  Keeping these aliases costs nothing and makes the contract
# explicit at both API boundaries.
market_direction = classify_score
score_bucket = classify_score


def _validate_score(score: float) -> float:
    score = float(score)
    if not isfinite(score) or score < 0 or score > 100:
        raise ValueError("factor score must be finite and within [0, 100]")
    return score


def _as_factor_input(factor: FactorInput | FactorScore) -> FactorInput | None:
    if isinstance(factor, FactorScore):
        return factor.evidence if factor.available else None
    return factor


def score_factor(
    factor: FactorInput | FactorScore,
    *,
    model_version: str = MODEL_VERSION,
) -> FactorScore:
    """Normalize one factor input to 0–100.

    Trend uses the five explicit MA rules from the model document.  Scalar
    inputs may carry a pre-normalized ``value`` (with no raw ``values`` map),
    or a ``values['score']`` field.  Raw scalar normalization against a
    historical distribution is intentionally deferred until the model fixes
    those windows and thresholds.
    """

    if isinstance(factor, FactorScore):
        if factor.model_version != model_version:
            raise ValueError("factor and requested model versions differ")
        return factor
    if not isinstance(factor, FactorInput):
        raise TypeError("factor must be a FactorInput or FactorScore")
    if factor.status != FACTOR_AVAILABLE:
        return FactorScore(
            factor.factor_id,
            None,
            FACTOR_UNAVAILABLE,
            model_version,
            factor,
            factor.reason or "factor_input_unavailable",
        )

    if factor.factor_id == TREND_FACTOR_ID:
        values = factor.values or {}
        try:
            close = float(values["close"])
            ma20 = float(values["ma20"])
            ma60 = float(values["ma60"])
        except (KeyError, TypeError, ValueError):
            return FactorScore(
                factor.factor_id,
                None,
                FACTOR_UNAVAILABLE,
                model_version,
                factor,
                "trend_requires_close_ma20_ma60",
            )
        if not all(isfinite(value) for value in (close, ma20, ma60)):
            return FactorScore(
                factor.factor_id,
                None,
                FACTOR_UNAVAILABLE,
                model_version,
                factor,
                "trend_requires_finite_values",
            )
        if close > ma20 > ma60:
            score = 100.0
        elif close > ma20:
            score = 75.0
        elif close < ma20 < ma60:
            score = 0.0
        elif close < ma20:
            score = 25.0
        else:
            score = 50.0
        return FactorScore(
            factor.factor_id, score, FACTOR_AVAILABLE, model_version, factor
        )

    if factor.value is None:
        return FactorScore(
            factor.factor_id,
            None,
            FACTOR_UNAVAILABLE,
            model_version,
            factor,
            "scalar_factor_value_missing",
        )
    try:
        value = float(factor.value)
    except (TypeError, ValueError):
        value = float("nan")
    try:
        raw_values = factor.values or {}
        if "score" in raw_values:
            score = _validate_score(raw_values["score"])
        elif not raw_values and isfinite(value):
            score = _validate_score(value)
        else:
            raise ValueError("scalar_factor_requires_normalized_score")
    except (TypeError, ValueError) as exc:
        return FactorScore(
            factor.factor_id,
            None,
            FACTOR_UNAVAILABLE,
            model_version,
            factor,
            str(exc),
        )
    return FactorScore(factor.factor_id, score, FACTOR_AVAILABLE, model_version, factor)


def calculate_factor_score(*args, **kwargs) -> FactorScore:
    """Descriptive alias for :func:`score_factor`."""

    return score_factor(*args, **kwargs)


__all__ = [
    "BEAR",
    "BULL",
    "FACTOR_WEIGHTS",
    "MODEL_VERSION",
    "NEUTRAL",
    "REQUIRED_FACTOR_IDS",
    "STRONG_BEAR",
    "STRONG_BULL",
    "FactorScore",
    "MarketDirection",
    "MarketScore",
    "calculate_factor_score",
    "classify_score",
    "market_direction",
    "score_bucket",
    "score_factor",
]
