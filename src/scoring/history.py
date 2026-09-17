"""Point-in-time historical value series for percentile-based v0.1 factors.

Builds each factor's ``historical_values`` sample by replaying the same
point-in-time factor adapters used for the target date, once per candidate
date inside that factor's comparison window. Reusing the adapters means a
historical point is excluded by the exact same as-of and warm-up rules that
would apply if that date were itself being scored today, so this cannot
introduce a lookahead violation the adapters do not already guard against.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date, datetime
from typing import Any

from src.factors.contracts import (
    BASIS_FACTOR_ID,
    FACTOR_AVAILABLE,
    FOREIGN_TX_CHANGE_FACTOR_ID,
    FOREIGN_TX_POSITION_FACTOR_ID,
    MOMENTUM_FACTOR_ID,
    PCR_FACTOR_ID,
    VIX_FACTOR_ID,
    AsOfPolicy,
    FactorInput,
    adapt_pcr_input,
    adapt_technical_inputs,
    adapt_tx_inputs,
    adapt_vix_input,
    observation_identity,
)

# v0.1 initial assumption from docs/factor-model-v0.1.md's historical
# comparison window section: 3 years for most percentile-based factors, 1
# year for VIX. Explicitly not yet confirmed by backtest; expected to change
# once Phase 3 validates score discrimination against these window lengths.
DEFAULT_WINDOW_YEARS: Mapping[str, int] = {
    MOMENTUM_FACTOR_ID: 3,
    FOREIGN_TX_POSITION_FACTOR_ID: 3,
    FOREIGN_TX_CHANGE_FACTOR_ID: 3,
    BASIS_FACTOR_ID: 3,
    PCR_FACTOR_ID: 3,
    VIX_FACTOR_ID: 1,
}


def build_historical_values(
    *,
    taiex_observations: Sequence[Any],
    pcr_observations: Sequence[Any],
    tx_observations: Sequence[Any],
    vix_observations: Sequence[Any],
    institutional_observations: Sequence[Any] | None = None,
    target_date: date | str,
    as_of: date | datetime | str | None = None,
    as_of_policy: AsOfPolicy = "observation_date",
    window_years: Mapping[str, int] | None = None,
) -> dict[str, list[float]]:
    """Replay each percentile factor's adapter over its trailing window.

    Only dates strictly before ``target_date`` are used, so today's own
    value is never part of its own comparison sample. A factor id is present
    in the result only if at least one historical point was available; a
    factor with zero eligible points is omitted rather than mapped to an
    empty list, so the scoring layer reports the same
    ``scalar_factor_requires_normalized_score`` reason it would for a caller
    that passed no history at all, instead of a separate empty-sample error.

    This replays four adapters once per candidate date. For a 3-year window
    that is roughly 750 trading dates, each rescanning the full observation
    sequences passed in; correctness over the daily runner's data volumes
    was prioritized over avoiding that repeated scan.
    """

    target = _as_date(target_date)
    windows = {**DEFAULT_WINDOW_YEARS, **(window_years or {})}
    earliest_start = _years_before(target, max(windows.values()))

    candidate_dates = sorted(
        {
            candidate
            for group in (
                taiex_observations,
                pcr_observations,
                tx_observations,
                vix_observations,
                institutional_observations or (),
            )
            for observation in group
            if earliest_start <= (candidate := _observation_date(observation)) < target
        }
    )

    history: dict[str, list[float]] = {}
    for candidate in candidate_dates:
        technical = adapt_technical_inputs(
            taiex_observations, candidate, as_of=as_of, as_of_policy=as_of_policy
        )
        _record(history, technical.get(MOMENTUM_FACTOR_ID), candidate, target, windows)
        _record(
            history,
            adapt_pcr_input(
                pcr_observations, candidate, as_of=as_of, as_of_policy=as_of_policy
            ),
            candidate,
            target,
            windows,
        )
        _record(
            history,
            adapt_vix_input(
                vix_observations, candidate, as_of=as_of, as_of_policy=as_of_policy
            ),
            candidate,
            target,
            windows,
        )
        tx_inputs = adapt_tx_inputs(
            tx_observations,
            taiex_observations,
            candidate,
            institutional_observations=institutional_observations,
            as_of=as_of,
            as_of_policy=as_of_policy,
        )
        for factor_id in (
            BASIS_FACTOR_ID,
            FOREIGN_TX_POSITION_FACTOR_ID,
            FOREIGN_TX_CHANGE_FACTOR_ID,
        ):
            _record(history, tx_inputs.get(factor_id), candidate, target, windows)

    return history


def _record(
    history: dict[str, list[float]],
    factor_input: FactorInput | None,
    candidate: date,
    target: date,
    windows: Mapping[str, int],
) -> None:
    if (
        factor_input is None
        or factor_input.status != FACTOR_AVAILABLE
        or factor_input.value is None
    ):
        return
    window_start = _years_before(target, windows.get(factor_input.factor_id, 3))
    if candidate < window_start:
        return
    history.setdefault(factor_input.factor_id, []).append(factor_input.value)


def _as_date(value: date | datetime | str) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(value)


def _years_before(value: date, years: int) -> date:
    try:
        return value.replace(year=value.year - years)
    except ValueError:
        # value is Feb 29 on a leap year; that many years back is never one.
        return value.replace(month=2, day=28, year=value.year - years)


def _observation_date(observation: Any) -> date:
    return date.fromisoformat(observation_identity(observation).observation_date)


__all__ = ["DEFAULT_WINDOW_YEARS", "build_historical_values"]
