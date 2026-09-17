"""Pure v0.1 adapters from source observations to factor inputs.

The adapters deliberately stop before scoring.  They select observations that
were available at an explicit as-of boundary, retain the source identity used
for every value, and return an explicit status when a value cannot be formed.
No adapter fills missing data with zero or with a neutral value.
"""

from __future__ import annotations

import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any, Literal

FACTOR_AVAILABLE = "available"
FACTOR_WARM_UP = "warm_up"
FACTOR_UNAVAILABLE = "unavailable"
FactorStatus = Literal["available", "warm_up", "unavailable"]

TAIEX_DATASET_ID = "twse_taiex_daily_v1"
PCR_DATASET_ID = "taifex_txo_oi_pcr_v1"
TX_DATASET_ID = "taifex_tx_daily_contract_v1"
VIX_DATASET_ID = "taifex_taiwan_vix_close_v1"
INSTITUTIONAL_FUTURES_DATASET_ID = "taifex_institutional_futures_oi_v1"
FOREIGN_CASH_DATASET_ID = "twse_foreign_cash_bfi82u_v1"
MARKET_TURNOVER_DATASET_ID = "twse_market_turnover_fmtqik_v1"

TREND_FACTOR_ID = "taiex_ma20_ma60_trend"
MOMENTUM_FACTOR_ID = "taiex_20d_momentum"
FOREIGN_CASH_FACTOR_ID = "foreign_cash_5d"
FOREIGN_TX_POSITION_FACTOR_ID = "foreign_tx_net_position"
FOREIGN_TX_CHANGE_FACTOR_ID = "foreign_tx_net_position_5d_change"
BASIS_FACTOR_ID = "tx_basis"
PCR_FACTOR_ID = "txo_oi_pcr"
VIX_FACTOR_ID = "taiwan_vix"

_TX_KEY = re.compile(r"^TX:(?P<expiry>[^:]+):(?P<session>.*)$")


@dataclass(frozen=True)
class ObservationIdentity:
    """Stable source identity carried into a derived factor result."""

    dataset_id: str
    observation_date: str
    source_record_key: str
    source_payload_hash: str | None = None
    publication_label: str | None = None
    source_revision: str | None = None
    observation_id: int | None = None


@dataclass(frozen=True)
class FactorInput:
    """A factor's point-in-time raw input, with an explicit quality state.

    ``values`` contains the named raw values needed by the scoring layer.
    ``value`` is provided for scalar factors such as momentum, PCR, basis and
    VIX; multi-value factors such as the MA trend leave it as ``None``.
    """

    factor_id: str
    observation_date: str
    status: FactorStatus
    value: float | None = None
    values: Mapping[str, float] | None = None
    observation_identities: tuple[ObservationIdentity, ...] = ()
    as_of: str | None = None
    window_start: str | None = None
    window_end: str | None = None
    reason: str | None = None

    @property
    def available(self) -> bool:
        """Whether the input can be consumed by a scoring function."""

        return self.status == FACTOR_AVAILABLE

    @property
    def observations(self) -> tuple[ObservationIdentity, ...]:
        """Compatibility alias for callers that use ``observations``."""

        return self.observation_identities


ObservationLike = Any
AsOfPolicy = Literal["observation_date", "require_published_at"]


def observation_identity(observation: ObservationLike) -> ObservationIdentity:
    """Build the source identity without depending on a storage backend."""

    return ObservationIdentity(
        dataset_id=str(_field(observation, "dataset_id")),
        observation_date=_as_date(_field(observation, "observation_date")).isoformat(),
        source_record_key=str(_field(observation, "source_record_key")),
        source_payload_hash=_optional_text(observation, "source_payload_hash"),
        publication_label=_optional_text(observation, "publication_label"),
        source_revision=_optional_text(observation, "source_revision"),
        observation_id=_optional_int(observation, "id"),
    )


def adapt_technical_inputs(
    observations: Sequence[ObservationLike],
    target_date: date | str,
    *,
    as_of: date | datetime | str | None = None,
    as_of_policy: AsOfPolicy = "observation_date",
) -> dict[str, FactorInput]:
    """Adapt TAIEX closes into the MA trend and 20-day momentum inputs."""

    target = _as_date(target_date)
    selected = _daily_observations(
        observations,
        dataset_id=TAIEX_DATASET_ID,
        target_date=target,
        as_of=as_of,
        as_of_policy=as_of_policy,
    )
    series = sorted(selected.items(), key=lambda item: item[0])
    by_factor: dict[str, FactorInput] = {}
    if not any(observation_date == target for observation_date, _ in series):
        reason = _missing_reason(observations, TAIEX_DATASET_ID, target, as_of)
        by_factor[TREND_FACTOR_ID] = _unavailable(
            TREND_FACTOR_ID, target, as_of, reason
        )
        by_factor[MOMENTUM_FACTOR_ID] = _unavailable(
            MOMENTUM_FACTOR_ID, target, as_of, reason
        )
        return by_factor

    closes: list[tuple[date, float, ObservationLike]] = []
    for observation_date, observation in series:
        close = _number(observation, "close")
        if close is not None:
            closes.append((observation_date, close, observation))
    if not any(observation_date == target for observation_date, _, _ in closes):
        reason = "target_close_unavailable"
        by_factor[TREND_FACTOR_ID] = _unavailable(
            TREND_FACTOR_ID, target, as_of, reason
        )
        by_factor[MOMENTUM_FACTOR_ID] = _unavailable(
            MOMENTUM_FACTOR_ID, target, as_of, reason
        )
        return by_factor

    target_index = next(index for index, row in enumerate(closes) if row[0] == target)
    target_close = closes[target_index][1]
    trend_rows = closes[: target_index + 1]
    trend_identities = tuple(observation_identity(row[2]) for row in trend_rows[-60:])
    if len(trend_rows) < 60:
        by_factor[TREND_FACTOR_ID] = _warm_up(
            TREND_FACTOR_ID,
            target,
            as_of,
            reason="requires_60_available_TAIEX_closes_for_MA60",
            identities=trend_identities,
            window_start=trend_rows[0][0] if trend_rows else None,
        )
    else:
        ma20 = sum(row[1] for row in trend_rows[-20:]) / 20
        ma60 = sum(row[1] for row in trend_rows[-60:]) / 60
        by_factor[TREND_FACTOR_ID] = FactorInput(
            factor_id=TREND_FACTOR_ID,
            observation_date=target.isoformat(),
            status=FACTOR_AVAILABLE,
            values={"close": target_close, "ma20": ma20, "ma60": ma60},
            observation_identities=trend_identities,
            as_of=_as_of_text(as_of),
            window_start=trend_rows[-60][0].isoformat(),
            window_end=target.isoformat(),
        )

    momentum_rows = trend_rows
    momentum_identities = tuple(
        observation_identity(row[2]) for row in momentum_rows[-21:]
    )
    if len(momentum_rows) < 21:
        by_factor[MOMENTUM_FACTOR_ID] = _warm_up(
            MOMENTUM_FACTOR_ID,
            target,
            as_of,
            reason="requires_21_available_TAIEX_closes_for_20d_return",
            identities=momentum_identities,
            window_start=momentum_rows[0][0] if momentum_rows else None,
        )
    else:
        start_close = momentum_rows[-21][1]
        by_factor[MOMENTUM_FACTOR_ID] = FactorInput(
            factor_id=MOMENTUM_FACTOR_ID,
            observation_date=target.isoformat(),
            status=FACTOR_AVAILABLE,
            value=target_close / start_close - 1,
            values={"close": target_close, "close_20d_prior": start_close},
            observation_identities=momentum_identities,
            as_of=_as_of_text(as_of),
            window_start=momentum_rows[-21][0].isoformat(),
            window_end=target.isoformat(),
        )
    return by_factor


def adapt_pcr_input(
    observations: Sequence[ObservationLike],
    target_date: date | str,
    *,
    as_of: date | datetime | str | None = None,
    as_of_policy: AsOfPolicy = "observation_date",
) -> FactorInput:
    """Adapt TAIFEX TXO open-interest data into the OI PCR input."""

    target = _as_date(target_date)
    selected = _daily_observations(
        observations,
        dataset_id=PCR_DATASET_ID,
        target_date=target,
        as_of=as_of,
        as_of_policy=as_of_policy,
    )
    observation = selected.get(target)
    if observation is None:
        return _unavailable(
            PCR_FACTOR_ID,
            target,
            as_of,
            _missing_reason(observations, PCR_DATASET_ID, target, as_of),
        )
    put_oi = _number(observation, "put_oi")
    call_oi = _number(observation, "call_oi")
    identity = (observation_identity(observation),)
    if put_oi is None or call_oi is None:
        return _unavailable(
            PCR_FACTOR_ID, target, as_of, "put_oi_or_call_oi_unavailable", identity
        )
    if call_oi == 0:
        return _unavailable(PCR_FACTOR_ID, target, as_of, "call_oi_zero", identity)
    return FactorInput(
        factor_id=PCR_FACTOR_ID,
        observation_date=target.isoformat(),
        status=FACTOR_AVAILABLE,
        value=put_oi / call_oi,
        values={"put_oi": put_oi, "call_oi": call_oi, "oi_pcr": put_oi / call_oi},
        observation_identities=identity,
        as_of=_as_of_text(as_of),
        window_start=target.isoformat(),
        window_end=target.isoformat(),
    )


def adapt_tx_inputs(
    tx_observations: Sequence[ObservationLike],
    taiex_observations: Sequence[ObservationLike],
    target_date: date | str,
    *,
    institutional_observations: Sequence[ObservationLike] | None = None,
    as_of: date | datetime | str | None = None,
    as_of_policy: AsOfPolicy = "observation_date",
) -> dict[str, FactorInput]:
    """Adapt TX and TAIEX observations into basis and explicit OI states.

    The current free source contract does not contain an investor-level TX OI
    observation.  The two foreign-position factors therefore stay unavailable
    and never derive a value from the aggregate contract OI column.
    """

    target = _as_date(target_date)
    tx_selected = _daily_observations(
        tx_observations,
        dataset_id=TX_DATASET_ID,
        target_date=target,
        as_of=as_of,
        as_of_policy=as_of_policy,
    )
    spot_selected = _daily_observations(
        taiex_observations,
        dataset_id=TAIEX_DATASET_ID,
        target_date=target,
        as_of=as_of,
        as_of_policy=as_of_policy,
    )
    if institutional_observations:
        result = _adapt_institutional_futures_inputs(
            institutional_observations,
            target,
            as_of=as_of,
            as_of_policy=as_of_policy,
        )
    else:
        result = {
            FOREIGN_TX_POSITION_FACTOR_ID: _unavailable(
                FOREIGN_TX_POSITION_FACTOR_ID,
                target,
                as_of,
                "foreign_investor_TX_OI_source_unavailable",
            ),
            FOREIGN_TX_CHANGE_FACTOR_ID: _unavailable(
                FOREIGN_TX_CHANGE_FACTOR_ID,
                target,
                as_of,
                "foreign_investor_TX_OI_source_unavailable",
            ),
        }
    tx_observation = _select_front_tx(tx_selected, target)
    spot_observation = spot_selected.get(target)
    tx_close = _number(tx_observation, "close") if tx_observation else None
    spot_close = _number(spot_observation, "close") if spot_observation else None
    if tx_observation is None or spot_observation is None:
        reason = "TX_or_TAIEX_close_unavailable"
        result[BASIS_FACTOR_ID] = _unavailable(BASIS_FACTOR_ID, target, as_of, reason)
    elif tx_close is None or spot_close is None:
        result[BASIS_FACTOR_ID] = _unavailable(
            BASIS_FACTOR_ID, target, as_of, "TX_or_TAIEX_close_unavailable"
        )
    else:
        basis = tx_close - spot_close
        result[BASIS_FACTOR_ID] = FactorInput(
            factor_id=BASIS_FACTOR_ID,
            observation_date=target.isoformat(),
            status=FACTOR_AVAILABLE,
            value=basis,
            values={"tx_close": tx_close, "taiex_close": spot_close, "basis": basis},
            observation_identities=(
                observation_identity(tx_observation),
                observation_identity(spot_observation),
            ),
            as_of=_as_of_text(as_of),
            window_start=target.isoformat(),
            window_end=target.isoformat(),
        )
    return result


def adapt_vix_input(
    observations: Sequence[ObservationLike],
    target_date: date | str,
    *,
    as_of: date | datetime | str | None = None,
    as_of_policy: AsOfPolicy = "observation_date",
) -> FactorInput:
    """Adapt the official daily Taiwan VIX close into a scalar input."""

    target = _as_date(target_date)
    selected = _daily_observations(
        observations,
        dataset_id=VIX_DATASET_ID,
        target_date=target,
        as_of=as_of,
        as_of_policy=as_of_policy,
    )
    observation = selected.get(target)
    if observation is None:
        return _unavailable(
            VIX_FACTOR_ID,
            target,
            as_of,
            _missing_reason(observations, VIX_DATASET_ID, target, as_of),
        )
    close = _number(observation, "close")
    identity = (observation_identity(observation),)
    if close is None:
        return _unavailable(
            VIX_FACTOR_ID, target, as_of, "vix_close_unavailable", identity
        )
    return FactorInput(
        factor_id=VIX_FACTOR_ID,
        observation_date=target.isoformat(),
        status=FACTOR_AVAILABLE,
        value=close,
        values={"close": close},
        observation_identities=identity,
        as_of=_as_of_text(as_of),
        window_start=target.isoformat(),
        window_end=target.isoformat(),
    )


def adapt_foreign_cash_input(
    cash_observations: Sequence[ObservationLike],
    turnover_observations: Sequence[ObservationLike],
    target_date: date | str,
    *,
    as_of: date | datetime | str | None = None,
    as_of_policy: AsOfPolicy = "observation_date",
) -> FactorInput:
    """Adapt BFI82U foreign net buy/sell and FMTQIK turnover into a 5-day ratio.

    ``foreign5d = sum(foreign net buy/sell over the last 5 available BFI82U
    dates) / sum(FMTQIK turnover for those same 5 dates)``. Both series must
    have a value for every one of those 5 dates; a gap on either side leaves
    the factor unavailable rather than computing the ratio over a shorter or
    misaligned window. Callers are expected to only supply BFI82U
    observations on or after ``FOREIGN_CASH_VERIFIED_START``
    (src/data/twse_foreign_cash.py); this adapter does not re-check that
    date itself, since it is enforced where the data is collected.
    """

    target = _as_date(target_date)
    cash_selected = _daily_observations(
        cash_observations,
        dataset_id=FOREIGN_CASH_DATASET_ID,
        target_date=target,
        as_of=as_of,
        as_of_policy=as_of_policy,
    )
    turnover_selected = _daily_observations(
        turnover_observations,
        dataset_id=MARKET_TURNOVER_DATASET_ID,
        target_date=target,
        as_of=as_of,
        as_of_policy=as_of_policy,
    )
    cash_rows = sorted(cash_selected.items(), key=lambda item: item[0])
    if not cash_rows or cash_rows[-1][0] != target:
        reason = _missing_reason(
            cash_observations, FOREIGN_CASH_DATASET_ID, target, as_of
        )
        return _unavailable(FOREIGN_CASH_FACTOR_ID, target, as_of, reason)

    window = cash_rows[-5:]
    if len(window) < 5:
        return _warm_up(
            FOREIGN_CASH_FACTOR_ID,
            target,
            as_of,
            reason="requires_5_available_foreign_cash_observations",
            identities=tuple(observation_identity(row) for _, row in window),
            window_start=window[0][0] if window else None,
        )

    net_total = 0.0
    turnover_total = 0.0
    identities: list[ObservationIdentity] = []
    for day, cash_row in window:
        net = _number(cash_row, "net_buy_sell")
        turnover_row = turnover_selected.get(day)
        turnover = (
            _number(turnover_row, "turnover") if turnover_row is not None else None
        )
        if net is None or turnover_row is None or turnover is None:
            identities.append(observation_identity(cash_row))
            if turnover_row is not None:
                identities.append(observation_identity(turnover_row))
            return _unavailable(
                FOREIGN_CASH_FACTOR_ID,
                target,
                as_of,
                "foreign_cash_or_market_turnover_unavailable_for_window_date",
                tuple(identities),
            )
        net_total += net
        turnover_total += turnover
        identities.append(observation_identity(cash_row))
        identities.append(observation_identity(turnover_row))

    if turnover_total == 0:
        return _unavailable(
            FOREIGN_CASH_FACTOR_ID,
            target,
            as_of,
            "market_5d_turnover_zero",
            tuple(identities),
        )
    ratio = net_total / turnover_total
    return FactorInput(
        factor_id=FOREIGN_CASH_FACTOR_ID,
        observation_date=target.isoformat(),
        status=FACTOR_AVAILABLE,
        value=ratio,
        values={
            "foreign_5d_net": net_total,
            "market_5d_turnover": turnover_total,
            "ratio": ratio,
        },
        observation_identities=tuple(identities),
        as_of=_as_of_text(as_of),
        window_start=window[0][0].isoformat(),
        window_end=target.isoformat(),
    )


def adapt_v01_inputs(
    *,
    taiex_observations: Sequence[ObservationLike],
    pcr_observations: Sequence[ObservationLike],
    tx_observations: Sequence[ObservationLike],
    vix_observations: Sequence[ObservationLike],
    institutional_observations: Sequence[ObservationLike] | None = None,
    cash_observations: Sequence[ObservationLike] | None = None,
    turnover_observations: Sequence[ObservationLike] | None = None,
    target_date: date | str,
    as_of: date | datetime | str | None = None,
    as_of_policy: AsOfPolicy = "observation_date",
) -> dict[str, FactorInput]:
    """Build the available-source v0.1 inputs in one deterministic mapping."""

    result = adapt_technical_inputs(
        taiex_observations,
        target_date,
        as_of=as_of,
        as_of_policy=as_of_policy,
    )
    result.update(
        {
            PCR_FACTOR_ID: adapt_pcr_input(
                pcr_observations,
                target_date,
                as_of=as_of,
                as_of_policy=as_of_policy,
            ),
            VIX_FACTOR_ID: adapt_vix_input(
                vix_observations,
                target_date,
                as_of=as_of,
                as_of_policy=as_of_policy,
            ),
        }
    )
    result.update(
        adapt_tx_inputs(
            tx_observations,
            taiex_observations,
            target_date,
            institutional_observations=institutional_observations,
            as_of=as_of,
            as_of_policy=as_of_policy,
        )
    )
    if cash_observations and turnover_observations:
        result[FOREIGN_CASH_FACTOR_ID] = adapt_foreign_cash_input(
            cash_observations,
            turnover_observations,
            target_date,
            as_of=as_of,
            as_of_policy=as_of_policy,
        )
    else:
        result[FOREIGN_CASH_FACTOR_ID] = _unavailable(
            FOREIGN_CASH_FACTOR_ID,
            _as_date(target_date),
            as_of,
            "foreign_cash_amount_source_contract_unresolved",
        )
    return result


# Short aliases keep the contract pleasant to use from a factor pipeline.
adapt_technical = adapt_technical_inputs
adapt_pcr = adapt_pcr_input
adapt_tx = adapt_tx_inputs
adapt_vix = adapt_vix_input
adapt_foreign_cash = adapt_foreign_cash_input


def _field(observation: ObservationLike, name: str) -> Any:
    if isinstance(observation, Mapping):
        return observation[name]
    return getattr(observation, name)


def _optional_text(observation: ObservationLike, name: str) -> str | None:
    try:
        value = _field(observation, name)
    except (AttributeError, KeyError):
        return None
    return str(value) if value is not None else None


def _optional_int(observation: ObservationLike, name: str) -> int | None:
    try:
        value = _field(observation, name)
    except (AttributeError, KeyError):
        return None
    return int(value) if value is not None else None


def _as_date(value: date | datetime | str) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(value)
    except ValueError:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date()


def _as_of_datetime(value: date | datetime | str) -> datetime | None:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value
    if isinstance(value, date):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)


def _as_of_text(value: date | datetime | str | None) -> str | None:
    if value is None:
        return None
    return value.isoformat() if isinstance(value, (date, datetime)) else value


def _number(observation: ObservationLike | None, name: str) -> float | None:
    if observation is None:
        return None
    try:
        values = _field(observation, "values")
        value = values[name]
        number = float(value)
    except (AttributeError, KeyError, TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _daily_observations(
    observations: Sequence[ObservationLike],
    *,
    dataset_id: str,
    target_date: date,
    as_of: date | datetime | str | None,
    as_of_policy: AsOfPolicy,
) -> dict[date, ObservationLike]:
    if as_of_policy not in {"observation_date", "require_published_at"}:
        raise ValueError("unsupported as_of_policy")
    as_of_date = _as_date(as_of) if as_of is not None else None
    as_of_timestamp = _as_of_datetime(as_of) if as_of is not None else None
    candidates: dict[date, list[ObservationLike]] = {}
    for observation in observations:
        try:
            if str(_field(observation, "dataset_id")) != dataset_id:
                continue
            observation_date = _as_date(_field(observation, "observation_date"))
            if observation_date > target_date:
                continue
            if str(_field(observation, "quality_status")) != "available":
                continue
        except (AttributeError, KeyError, TypeError, ValueError):
            continue
        if as_of_date is not None and observation_date > as_of_date:
            continue
        published_at = _optional_text(observation, "published_at")
        if as_of_timestamp is not None:
            if published_at is None:
                if as_of_policy == "require_published_at":
                    continue
            else:
                published = _as_of_datetime(published_at)
                if published is None or published > as_of_timestamp:
                    continue
        elif as_of_policy == "require_published_at" and published_at is None:
            continue
        candidates.setdefault(observation_date, []).append(observation)

    selected: dict[date, ObservationLike] = {}
    for observation_date, rows in candidates.items():
        selected[observation_date] = max(rows, key=_observation_order)
    return selected


def _observation_order(observation: ObservationLike) -> tuple[str, str, str, str]:
    return (
        _optional_text(observation, "published_at") or "",
        _optional_text(observation, "source_revision") or "",
        _optional_text(observation, "retrieved_at") or "",
        _optional_text(observation, "source_payload_hash") or "",
    )


def _select_front_tx(
    selected: Mapping[date, ObservationLike], target_date: date
) -> ObservationLike | None:
    rows = [
        observation
        for observation_date, observation in selected.items()
        if observation_date == target_date
    ]
    parsed: list[tuple[tuple[int, int, int, str], ObservationLike]] = []
    for observation in rows:
        key = _optional_text(observation, "source_record_key") or ""
        match = _TX_KEY.match(key)
        if match is None or match.group("session") not in {"一般", "<missing>", ""}:
            continue
        expiry = match.group("expiry")
        digits = re.sub(r"[^0-9]", "", expiry)
        if len(digits) < 6:
            continue
        year, month = int(digits[:4]), int(digits[4:6])
        period = year * 12 + month
        target_period = target_date.year * 12 + target_date.month
        if period < target_period:
            continue
        parsed.append(((period, len(digits), len(expiry), expiry), observation))
    if not parsed:
        return None
    return min(parsed, key=lambda row: row[0])[1]


def _adapt_institutional_futures_inputs(
    observations: Sequence[ObservationLike],
    target: date,
    *,
    as_of: date | datetime | str | None,
    as_of_policy: AsOfPolicy,
) -> dict[str, FactorInput]:
    """Build foreign TX OI and its five-trading-day change when available."""

    selected = _daily_observations(
        observations,
        dataset_id=INSTITUTIONAL_FUTURES_DATASET_ID,
        target_date=target,
        as_of=as_of,
        as_of_policy=as_of_policy,
    )
    rows = sorted(selected.items(), key=lambda item: item[0])
    latest = selected.get(target)
    if latest is None:
        reason = _missing_reason(
            observations, INSTITUTIONAL_FUTURES_DATASET_ID, target, as_of
        )
        return {
            FOREIGN_TX_POSITION_FACTOR_ID: _unavailable(
                FOREIGN_TX_POSITION_FACTOR_ID, target, as_of, reason
            ),
            FOREIGN_TX_CHANGE_FACTOR_ID: _unavailable(
                FOREIGN_TX_CHANGE_FACTOR_ID, target, as_of, reason
            ),
        }
    net = _number(latest, "open_interest_net")
    identity = (observation_identity(latest),)
    if net is None:
        unavailable = "foreign_TX_OI_net_unavailable"
        return {
            FOREIGN_TX_POSITION_FACTOR_ID: _unavailable(
                FOREIGN_TX_POSITION_FACTOR_ID, target, as_of, unavailable, identity
            ),
            FOREIGN_TX_CHANGE_FACTOR_ID: _unavailable(
                FOREIGN_TX_CHANGE_FACTOR_ID, target, as_of, unavailable, identity
            ),
        }

    position = FactorInput(
        factor_id=FOREIGN_TX_POSITION_FACTOR_ID,
        observation_date=target.isoformat(),
        status=FACTOR_AVAILABLE,
        value=net,
        values={"open_interest_net": net},
        observation_identities=identity,
        as_of=_as_of_text(as_of),
        window_start=target.isoformat(),
        window_end=target.isoformat(),
    )
    if len(rows) < 6:
        change = _warm_up(
            FOREIGN_TX_CHANGE_FACTOR_ID,
            target,
            as_of,
            reason="requires_6_available_foreign_TX_OI_observations",
            identities=tuple(observation_identity(row) for _, row in rows),
            window_start=rows[0][0] if rows else None,
        )
    else:
        prior_date, prior = rows[-6]
        prior_net = _number(prior, "open_interest_net")
        if prior_net is None:
            change = _unavailable(
                FOREIGN_TX_CHANGE_FACTOR_ID,
                target,
                as_of,
                "foreign_TX_OI_prior_net_unavailable",
                tuple(observation_identity(row) for _, row in rows[-6:]),
            )
        else:
            change = FactorInput(
                factor_id=FOREIGN_TX_CHANGE_FACTOR_ID,
                observation_date=target.isoformat(),
                status=FACTOR_AVAILABLE,
                value=net - prior_net,
                values={"current_net": net, "prior_net": prior_net},
                observation_identities=tuple(
                    observation_identity(row) for _, row in rows[-6:]
                ),
                as_of=_as_of_text(as_of),
                window_start=prior_date.isoformat(),
                window_end=target.isoformat(),
            )
    return {
        FOREIGN_TX_POSITION_FACTOR_ID: position,
        FOREIGN_TX_CHANGE_FACTOR_ID: change,
    }


def _missing_reason(
    observations: Sequence[ObservationLike],
    dataset_id: str,
    target_date: date,
    as_of: date | datetime | str | None,
) -> str:
    dates = []
    for observation in observations:
        try:
            if str(_field(observation, "dataset_id")) == dataset_id:
                dates.append(_as_date(_field(observation, "observation_date")))
        except (AttributeError, KeyError, TypeError, ValueError):
            continue
    if dates and max(dates) < target_date:
        return "target_date_missing"
    if as_of is not None and _as_date(as_of) < target_date:
        return "target_date_after_as_of"
    return "observation_unavailable"


def _unavailable(
    factor_id: str,
    target_date: date,
    as_of: date | datetime | str | None,
    reason: str,
    identities: tuple[ObservationIdentity, ...] = (),
) -> FactorInput:
    return FactorInput(
        factor_id=factor_id,
        observation_date=target_date.isoformat(),
        status=FACTOR_UNAVAILABLE,
        observation_identities=identities,
        as_of=_as_of_text(as_of),
        reason=reason,
    )


def _warm_up(
    factor_id: str,
    target_date: date,
    as_of: date | datetime | str | None,
    *,
    reason: str,
    identities: tuple[ObservationIdentity, ...],
    window_start: date | None,
) -> FactorInput:
    return FactorInput(
        factor_id=factor_id,
        observation_date=target_date.isoformat(),
        status=FACTOR_WARM_UP,
        observation_identities=identities,
        as_of=_as_of_text(as_of),
        window_start=window_start.isoformat() if window_start else None,
        window_end=target_date.isoformat(),
        reason=reason,
    )


__all__ = [
    "BASIS_FACTOR_ID",
    "FACTOR_AVAILABLE",
    "FACTOR_UNAVAILABLE",
    "FACTOR_WARM_UP",
    "FOREIGN_CASH_DATASET_ID",
    "FOREIGN_CASH_FACTOR_ID",
    "FOREIGN_TX_CHANGE_FACTOR_ID",
    "FOREIGN_TX_POSITION_FACTOR_ID",
    "INSTITUTIONAL_FUTURES_DATASET_ID",
    "MARKET_TURNOVER_DATASET_ID",
    "MOMENTUM_FACTOR_ID",
    "PCR_FACTOR_ID",
    "TREND_FACTOR_ID",
    "VIX_FACTOR_ID",
    "AsOfPolicy",
    "FactorInput",
    "FactorStatus",
    "ObservationIdentity",
    "adapt_foreign_cash",
    "adapt_foreign_cash_input",
    "adapt_pcr",
    "adapt_pcr_input",
    "adapt_technical",
    "adapt_technical_inputs",
    "adapt_tx",
    "adapt_tx_inputs",
    "adapt_v01_inputs",
    "adapt_vix",
    "adapt_vix_input",
    "observation_identity",
]
