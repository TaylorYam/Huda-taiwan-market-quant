"""Read-only dashboard view models built from a calculated daily score.

The dashboard layer formats an already calculated result. It never fetches
source observations or recalculates factors, which keeps the displayed state
traceable to the persisted score pipeline.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from src.scoring.pipeline import DailyScoreResult

FACTOR_LABELS = {
    "taiex_ma20_ma60_trend": "TAIEX 均線趨勢",
    "taiex_20d_momentum": "TAIEX 20 日動能",
    "foreign_cash_5d": "外資現貨 5 日",
    "foreign_tx_net_position": "外資台指期淨部位",
    "foreign_tx_net_position_5d_change": "外資台指期 5 日變化",
    "tx_basis": "期現貨價差",
    "txo_oi_pcr": "選擇權 OI PCR",
    "taiwan_vix": "Taiwan VIX",
}

FACTOR_CATEGORIES = {
    "taiex_ma20_ma60_trend": "技術",
    "taiex_20d_momentum": "技術",
    "foreign_cash_5d": "現貨籌碼",
    "foreign_tx_net_position": "期貨籌碼",
    "foreign_tx_net_position_5d_change": "期貨籌碼",
    "tx_basis": "期貨",
    "txo_oi_pcr": "選擇權",
    "taiwan_vix": "市場風險",
}


@dataclass(frozen=True)
class DashboardFactorRow:
    """One display row for a factor, including its data-quality state."""

    factor_id: str
    label: str
    category: str
    status: str
    score: float | None
    raw_value: float | None
    reason: str | None
    observation_count: int


@dataclass(frozen=True)
class DashboardSnapshot:
    """The complete read-only payload a dashboard renderer needs."""

    target_date: str
    as_of: str | None
    model_version: str
    status: str
    score: float | None
    direction: str | None
    reason: str | None
    factors: tuple[DashboardFactorRow, ...]

    @property
    def headline(self) -> str:
        if self.status != "available":
            return "Market Score 尚不可用"
        return self.direction or "Market Score"

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["factors"] = [asdict(row) for row in self.factors]
        payload["headline"] = self.headline
        return payload


def build_snapshot(result: DailyScoreResult) -> DashboardSnapshot:
    """Format a pipeline result without changing its calculation."""

    rows = tuple(
        DashboardFactorRow(
            factor_id=factor_id,
            label=FACTOR_LABELS.get(factor_id, factor_id),
            category=FACTOR_CATEGORIES.get(factor_id, "其他"),
            status=result.factor_scores[factor_id].status,
            score=result.factor_scores[factor_id].score,
            raw_value=factor.value,
            reason=result.factor_scores[factor_id].reason or factor.reason,
            observation_count=len(factor.observation_identities),
        )
        for factor_id, factor in result.factor_inputs.items()
    )
    return DashboardSnapshot(
        target_date=result.target_date,
        as_of=result.as_of,
        model_version=result.model_version,
        status=result.status,
        score=result.score,
        direction=result.direction,
        reason=result.market_score.reason,
        factors=rows,
    )


__all__ = [
    "FACTOR_CATEGORIES",
    "FACTOR_LABELS",
    "DashboardFactorRow",
    "DashboardSnapshot",
    "build_snapshot",
]
