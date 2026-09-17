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
from .persistence import MarketScoreRecord
from .pipeline import DailyScoreResult, calculate_daily_score

__all__ = [
    "BEAR",
    "BULL",
    "FACTOR_WEIGHTS",
    "MODEL_VERSION",
    "NEUTRAL",
    "REQUIRED_FACTOR_IDS",
    "STRONG_BEAR",
    "STRONG_BULL",
    "DailyScoreResult",
    "FactorScore",
    "MarketDirection",
    "MarketScore",
    "MarketScoreRecord",
    "aggregate_scores",
    "calculate_daily_score",
    "calculate_factor_score",
    "calculate_market_score",
    "classify_score",
    "market_direction",
    "score_bucket",
    "score_factor",
    "score_market",
]
