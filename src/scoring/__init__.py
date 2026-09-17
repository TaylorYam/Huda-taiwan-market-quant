"""Versioned factor and Market Score contracts for model v0.1."""

from .contracts import (
    BEAR,
    BULL,
    FACTOR_WEIGHTS,
    MODEL_VERSION,
    NEUTRAL,
    REQUIRED_FACTOR_IDS,
    STRONG_BEAR,
    STRONG_BULL,
    FactorScore,
    MarketDirection,
    MarketScore,
    calculate_factor_score,
    classify_score,
    market_direction,
    score_bucket,
    score_factor,
)
from .engine import (
    aggregate_scores,
    calculate_market_score,
    score_market,
)

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
    "aggregate_scores",
    "calculate_factor_score",
    "calculate_market_score",
    "classify_score",
    "market_direction",
    "score_bucket",
    "score_factor",
    "score_market",
]
