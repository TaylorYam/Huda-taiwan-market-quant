"""Layer 1 backtest: does Market Score actually rank future TAIEX returns?

docs/backtest-spec-v0.1.md splits validation into two layers and requires the
first to pass before the second (position sizing, Sharpe, drawdown) is even
attempted. This module implements only that first layer: replay the
point-in-time Market Score on every historical trading day, then check
whether higher scores were actually followed by better forward TAIEX
returns. It does not simulate a strategy or costs.

Point-in-time semantics differ from src/scoring/daily_runner.py's live run.
The live runner gates eligible observations on ``retrieved_at``,
``ingested_at`` and ``published_at`` because those timestamps record when a
collector actually saw the data, which matters for a same-day production
run. For a replay over bulk-backfilled history, every row's collection
timestamps read "whenever the backfill happened to run" (e.g. today),
regardless of the row's own observation date; gating on them would make
every historical day look like it had no data yet. This module therefore
calls the scoring layer with ``as_of=None``, which falls back to filtering
purely on ``observation_date <= target_date`` in every factor adapter — the
only knowledge boundary that is meaningful for a bulk historical replay.

Rolling/expanding history (docs/backtest-spec-v0.1.md#5) still applies: each
day's percentile history is rebuilt by :func:`src.scoring.history.build_historical_values`
from only the observations dated before that day, never precomputed once
over the full period and backfilled.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from itertools import pairwise
from statistics import median
from typing import Any

from src.factors.contracts import FACTOR_AVAILABLE, TAIEX_DATASET_ID
from src.scoring.contracts import (
    BEAR,
    BULL,
    MODEL_VERSION,
    NEUTRAL,
    STRONG_BEAR,
    STRONG_BULL,
)
from src.scoring.history import build_historical_values
from src.scoring.pipeline import DailyScoreResult, calculate_daily_score

FORWARD_RETURN_HORIZONS: tuple[int, ...] = (5, 10, 20)
PRIMARY_HORIZON = 10

# Canonical low-to-high order for the five v0.1 buckets, reusing the same
# direction labels src.scoring.contracts.classify_score already assigns to
# an available Market Score, so a bucket boundary can never drift from the
# one the live pipeline reports as a day's direction.
BUCKET_ORDER: tuple[str, ...] = (STRONG_BEAR, BEAR, NEUTRAL, BULL, STRONG_BULL)
BUCKET_RANGE_LABEL: Mapping[str, str] = {
    STRONG_BEAR: "[0, 20)",
    BEAR: "[20, 40)",
    NEUTRAL: "[40, 60)",
    BULL: "[60, 80)",
    STRONG_BULL: "[80, 100]",
}


@dataclass(frozen=True)
class DailyBacktestRow:
    """One trading day's point-in-time score and its realized forward returns."""

    target_date: str
    status: str
    score: float | None
    direction: str | None
    missing_factor_ids: tuple[str, ...]
    forward_returns: Mapping[int, float | None]

    def as_dict(self) -> dict[str, Any]:
        return {
            "target_date": self.target_date,
            "status": self.status,
            "score": self.score,
            "direction": self.direction,
            "missing_factor_ids": list(self.missing_factor_ids),
            "forward_returns": dict(self.forward_returns),
        }


@dataclass(frozen=True)
class BucketStats:
    """Forward-return statistics for one score bucket, across all horizons."""

    direction: str
    range_label: str
    sample_count: int
    avg_return: Mapping[int, float | None]
    median_return: Mapping[int, float | None]
    positive_ratio: Mapping[int, float | None]

    def as_dict(self) -> dict[str, Any]:
        return {
            "direction": self.direction,
            "range": self.range_label,
            "sample_count": self.sample_count,
            "avg_return": dict(self.avg_return),
            "median_return": dict(self.median_return),
            "positive_ratio": dict(self.positive_ratio),
        }


@dataclass(frozen=True)
class Layer1Report:
    """The full Layer 1 result: per-day rows plus per-bucket aggregates."""

    model_version: str
    backtest_start: str
    backtest_end: str
    horizons: tuple[int, ...]
    primary_horizon: int
    scored_days: int
    available_days: int
    buckets: tuple[BucketStats, ...]
    daily_rows: tuple[DailyBacktestRow, ...]

    def is_monotonic(self, horizon: int | None = None) -> bool | None:
        """Whether avg forward return is non-decreasing across populated buckets.

        Returns ``None`` when fewer than two buckets have any samples at this
        horizon, since monotonicity is not a meaningful claim with a single
        data point. Empty buckets are skipped rather than treated as a
        break, since an empty bucket carries no evidence either way.
        """

        target_horizon = self.primary_horizon if horizon is None else horizon
        values = [
            bucket.avg_return[target_horizon]
            for bucket in self.buckets
            if bucket.avg_return.get(target_horizon) is not None
        ]
        if len(values) < 2:
            return None
        return all(a <= b for a, b in pairwise(values))

    def as_dict(self) -> dict[str, Any]:
        return {
            "model_version": self.model_version,
            "backtest_start": self.backtest_start,
            "backtest_end": self.backtest_end,
            "horizons": list(self.horizons),
            "primary_horizon": self.primary_horizon,
            "scored_days": self.scored_days,
            "available_days": self.available_days,
            "monotonic": {
                str(horizon): self.is_monotonic(horizon) for horizon in self.horizons
            },
            "buckets": [bucket.as_dict() for bucket in self.buckets],
        }


def _as_date(value: date | str) -> date:
    return date.fromisoformat(value) if isinstance(value, str) else value


def _latest_taiex_closes(observations: Sequence[Any]) -> list[tuple[date, float]]:
    """One close per date: the highest-priority available TAIEX revision.

    Forward returns are this backtest's ground truth, computed with full
    knowledge of the whole series (unlike the score, which only ever sees
    the past). The revision tie-break mirrors
    src.factors.contracts._observation_order (latest published_at, then
    source_revision, then retrieved_at, then payload hash) so the close used
    here always agrees with the close each day's own score was computed
    from.
    """

    best: dict[date, tuple[tuple[str, str, str, str], float]] = {}
    for observation in observations:
        if observation.dataset_id != TAIEX_DATASET_ID:
            continue
        if observation.quality_status != "available":
            continue
        raw_close = observation.values.get("close")
        if raw_close is None:
            continue
        try:
            close = float(raw_close)
        except (TypeError, ValueError):
            continue
        if not math.isfinite(close):
            continue
        day = date.fromisoformat(observation.observation_date)
        order = (
            observation.published_at or "",
            observation.source_revision or "",
            observation.retrieved_at or "",
            observation.source_payload_hash or "",
        )
        current = best.get(day)
        if current is None or order > current[0]:
            best[day] = (order, close)
    return sorted((day, payload[1]) for day, payload in best.items())


def compute_forward_returns(
    taiex_observations: Sequence[Any],
    horizons: Sequence[int] = FORWARD_RETURN_HORIZONS,
) -> dict[date, dict[int, float | None]]:
    """Realized forward TAIEX returns per signal date.

    Horizons are counted in trading days actually present in this series
    (gaps are never filled), matching backtest-spec-v0.1.md#2. A horizon
    that runs past the end of the available series is ``None`` rather than
    an extrapolated guess.
    """

    closes = _latest_taiex_closes(taiex_observations)
    result: dict[date, dict[int, float | None]] = {}
    for index, (day, close) in enumerate(closes):
        horizon_returns: dict[int, float | None] = {}
        for horizon in horizons:
            future_index = index + horizon
            if future_index < len(closes) and close != 0:
                horizon_returns[horizon] = closes[future_index][1] / close - 1
            else:
                horizon_returns[horizon] = None
        result[day] = horizon_returns
    return result


def build_score_series(
    *,
    taiex_observations: Sequence[Any],
    pcr_observations: Sequence[Any],
    tx_observations: Sequence[Any],
    vix_observations: Sequence[Any],
    institutional_observations: Sequence[Any] | None = None,
    cash_observations: Sequence[Any] | None = None,
    turnover_observations: Sequence[Any] | None = None,
    start_date: date | str,
    end_date: date | str,
    window_years: Mapping[str, int] | None = None,
) -> list[DailyScoreResult]:
    """Replay :func:`calculate_daily_score` for every TAIEX trading day in range.

    Each day's percentile history comes from only observations dated before
    that day (see the module docstring on ``as_of=None``); nothing here
    computes a percentile once over the full period and backfills it. This
    calls the same adapters and scoring functions as production, so a
    passing Layer 1 result validates the actual shipped pipeline rather than
    a parallel approximation of it. Callers should fetch enough history
    before ``start_date`` to cover both the raw warm-up (60 days for MA60)
    and the percentile window (3 years by default, 1 year for VIX); a
    shorter supply just reports more ``warm_up``/``unavailable`` days at the
    start of the range rather than failing.
    """

    start = _as_date(start_date)
    end = _as_date(end_date)
    if start > end:
        raise ValueError("start_date must not be after end_date")
    candidate_days = [
        day
        for day, _ in _latest_taiex_closes(taiex_observations)
        if start <= day <= end
    ]
    results: list[DailyScoreResult] = []
    for day in candidate_days:
        historical_values = build_historical_values(
            taiex_observations=taiex_observations,
            pcr_observations=pcr_observations,
            tx_observations=tx_observations,
            vix_observations=vix_observations,
            institutional_observations=institutional_observations,
            cash_observations=cash_observations,
            turnover_observations=turnover_observations,
            target_date=day,
            window_years=window_years,
        )
        results.append(
            calculate_daily_score(
                taiex_observations=taiex_observations,
                pcr_observations=pcr_observations,
                tx_observations=tx_observations,
                vix_observations=vix_observations,
                institutional_observations=institutional_observations,
                cash_observations=cash_observations,
                turnover_observations=turnover_observations,
                target_date=day,
                historical_values=historical_values,
            )
        )
    return results


def summarize_buckets(
    rows: Sequence[DailyBacktestRow],
    horizons: Sequence[int] = FORWARD_RETURN_HORIZONS,
) -> tuple[BucketStats, ...]:
    """Group available days by direction and summarize forward returns.

    Days without an available score (and therefore no direction) are
    excluded rather than folded into a bucket, so an unavailable day never
    silently counts as neutral.
    """

    grouped: dict[str, list[DailyBacktestRow]] = {label: [] for label in BUCKET_ORDER}
    for row in rows:
        if row.status != FACTOR_AVAILABLE or row.direction is None:
            continue
        grouped[row.direction].append(row)

    buckets = []
    for label in BUCKET_ORDER:
        members = grouped[label]
        avg: dict[int, float | None] = {}
        med: dict[int, float | None] = {}
        positive_ratio: dict[int, float | None] = {}
        for horizon in horizons:
            values = [
                value
                for member in members
                if (value := member.forward_returns.get(horizon)) is not None
            ]
            if values:
                avg[horizon] = sum(values) / len(values)
                med[horizon] = median(values)
                positive_ratio[horizon] = sum(1 for value in values if value > 0) / len(
                    values
                )
            else:
                avg[horizon] = None
                med[horizon] = None
                positive_ratio[horizon] = None
        buckets.append(
            BucketStats(
                direction=label,
                range_label=BUCKET_RANGE_LABEL[label],
                sample_count=len(members),
                avg_return=avg,
                median_return=med,
                positive_ratio=positive_ratio,
            )
        )
    return tuple(buckets)


def run_layer1_backtest(
    *,
    taiex_observations: Sequence[Any],
    pcr_observations: Sequence[Any],
    tx_observations: Sequence[Any],
    vix_observations: Sequence[Any],
    institutional_observations: Sequence[Any] | None = None,
    cash_observations: Sequence[Any] | None = None,
    turnover_observations: Sequence[Any] | None = None,
    start_date: date | str,
    end_date: date | str,
    horizons: Sequence[int] = FORWARD_RETURN_HORIZONS,
    primary_horizon: int = PRIMARY_HORIZON,
    window_years: Mapping[str, int] | None = None,
) -> Layer1Report:
    """Run the full Layer 1 replay and bucket-return summary in one call."""

    if primary_horizon not in horizons:
        raise ValueError("primary_horizon must be one of horizons")

    score_results = build_score_series(
        taiex_observations=taiex_observations,
        pcr_observations=pcr_observations,
        tx_observations=tx_observations,
        vix_observations=vix_observations,
        institutional_observations=institutional_observations,
        cash_observations=cash_observations,
        turnover_observations=turnover_observations,
        start_date=start_date,
        end_date=end_date,
        window_years=window_years,
    )
    forward_returns = compute_forward_returns(taiex_observations, horizons)

    rows = []
    for result in score_results:
        day = date.fromisoformat(result.target_date)
        day_returns = forward_returns.get(day) or {
            horizon: None for horizon in horizons
        }
        rows.append(
            DailyBacktestRow(
                target_date=result.target_date,
                status=result.status,
                score=result.score,
                direction=result.direction,
                missing_factor_ids=result.market_score.missing_factor_ids,
                forward_returns=day_returns,
            )
        )

    buckets = summarize_buckets(rows, horizons)
    available_days = sum(1 for row in rows if row.status == FACTOR_AVAILABLE)
    return Layer1Report(
        model_version=MODEL_VERSION,
        backtest_start=_as_date(start_date).isoformat(),
        backtest_end=_as_date(end_date).isoformat(),
        horizons=tuple(horizons),
        primary_horizon=primary_horizon,
        scored_days=len(rows),
        available_days=available_days,
        buckets=buckets,
        daily_rows=tuple(rows),
    )


def format_report(report: Layer1Report) -> str:
    """Render the section-9 style text table from docs/backtest-spec-v0.1.md."""

    lines = [
        f"Model version: {report.model_version}",
        f"Backtest period: {report.backtest_start} ~ {report.backtest_end}",
        f"Primary horizon: {report.primary_horizon} trading days",
        f"Scored days: {report.scored_days} (available: {report.available_days})",
        "",
    ]
    header = "Score Bucket".ljust(16) + "N".rjust(6)
    header += "".join(f"Avg {horizon}D".rjust(12) for horizon in report.horizons)
    lines.append(header)
    for bucket in report.buckets:
        row = bucket.range_label.ljust(16) + str(bucket.sample_count).rjust(6)
        for horizon in report.horizons:
            value = bucket.avg_return.get(horizon)
            text = "n/a" if value is None else f"{value * 100:+.2f}%"
            row += text.rjust(12)
        lines.append(row)

    lines.append("")
    lines.append(
        "Median".ljust(16)
        + " ".rjust(6)
        + "".join(f"Median {horizon}D".rjust(12) for horizon in report.horizons)
    )
    for bucket in report.buckets:
        row = bucket.range_label.ljust(16) + str(bucket.sample_count).rjust(6)
        for horizon in report.horizons:
            value = bucket.median_return.get(horizon)
            text = "n/a" if value is None else f"{value * 100:+.2f}%"
            row += text.rjust(12)
        lines.append(row)

    lines.append("")
    for horizon in report.horizons:
        verdict = report.is_monotonic(horizon)
        text = (
            "n/a (fewer than 2 populated buckets)"
            if verdict is None
            else ("yes" if verdict else "no")
        )
        lines.append(f"Monotonic ({horizon}D avg return, low bucket to high): {text}")

    return "\n".join(lines)


__all__ = [
    "BUCKET_ORDER",
    "BUCKET_RANGE_LABEL",
    "FORWARD_RETURN_HORIZONS",
    "PRIMARY_HORIZON",
    "BucketStats",
    "DailyBacktestRow",
    "Layer1Report",
    "build_score_series",
    "compute_forward_returns",
    "format_report",
    "run_layer1_backtest",
    "summarize_buckets",
]
