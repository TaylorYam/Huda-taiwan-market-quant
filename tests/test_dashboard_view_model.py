from __future__ import annotations

from datetime import date, timedelta
from hashlib import sha256

from src.dashboard import build_snapshot
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


def test_snapshot_is_read_only_and_exposes_unavailable_reasons() -> None:
    target = date(2026, 9, 17)
    taiex = [
        _observation(
            "twse_taiex_daily_v1",
            target - timedelta(days=offset),
            {"close": 20_000 + offset},
            "TAIEX",
        )
        for offset in range(59, -1, -1)
    ]
    result = calculate_daily_score(
        taiex_observations=taiex,
        pcr_observations=[
            _observation(
                "taifex_txo_oi_pcr_v1",
                target,
                {"put_oi": 120, "call_oi": 100},
                "PCR",
            )
        ],
        tx_observations=[
            _observation(
                "taifex_tx_daily_contract_v1",
                target,
                {"close": 20_050},
                "TX:202610:一般",
            )
        ],
        vix_observations=[
            _observation("taifex_taiwan_vix_close_v1", target, {"close": 18}, "VIX")
        ],
        target_date=target,
        historical_values={
            MOMENTUM_FACTOR_ID: [0.0, 0.01, 0.02],
            BASIS_FACTOR_ID: [-100, 0, 100],
            PCR_FACTOR_ID: [0.8, 1.0, 1.2],
            VIX_FACTOR_ID: [15, 20, 30],
        },
    )

    snapshot = build_snapshot(result)
    payload = snapshot.as_dict()

    assert snapshot.headline == "Market Score 尚不可用"
    assert payload["status"] == "unavailable"
    assert payload["factors"]
    cash_row = next(
        row for row in payload["factors"] if row["factor_id"] == "foreign_cash_5d"
    )
    assert cash_row["status"] == "unavailable"
    assert cash_row["reason"] == "foreign_cash_amount_source_contract_unresolved"
