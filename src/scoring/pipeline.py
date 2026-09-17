"""Point-in-time v0.1 factor and Market Score orchestration.

This module joins the pure factor adapters to the scoring contract.  It does
not know about SQLite, Supabase, or a dashboard: callers provide the source
observations and, for percentile-based factors, the historical values that
were available at the same as-of boundary.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from types import MappingProxyType
from typing import Any

from src.factors.contracts import (
    AsOfPolicy,
    FactorInput,
    adapt_v01_inputs,
)

from .contracts import MODEL_VERSION, FactorScore, MarketScore, score_factor
from .engine import calculate_market_score


@dataclass(frozen=True)
class DailyScoreResult:
    """A reproducible score calculation for one observation date."""

    target_date: str
    as_of: str | None
    factor_inputs: Mapping[str, FactorInput]
    factor_scores: Mapping[str, FactorScore]
    market_score: MarketScore
    model_version: str = MODEL_VERSION

    @property
    def status(self) -> str:
        return self.market_score.status

    @property
    def score(self) -> float | None:
        return self.market_score.score

    @property
    def direction(self) -> str | None:
        return self.market_score.direction

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable report for a CLI or dashboard."""

        return {
            "target_date": self.target_date,
            "as_of": self.as_of,
            "model_version": self.model_version,
            "status": self.status,
            "score": self.score,
            "direction": self.direction,
            "missing_factor_ids": list(self.market_score.missing_factor_ids),
            "reason": self.market_score.reason,
            "factors": {
                factor_id: {
                    "status": factor.status,
                    "value": factor.value,
                    "values": dict(factor.values or {}),
                    "reason": factor.reason,
                    "window_start": factor.window_start,
                    "window_end": factor.window_end,
                    "observation_identities": [
                        {
                            "dataset_id": identity.dataset_id,
                            "observation_date": identity.observation_date,
                            "source_record_key": identity.source_record_key,
                            "source_payload_hash": identity.source_payload_hash,
                            "publication_label": identity.publication_label,
                            "source_revision": identity.source_revision,
                            "observation_id": identity.observation_id,
                        }
                        for identity in factor.observation_identities
                    ],
                    "score": self.factor_scores[factor_id].score,
                    "score_status": self.factor_scores[factor_id].status,
                    "score_reason": self.factor_scores[factor_id].reason,
                }
                for factor_id, factor in self.factor_inputs.items()
            },
        }


def calculate_daily_score(
    *,
    taiex_observations: Sequence[Any],
    pcr_observations: Sequence[Any],
    tx_observations: Sequence[Any],
    vix_observations: Sequence[Any],
    institutional_observations: Sequence[Any] | None = None,
    target_date: date | str,
    as_of: date | datetime | str | None = None,
    as_of_policy: AsOfPolicy = "observation_date",
    historical_values: Mapping[str, Sequence[float]] | None = None,
    model_version: str = MODEL_VERSION,
) -> DailyScoreResult:
    """Build and score all v0.1 factors for one target date.

    ``historical_values`` is keyed by factor id and must contain only values
    known at the selected as-of boundary.  Omitting a history leaves that
    percentile-based factor explicitly unavailable; it never silently becomes
    a neutral score.
    """

    target = _date_text(target_date)
    as_of_text = _as_of_text(as_of)
    factor_inputs = adapt_v01_inputs(
        taiex_observations=taiex_observations,
        pcr_observations=pcr_observations,
        tx_observations=tx_observations,
        vix_observations=vix_observations,
        institutional_observations=institutional_observations,
        target_date=target,
        as_of=as_of,
        as_of_policy=as_of_policy,
    )
    history = historical_values or {}
    factor_scores = {
        factor_id: score_factor(
            factor,
            historical_values=history.get(factor_id),
            model_version=model_version,
        )
        for factor_id, factor in factor_inputs.items()
    }
    market_score = calculate_market_score(
        factor_scores,
        model_version=model_version,
    )
    return DailyScoreResult(
        target_date=target,
        as_of=as_of_text,
        factor_inputs=MappingProxyType(dict(factor_inputs)),
        factor_scores=MappingProxyType(factor_scores),
        market_score=market_score,
        model_version=model_version,
    )


def _date_text(value: date | str) -> str:
    parsed = date.fromisoformat(value) if isinstance(value, str) else value
    return parsed.isoformat()


def _as_of_text(value: date | datetime | str | None) -> str | None:
    if value is None:
        return None
    return value.isoformat() if isinstance(value, (date, datetime)) else value


__all__ = ["DailyScoreResult", "calculate_daily_score"]
