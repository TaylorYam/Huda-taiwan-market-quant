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

# Keep the public explanation concise and aligned with the versioned model.
# Source attribution and score-boundary details remain in the source-status
# section and model documentation rather than being repeated under every chart.
FACTOR_EXPLANATIONS = {
    "taiex_ma20_ma60_trend": {
        "purpose": "判斷大盤目前的主要趨勢方向。",
        "window": "當日收盤、MA20 與 MA60。",
        "logic": "依價格與兩條均線的排列給分：指數 > MA20 > MA60 為 100；指數 < MA20 < MA60 為 0；其餘排列依序給 25、50 或 75。",
        "direction": "均線排列越偏多，分數越高。",
    },
    "taiex_20d_momentum": {
        "purpose": "觀察最近約一個月的大盤價格強弱。",
        "window": "20 個交易日。",
        "logic": "20 日報酬率 = 今日 TAIEX / 20 個交易日前 TAIEX − 1，再與歷史分布比較轉成分數。",
        "direction": "動能越強，分數越高。",
    },
    "foreign_cash_5d": {
        "purpose": "觀察外資近期資金流入或流出。",
        "window": "最近 5 個交易日。",
        "logic": "外資 5 日累計買賣超 ÷ 市場 5 日成交金額，再與歷史分布比較。",
        "direction": "買超比例越高，分數越高。",
    },
    "foreign_tx_net_position": {
        "purpose": "判斷外資台指期目前相對偏多或偏空。",
        "window": "當日外資台指期未平倉部位與歷史分布。",
        "logic": "淨部位 = 多方未平倉 − 空方未平倉，再依外資自身歷史分布轉成分數。",
        "direction": "相對淨多越高，分數越高。",
    },
    "foreign_tx_net_position_5d_change": {
        "purpose": "觀察外資期貨部位正在往哪個方向變化。",
        "window": "今日與 5 個交易日前。",
        "logic": "5 日變化 = 今日淨部位 − 5 個交易日前淨部位。",
        "direction": "加多或減空代表改善，分數越高。",
    },
    "tx_basis": {
        "purpose": "觀察期貨相對現貨的樂觀或保守程度。",
        "window": "當日近月台指期與 TAIEX。",
        "logic": "Basis = 台指期近月價格 − TAIEX。",
        "direction": "正價差方向通常偏多，負價差方向通常偏空。",
    },
    "txo_oi_pcr": {
        "purpose": "觀察選擇權未平倉量的多空與避險結構。",
        "window": "當日 Put OI 與 Call OI。",
        "logic": "OI PCR = Put OI / Call OI，再依歷史分布與模型方向轉成分數。",
        "direction": "依 v0.1 歷史分布判斷；極端值不直接等同單一多空方向。",
    },
    "taiwan_vix": {
        "purpose": "觀察市場波動與恐慌程度。",
        "window": "近一年歷史分布。",
        "logic": "VIX Score = 100 − VIX 歷史百分位。",
        "direction": "VIX 越低、風險越低，分數越高。",
    },
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
    "FACTOR_EXPLANATIONS",
    "FACTOR_LABELS",
    "DashboardFactorRow",
    "DashboardSnapshot",
    "build_snapshot",
]
