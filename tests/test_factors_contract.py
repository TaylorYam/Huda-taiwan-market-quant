from datetime import date

from src.data.storage import Observation
from src.factors.contracts import (
    BASIS_FACTOR_ID,
    FACTOR_AVAILABLE,
    FACTOR_UNAVAILABLE,
    FACTOR_WARM_UP,
    FOREIGN_CASH_FACTOR_ID,
    FOREIGN_TX_POSITION_FACTOR_ID,
    MOMENTUM_FACTOR_ID,
    PCR_FACTOR_ID,
    TREND_FACTOR_ID,
    VIX_FACTOR_ID,
    adapt_pcr_input,
    adapt_technical_inputs,
    adapt_tx_inputs,
    adapt_v01_inputs,
    adapt_vix_input,
)


def make_observation(
    dataset_id: str,
    observation_date: date,
    values: dict[str, float],
    *,
    source_record_key: str = "record",
    quality_status: str = "available",
    published_at: str | None = None,
    source_revision: str | None = None,
) -> Observation:
    return Observation(
        dataset_id=dataset_id,
        schema_version="0.1",
        observation_date=observation_date.isoformat(),
        source_date=observation_date.isoformat(),
        source_name="TWSE" if dataset_id.startswith("twse") else "TAIFEX",
        source_url="https://official.example/observation",
        source_record_key=source_record_key,
        retrieved_at="2026-09-17T00:00:00+00:00",
        ingested_at="2026-09-17T00:00:00+00:00",
        source_payload_hash=("a" * 63) + str(observation_date.day % 10),
        parser_version="test@0.1",
        values=values,
        quality_status=quality_status,
        published_at=published_at,
        source_revision=source_revision,
    )


def test_technical_inputs_warm_up_then_calculate_and_keep_identity() -> None:
    observations = [
        make_observation("twse_taiex_daily_v1", date(2026, 1, 1), {"close": 100})
    ]
    warm = adapt_technical_inputs(observations, date(2026, 1, 1))
    assert warm[TREND_FACTOR_ID].status == FACTOR_WARM_UP
    assert warm[MOMENTUM_FACTOR_ID].status == FACTOR_WARM_UP

    observations = [
        make_observation(
            "twse_taiex_daily_v1",
            date(2026, 1, 1).fromordinal(date(2026, 1, 1).toordinal() + index),
            {"close": 100 + index},
        )
        for index in range(60)
    ]
    result = adapt_technical_inputs(observations, date(2026, 3, 2))
    assert result[TREND_FACTOR_ID].status == FACTOR_UNAVAILABLE
    assert result[TREND_FACTOR_ID].reason == "target_date_missing"

    target = observations[-1].observation_date
    result = adapt_technical_inputs(observations, target)
    trend = result[TREND_FACTOR_ID]
    momentum = result[MOMENTUM_FACTOR_ID]
    assert trend.status == FACTOR_AVAILABLE
    assert trend.values is not None
    assert trend.values["ma20"] == 149.5
    assert trend.values["ma60"] == 129.5
    assert momentum.value == (159 / 139) - 1
    assert len(trend.observation_identities) == 60
    assert trend.observation_identities[-1].source_record_key == "record"


def test_as_of_excludes_published_future_without_filling_value() -> None:
    observation = make_observation(
        "taifex_taiwan_vix_close_v1",
        date(2026, 9, 17),
        {"close": 20},
        published_at="2026-09-17T15:00:00+08:00",
    )
    result = adapt_vix_input(
        [observation],
        date(2026, 9, 17),
        as_of="2026-09-17T14:00:00+08:00",
    )
    assert result.status == FACTOR_UNAVAILABLE
    assert result.value is None


def test_pcr_zero_call_oi_is_unavailable_and_source_empty_is_unavailable() -> None:
    zero = make_observation(
        "taifex_txo_oi_pcr_v1",
        date(2026, 9, 17),
        {"put_oi": 10, "call_oi": 0},
    )
    result = adapt_pcr_input([zero], date(2026, 9, 17))
    assert result.status == FACTOR_UNAVAILABLE
    assert result.reason == "call_oi_zero"

    empty = make_observation(
        "taifex_txo_oi_pcr_v1",
        date(2026, 9, 17),
        {},
        quality_status="source_empty",
    )
    assert adapt_pcr_input([empty], date(2026, 9, 17)).status == FACTOR_UNAVAILABLE


def test_tx_basis_uses_nearest_general_contract_and_keeps_foreign_oi_unavailable() -> (
    None
):
    target = date(2026, 9, 17)
    tx = [
        make_observation(
            "taifex_tx_daily_contract_v1",
            target,
            {"close": 22_100},
            source_record_key="TX:202610:一般",
        ),
        make_observation(
            "taifex_tx_daily_contract_v1",
            target,
            {"close": 22_300},
            source_record_key="TX:202609:一般",
        ),
        make_observation(
            "taifex_tx_daily_contract_v1",
            target,
            {"close": 22_050},
            source_record_key="TX:202610:盤後",
        ),
    ]
    spot = [make_observation("twse_taiex_daily_v1", target, {"close": 22_000})]
    result = adapt_tx_inputs(tx, spot, target)
    assert result[BASIS_FACTOR_ID].status == FACTOR_AVAILABLE
    assert result[BASIS_FACTOR_ID].value == 100
    assert result[FOREIGN_TX_POSITION_FACTOR_ID].status == FACTOR_UNAVAILABLE
    assert result[FOREIGN_TX_POSITION_FACTOR_ID].value is None
    assert "source_unavailable" in (result[FOREIGN_TX_POSITION_FACTOR_ID].reason or "")


def test_v01_inputs_keep_blocked_cash_factor_unavailable() -> None:
    target = date(2026, 9, 17)
    result = adapt_v01_inputs(
        taiex_observations=[],
        pcr_observations=[],
        tx_observations=[],
        vix_observations=[],
        target_date=target,
    )
    assert result[FOREIGN_CASH_FACTOR_ID].status == FACTOR_UNAVAILABLE
    assert result[PCR_FACTOR_ID].status == FACTOR_UNAVAILABLE
    assert result[VIX_FACTOR_ID].status == FACTOR_UNAVAILABLE
