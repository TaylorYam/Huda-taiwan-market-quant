from __future__ import annotations

from datetime import date, timedelta

from src.data import Observation
from src.factors.contracts import (
    FACTOR_AVAILABLE,
    FOREIGN_TX_CHANGE_FACTOR_ID,
    FOREIGN_TX_POSITION_FACTOR_ID,
    adapt_tx_inputs,
)


def observation(day: date, net: float) -> Observation:
    return Observation(
        dataset_id="taifex_institutional_futures_oi_v1",
        schema_version="0.1",
        observation_date=day.isoformat(),
        source_date=day.strftime("%Y%m%d"),
        source_name="TAIFEX",
        source_url="https://openapi.taifex.com.tw/v1/example",
        source_record_key="TX:foreign:institutional",
        retrieved_at="2026-09-17T00:00:00+00:00",
        ingested_at="2026-09-17T00:00:00+00:00",
        source_payload_hash=(f"{day.toordinal():064x}"),
        parser_version="test@0.1",
        values={"open_interest_net": net},
        quality_status="available",
    )


def test_foreign_tx_oi_factors_use_daily_snapshot_and_five_day_change() -> None:
    target = date(2026, 9, 17)
    institutional = [
        observation(target - timedelta(days=offset), -80_000 + (5 - offset) * 1_000)
        for offset in range(5, -1, -1)
    ]

    result = adapt_tx_inputs(
        tx_observations=[],
        taiex_observations=[],
        institutional_observations=institutional,
        target_date=target,
    )

    assert result[FOREIGN_TX_POSITION_FACTOR_ID].status == FACTOR_AVAILABLE
    assert result[FOREIGN_TX_POSITION_FACTOR_ID].value == -75_000
    assert result[FOREIGN_TX_CHANGE_FACTOR_ID].status == FACTOR_AVAILABLE
    assert result[FOREIGN_TX_CHANGE_FACTOR_ID].value == 5_000
    assert len(result[FOREIGN_TX_CHANGE_FACTOR_ID].observation_identities) == 6
