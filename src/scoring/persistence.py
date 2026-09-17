"""Persistence envelope for reproducible Market Score results."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from .pipeline import DailyScoreResult


@dataclass(frozen=True)
class MarketScoreRecord:
    """A database-ready, idempotent representation of one daily calculation."""

    model_version: str
    target_date: str
    as_of: str | None
    status: str
    score: float | None
    direction: str | None
    reason: str | None
    calculation_hash: str
    factor_scores: dict[str, dict[str, Any]]
    observation_identities: list[dict[str, Any]]

    @classmethod
    def from_result(cls, result: DailyScoreResult) -> MarketScoreRecord:
        report = result.as_dict()
        canonical = json.dumps(
            report,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
        factor_scores = {
            factor_id: {
                "score": factor["score"],
                "status": factor["score_status"],
                "reason": factor["score_reason"],
            }
            for factor_id, factor in report["factors"].items()
        }
        identities: list[dict[str, Any]] = []
        seen: set[str] = set()
        for factor in report["factors"].values():
            for identity in factor["observation_identities"]:
                identity_key = json.dumps(
                    identity, sort_keys=True, separators=(",", ":")
                )
                if identity_key not in seen:
                    seen.add(identity_key)
                    identities.append(identity)
        return cls(
            model_version=result.model_version,
            target_date=result.target_date,
            as_of=result.as_of,
            status=result.status,
            score=result.score,
            direction=result.direction,
            reason=result.market_score.reason,
            calculation_hash=hashlib.sha256(canonical).hexdigest(),
            factor_scores=factor_scores,
            observation_identities=identities,
        )

    def as_dict(self) -> dict[str, Any]:
        """Return the stable JSON payload and SQL column values."""

        return {
            "model_version": self.model_version,
            "target_date": self.target_date,
            "as_of": self.as_of,
            "status": self.status,
            "score": self.score,
            "direction": self.direction,
            "reason": self.reason,
            "calculation_hash": self.calculation_hash,
            "factor_scores_json": self.factor_scores,
            "observation_identities_json": self.observation_identities,
        }


__all__ = ["MarketScoreRecord"]
