from __future__ import annotations

from datetime import date, timedelta
from hashlib import sha256

from src.data.storage import Observation
from src.factors.contracts import (
    BASIS_FACTOR_ID,
    FOREIGN_CASH_FACTOR_ID,
    FOREIGN_TX_CHANGE_FACTOR_ID,
    FOREIGN_TX_POSITION_FACTOR_ID,
    MOMENTUM_FACTOR_ID,
    PCR_FACTOR_ID,
    VIX_FACTOR_ID,
)
from src.scoring.history import build_historical_values

TARGET = date(2026, 9, 17)


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


def _dense_fixtures(
    target: date, span_days: int
) -> tuple[list[Observation], list[Observation], list[Observation], list[Observation]]:
    """40+ consecutive daily rows so momentum/basis/position/change warm up."""

    taiex = [
        _observation(
            "twse_taiex_daily_v1",
            target - timedelta(days=offset),
            {"close": 20_000 + (span_days - offset)},
            "TAIEX",
        )
        for offset in range(span_days, -1, -1)
    ]
    pcr = [
        _observation(
            "taifex_txo_oi_pcr_v1",
            target - timedelta(days=offset),
            {"put_oi": 100 + offset, "call_oi": 100},
            "PCR",
        )
        for offset in range(span_days, -1, -1)
    ]
    tx = [
        _observation(
            "taifex_tx_daily_contract_v1",
            target - timedelta(days=offset),
            {"close": 20_050 + (span_days - offset)},
            "TX:202612:一般",
        )
        for offset in range(span_days, -1, -1)
    ]
    institutional = [
        _observation(
            "taifex_institutional_futures_oi_v1",
            target - timedelta(days=offset),
            {"open_interest_net": -1000 + offset},
            "TX:foreign:institutional",
        )
        for offset in range(span_days, -1, -1)
    ]
    return taiex, pcr, tx, institutional


def test_builds_history_from_dense_recent_window() -> None:
    taiex, pcr, tx, institutional = _dense_fixtures(TARGET, span_days=40)
    vix = [
        _observation(
            "taifex_taiwan_vix_close_v1",
            TARGET - timedelta(days=offset),
            {"close": 15 + offset * 0.1},
            "VIX",
        )
        for offset in range(40, -1, -1)
    ]

    history = build_historical_values(
        taiex_observations=taiex,
        pcr_observations=pcr,
        tx_observations=tx,
        vix_observations=vix,
        institutional_observations=institutional,
        target_date=TARGET,
    )

    # Momentum needs 21 trailing closes, so only later candidate dates
    # (the 20 closest to target, each with >=21 closes behind it) qualify.
    assert len(history[MOMENTUM_FACTOR_ID]) == 20
    assert len(history[PCR_FACTOR_ID]) == 40
    assert len(history[VIX_FACTOR_ID]) == 40
    assert len(history[BASIS_FACTOR_ID]) == 40
    assert len(history[FOREIGN_TX_POSITION_FACTOR_ID]) == 40
    # Foreign TX change needs 6 trailing institutional observations.
    assert len(history[FOREIGN_TX_CHANGE_FACTOR_ID]) == 35


def test_excludes_target_date_itself() -> None:
    taiex, pcr, tx, institutional = _dense_fixtures(TARGET, span_days=25)
    vix = [
        _observation(
            "taifex_taiwan_vix_close_v1",
            TARGET - timedelta(days=offset),
            {"close": 20},
            "VIX",
        )
        for offset in range(25, -1, -1)
    ]

    history = build_historical_values(
        taiex_observations=taiex,
        pcr_observations=pcr,
        tx_observations=tx,
        vix_observations=vix,
        institutional_observations=institutional,
        target_date=TARGET,
    )

    # 26 rows (offset 25..0) minus the target date itself (offset 0).
    assert len(history[PCR_FACTOR_ID]) == 25


def test_vix_uses_a_shorter_window_than_the_other_factors() -> None:
    taiex, pcr, tx, institutional = _dense_fixtures(TARGET, span_days=25)
    old_day = TARGET - timedelta(days=730)  # ~2 years back: inside 3y, outside 1y.
    pcr = [
        *pcr,
        _observation(
            "taifex_txo_oi_pcr_v1", old_day, {"put_oi": 999, "call_oi": 333}, "PCR"
        ),
    ]
    vix = [
        _observation(
            "taifex_taiwan_vix_close_v1",
            TARGET - timedelta(days=offset),
            {"close": 20},
            "VIX",
        )
        for offset in range(25, -1, -1)
    ]
    vix.append(
        _observation("taifex_taiwan_vix_close_v1", old_day, {"close": 987.0}, "VIX")
    )

    history = build_historical_values(
        taiex_observations=taiex,
        pcr_observations=pcr,
        tx_observations=tx,
        vix_observations=vix,
        institutional_observations=institutional,
        target_date=TARGET,
    )

    assert 999 / 333 in history[PCR_FACTOR_ID]
    assert 987.0 not in history[VIX_FACTOR_ID]


def test_foreign_cash_history_requires_both_sources_and_a_full_5day_window() -> None:
    taiex, pcr, tx, institutional = _dense_fixtures(TARGET, span_days=25)
    vix = [
        _observation(
            "taifex_taiwan_vix_close_v1",
            TARGET - timedelta(days=offset),
            {"close": 20},
            "VIX",
        )
        for offset in range(25, -1, -1)
    ]
    cash = [
        _observation(
            "twse_foreign_cash_bfi82u_v1",
            TARGET - timedelta(days=offset),
            {"net_buy_sell": -1000.0, "category": "外資及陸資"},
            "BFI82U:foreign",
        )
        for offset in range(25, -1, -1)
    ]
    turnover = [
        _observation(
            "twse_market_turnover_fmtqik_v1",
            TARGET - timedelta(days=offset),
            {"turnover": 100_000.0},
            "FMTQIK:market",
        )
        for offset in range(25, -1, -1)
    ]

    without_cash = build_historical_values(
        taiex_observations=taiex,
        pcr_observations=pcr,
        tx_observations=tx,
        vix_observations=vix,
        institutional_observations=institutional,
        target_date=TARGET,
    )
    assert FOREIGN_CASH_FACTOR_ID not in without_cash

    with_cash = build_historical_values(
        taiex_observations=taiex,
        pcr_observations=pcr,
        tx_observations=tx,
        vix_observations=vix,
        institutional_observations=institutional,
        cash_observations=cash,
        turnover_observations=turnover,
        target_date=TARGET,
    )
    # 25 candidate dates, minus the first 4 which cannot form a full 5-day
    # trailing window yet (warm-up), leaves 21 available points.
    assert len(with_cash[FOREIGN_CASH_FACTOR_ID]) == 21


def test_omits_factor_ids_with_zero_available_points() -> None:
    history = build_historical_values(
        taiex_observations=[],
        pcr_observations=[],
        tx_observations=[],
        vix_observations=[],
        target_date=TARGET,
    )

    assert history == {}


def test_respects_as_of_boundary_like_the_live_adapters() -> None:
    taiex, pcr, tx, institutional = _dense_fixtures(TARGET, span_days=25)
    as_of = "2026-09-16T12:00:00+00:00"
    # This date sits outside the dense 25-day fixture, so it cannot be
    # shadowed by another row for the same date; only the publish-time
    # check below should decide whether it is visible.
    isolated_day = TARGET - timedelta(days=100)
    late_published = Observation(
        dataset_id="taifex_txo_oi_pcr_v1",
        schema_version="0.1",
        observation_date=isolated_day.isoformat(),
        source_date=isolated_day.isoformat(),
        source_name="TAIFEX",
        source_url="https://official.example/observation",
        source_record_key="PCR",
        retrieved_at="2026-09-17T00:00:00+00:00",
        ingested_at="2026-09-17T00:00:00+00:00",
        published_at="2026-09-16T13:00:00+00:00",  # 1 hour after as_of
        source_payload_hash="late",
        parser_version="test@0.1",
        values={"put_oi": 500, "call_oi": 100},  # ratio 5.0, distinctive
        quality_status="available",
    )
    vix = [
        _observation(
            "taifex_taiwan_vix_close_v1",
            TARGET - timedelta(days=offset),
            {"close": 20},
            "VIX",
        )
        for offset in range(25, -1, -1)
    ]

    history = build_historical_values(
        taiex_observations=taiex,
        pcr_observations=[*pcr, late_published],
        tx_observations=tx,
        vix_observations=vix,
        institutional_observations=institutional,
        target_date=TARGET,
        as_of=as_of,
    )

    assert 5.0 not in history[PCR_FACTOR_ID]
