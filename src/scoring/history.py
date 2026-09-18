"""Point-in-time historical value series for percentile-based v0.1 factors.

Builds each factor's ``historical_values`` sample by replaying the same
point-in-time factor adapters used for the target date, once per candidate
date inside that factor's comparison window. Reusing the adapters means a
historical point is excluded by the same as-of and warm-up rules that would
apply if that date were itself being scored today. The shared observation
envelope is filtered first, so retrieval and ingestion that happened after the
selected knowledge boundary cannot introduce lookahead.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date, datetime
from typing import Any

from src.factors.contracts import (
    BASIS_FACTOR_ID,
    FACTOR_AVAILABLE,
    FOREIGN_CASH_FACTOR_ID,
    FOREIGN_TX_CHANGE_FACTOR_ID,
    FOREIGN_TX_POSITION_FACTOR_ID,
    MOMENTUM_FACTOR_ID,
    PCR_FACTOR_ID,
    VIX_FACTOR_ID,
    AsOfPolicy,
    FactorInput,
    adapt_foreign_cash_input,
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
    FOREIGN_CASH_FACTOR_ID: 3,
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
    cash_observations: Sequence[Any] | None = None,
    turnover_observations: Sequence[Any] | None = None,
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
    if any(
        isinstance(years, bool) or not isinstance(years, int) or years < 1
        for years in windows.values()
    ):
        raise ValueError("window_years values must be positive integers")

    # The daily runner already applies this filter after the Supabase read.
    # Keep the invariant here as well because this function is also a public
    # replay boundary and callers may pass observations loaded elsewhere.
    as_of_timestamp = _as_of_timestamp(as_of)
    as_of_date = _as_date(as_of) if as_of is not None else None
    taiex_observations = _known_observations(
        taiex_observations, as_of_date=as_of_date, as_of_timestamp=as_of_timestamp
    )
    pcr_observations = _known_observations(
        pcr_observations, as_of_date=as_of_date, as_of_timestamp=as_of_timestamp
    )
    tx_observations = _known_observations(
        tx_observations, as_of_date=as_of_date, as_of_timestamp=as_of_timestamp
    )
    vix_observations = _known_observations(
        vix_observations, as_of_date=as_of_date, as_of_timestamp=as_of_timestamp
    )
    institutional_observations = (
        _known_observations(
            institutional_observations,
            as_of_date=as_of_date,
            as_of_timestamp=as_of_timestamp,
        )
        if institutional_observations is not None
        else None
    )
    cash_observations = (
        _known_observations(
            cash_observations,
            as_of_date=as_of_date,
            as_of_timestamp=as_of_timestamp,
        )
        if cash_observations is not None
        else None
    )
    turnover_observations = (
        _known_observations(
            turnover_observations,
            as_of_date=as_of_date,
            as_of_timestamp=as_of_timestamp,
        )
        if turnover_observations is not None
        else None
    )
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
                cash_observations or (),
                turnover_observations or (),
            )
            for observation in group
            if earliest_start <= (candidate := _observation_date(observation)) < target
        }
    )
    has_cash_sources = bool(cash_observations) and bool(turnover_observations)

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

        if has_cash_sources:
            _record(
                history,
                adapt_foreign_cash_input(
                    cash_observations,
                    turnover_observations,
                    candidate,
                    as_of=as_of,
                    as_of_policy=as_of_policy,
                ),
                candidate,
                target,
                windows,
            )

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
    try:
        return date.fromisoformat(value)
    except ValueError:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date()


def _as_of_timestamp(value: date | datetime | str | None) -> datetime | None:
    """Parse an optional knowledge-boundary timestamp.

    A date has no time-of-day boundary and is handled by ``_as_date``. A
    timestamp must carry an offset so a replay cannot silently depend on the
    host machine's local timezone.
    """

    if value is None or isinstance(value, date) and not isinstance(value, datetime):
        return None
    if isinstance(value, str):
        try:
            date.fromisoformat(value)
        except ValueError:
            pass
        else:
            return None
    parsed = (
        value
        if isinstance(value, datetime)
        else datetime.fromisoformat(value.replace("Z", "+00:00"))
    )
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("as_of must include a timezone")
    return parsed


def _known_observations(
    observations: Sequence[Any],
    *,
    as_of_date: date | None,
    as_of_timestamp: datetime | None,
) -> tuple[Any, ...]:
    """Retain rows whose complete evidence envelope was known at ``as_of``."""

    if as_of_date is None and as_of_timestamp is None:
        return tuple(observations)

    known: list[Any] = []
    for observation in observations:
        try:
            observation_date = _observation_date(observation)
            if as_of_date is not None and observation_date > as_of_date:
                continue
            if as_of_timestamp is not None:
                retrieved_at = _timestamp_field(observation, "retrieved_at")
                ingested_at = _timestamp_field(observation, "ingested_at")
                if (
                    retrieved_at is None
                    or ingested_at is None
                    or retrieved_at > as_of_timestamp
                    or ingested_at > as_of_timestamp
                ):
                    continue
                published_at = _timestamp_field(observation, "published_at")
                if published_at is not None and published_at > as_of_timestamp:
                    continue
        except (AttributeError, KeyError, TypeError, ValueError):
            # A malformed envelope cannot be proven to be known at the
            # boundary. Excluding it keeps it from contributing a lookahead
            # value; the daily runner's source-level validation still reports
            # malformed rows as a failed run.
            continue
        known.append(observation)
    return tuple(known)


def _timestamp_field(observation: Any, field_name: str) -> datetime | None:
    value = (
        observation.get(field_name)
        if isinstance(observation, Mapping)
        else getattr(observation, field_name)
    )
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a timestamp string")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{field_name} must include a timezone")
    return parsed


def _years_before(value: date, years: int) -> date:
    try:
        return value.replace(year=value.year - years)
    except ValueError:
        # value is Feb 29 on a leap year; that many years back is never one.
        return value.replace(month=2, day=28, year=value.year - years)


def _observation_date(observation: Any) -> date:
    return date.fromisoformat(observation_identity(observation).observation_date)


__all__ = ["DEFAULT_WINDOW_YEARS", "build_historical_values"]
