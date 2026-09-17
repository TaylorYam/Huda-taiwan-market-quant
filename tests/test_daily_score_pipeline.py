from __future__ import annotations

from datetime import date, timedelta
from hashlib import sha256

from src.data.storage import Observation
from src.factors.contracts import (
    BASIS_FACTOR_ID,
    MOMENTUM_FACTOR_ID,
    PCR_FACTOR_ID,
    VIX_FACTOR_ID,
)
from src.scoring import calculate_daily_score


def _observation(
    dataset_id: str, day: date, values: dict[str, float], key: str
) -> Observation:
    return Observation(
        dataset_id=dataset_id,
        schema_version="0.1",
        observation_date=day.isoformat(),
        source_date=day.isoformat(),
        source_name="TWSE" if dataset_id.startswith("twse") else "TAIFEX",
        source_url="https://official.example/observation",
        source_record_key=key,
        retrieved_at="2026-09-17T00:00:00+00:00",
        ingested_at="2026-09-17T00:00:00+00:00",
        source_payload_hash=sha256(
            f"{dataset_id}|{day.isoformat()}|{key}".encode()
        ).hexdigest(),
        parser_version="test@0.1",
        values=values,
        quality_status="available",
    )


def _source_observations(
    target: date,
) -> tuple[list[Observation], list[Observation], list[Observation], list[Observation]]:
    taiex = [
        _observation(
            "twse_taiex_daily_v1",
            target - timedelta(days=offset),
            {"close": 20_000 + offset},
            "TAIEX",
        )
        for offset in range(59, -1, -1)
    ]
    pcr = [
        _observation(
            "taifex_txo_oi_pcr_v1", target, {"put_oi": 120, "call_oi": 100}, "PCR"
        )
    ]
    tx = [
        _observation(
            "taifex_tx_daily_contract_v1", target, {"close": 20_050}, "TX:202610:一般"
        )
    ]
    vix = [_observation("taifex_taiwan_vix_close_v1", target, {"close": 18}, "VIX")]
    return taiex, pcr, tx, vix


def test_daily_score_is_unavailable_until_blocked_sources_are_available() -> None:
    target = date(2026, 9, 17)
    taiex, pcr, tx, vix = _source_observations(target)

    result = calculate_daily_score(
        taiex_observations=taiex,
        pcr_observations=pcr,
        tx_observations=tx,
        vix_observations=vix,
        target_date=target,
        historical_values={
            MOMENTUM_FACTOR_ID: [0.0, 0.01, 0.02],
            BASIS_FACTOR_ID: [-100, 0, 100],
            PCR_FACTOR_ID: [0.8, 1.0, 1.2],
            VIX_FACTOR_ID: [15, 20, 30],
        },
    )

    assert result.status == "unavailable"
    assert result.score is None
    assert "foreign_cash_5d" in result.market_score.missing_factor_ids
    assert "foreign_tx_net_position" in result.market_score.missing_factor_ids
    assert result.factor_inputs[BASIS_FACTOR_ID].available
    assert result.factor_scores[BASIS_FACTOR_ID].available


def test_daily_score_report_preserves_as_of_and_source_identity() -> None:
    target = date(2026, 9, 17)
    taiex, pcr, tx, vix = _source_observations(target)
    result = calculate_daily_score(
        taiex_observations=taiex,
        pcr_observations=pcr,
        tx_observations=tx,
        vix_observations=vix,
        target_date=target,
        as_of="2026-09-17T14:00:00+08:00",
        historical_values={
            MOMENTUM_FACTOR_ID: [0.0, 0.01, 0.02],
            BASIS_FACTOR_ID: [-100, 0, 100],
            PCR_FACTOR_ID: [0.8, 1.0, 1.2],
            VIX_FACTOR_ID: [15, 20, 30],
        },
    )

    payload = result.as_dict()
    assert payload["as_of"] == "2026-09-17T14:00:00+08:00"
    assert payload["factors"][BASIS_FACTOR_ID]["observation_identities"]
    assert payload["factors"][VIX_FACTOR_ID]["score_status"] == "available"
