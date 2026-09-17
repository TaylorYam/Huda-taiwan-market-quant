from __future__ import annotations

from dataclasses import replace
from datetime import date, timedelta

import pytest
from test_scoring_history import _dense_fixtures, _observation

from src.backtest.layer1 import (
    BUCKET_RANGE_LABEL,
    PRIMARY_HORIZON,
    BucketStats,
    DailyBacktestRow,
    Layer1Report,
    build_score_series,
    compute_forward_returns,
    format_report,
    run_layer1_backtest,
    summarize_buckets,
)
from src.factors.contracts import FACTOR_AVAILABLE, TAIEX_DATASET_ID
from src.scoring.contracts import BEAR, BULL, NEUTRAL, STRONG_BEAR, STRONG_BULL

BUCKET_ORDER = (STRONG_BEAR, BEAR, NEUTRAL, BULL, STRONG_BULL)
END = date(2026, 9, 17)


def _cash_and_turnover(target: date, span_days: int) -> tuple[list, list]:
    cash = [
        _observation(
            "twse_foreign_cash_bfi82u_v1",
            target - timedelta(days=offset),
            {"net_buy_sell": -1000.0 + offset, "category": "外資及陸資"},
            "BFI82U:foreign",
        )
        for offset in range(span_days, -1, -1)
    ]
    turnover = [
        _observation(
            "twse_market_turnover_fmtqik_v1",
            target - timedelta(days=offset),
            {"turnover": 100_000.0},
            "FMTQIK:market",
        )
        for offset in range(span_days, -1, -1)
    ]
    return cash, turnover


# --- compute_forward_returns ------------------------------------------------


def test_forward_returns_use_trading_day_offsets_present_in_the_series() -> None:
    start = date(2026, 1, 1)
    taiex = [
        _observation(
            TAIEX_DATASET_ID, start + timedelta(days=i), {"close": 100.0 + i}, "TAIEX"
        )
        for i in range(30)
    ]

    forward = compute_forward_returns(taiex, horizons=(1, 2, 5))

    day0 = forward[start]
    assert day0[1] == pytest.approx(101.0 / 100.0 - 1)
    assert day0[2] == pytest.approx(102.0 / 100.0 - 1)
    assert day0[5] == pytest.approx(105.0 / 100.0 - 1)

    # Index 24 (close=124) is the last day whose +5 horizon still lands on
    # index 29 (close=129), the final row in this 30-day series.
    day24 = forward[start + timedelta(days=24)]
    assert day24[5] == pytest.approx(129.0 / 124.0 - 1)

    # Index 25 no longer has a +5 partner but still has +1 and +2.
    day25 = forward[start + timedelta(days=25)]
    assert day25[5] is None
    assert day25[1] is not None

    last_day = forward[start + timedelta(days=29)]
    assert last_day == {1: None, 2: None, 5: None}


def test_forward_returns_pick_the_latest_revision_per_date() -> None:
    day = date(2026, 1, 5)
    stale = _observation(TAIEX_DATASET_ID, day, {"close": 999.0}, "TAIEX")
    fresh = replace(
        _observation(TAIEX_DATASET_ID, day, {"close": 100.0}, "TAIEX"),
        published_at="2026-01-06T00:00:00+00:00",
    )
    following = _observation(
        TAIEX_DATASET_ID, day + timedelta(days=1), {"close": 110.0}, "TAIEX"
    )

    forward = compute_forward_returns([stale, fresh, following], horizons=(1,))

    assert forward[day][1] == pytest.approx(110.0 / 100.0 - 1)


def test_forward_returns_ignore_non_taiex_and_unavailable_rows() -> None:
    day = date(2026, 1, 5)
    other_dataset = replace(
        _observation(TAIEX_DATASET_ID, day, {"close": 1.0}, "TAIEX"),
        dataset_id="taifex_txo_oi_pcr_v1",
    )
    bad_quality = replace(
        _observation(TAIEX_DATASET_ID, day, {"close": 2.0}, "TAIEX"),
        quality_status="pending",
    )

    forward = compute_forward_returns([other_dataset, bad_quality], horizons=(1,))

    assert forward == {}


# --- Layer1Report.is_monotonic ----------------------------------------------


def _report_from_avg_returns(
    values: list[float | None], horizon: int = PRIMARY_HORIZON
) -> Layer1Report:
    buckets = tuple(
        BucketStats(
            direction=label,
            range_label=BUCKET_RANGE_LABEL[label],
            sample_count=0 if value is None else 1,
            avg_return={horizon: value},
            median_return={horizon: value},
            positive_ratio={horizon: None},
        )
        for label, value in zip(BUCKET_ORDER, values)
    )
    return Layer1Report(
        model_version="v0.1",
        backtest_start="2020-01-01",
        backtest_end="2020-12-31",
        horizons=(horizon,),
        primary_horizon=horizon,
        scored_days=sum(bucket.sample_count for bucket in buckets),
        available_days=sum(bucket.sample_count for bucket in buckets),
        buckets=buckets,
        daily_rows=(),
    )


def test_is_monotonic_true_for_the_specs_own_illustrative_example() -> None:
    # docs/backtest-spec-v0.1.md#2's worked example: strictly increasing avg
    # 10-day return from the lowest to the highest score bucket.
    report = _report_from_avg_returns([-0.030, -0.012, 0.001, 0.013, 0.028])
    assert report.is_monotonic() is True


def test_is_monotonic_false_when_the_order_breaks() -> None:
    report = _report_from_avg_returns([-0.030, 0.005, 0.001, 0.013, 0.028])
    assert report.is_monotonic() is False


def test_is_monotonic_none_with_fewer_than_two_populated_buckets() -> None:
    report = _report_from_avg_returns([None, None, 0.001, None, None])
    assert report.is_monotonic() is None


# --- summarize_buckets -------------------------------------------------------


def test_summarize_buckets_excludes_unavailable_days_from_every_bucket() -> None:
    rows = [
        DailyBacktestRow(
            "2026-01-01", FACTOR_AVAILABLE, 15.0, STRONG_BEAR, (), {10: -0.05}
        ),
        DailyBacktestRow(
            "2026-01-02", "unavailable", None, None, ("taiwan_vix",), {10: None}
        ),
        DailyBacktestRow(
            "2026-01-03", FACTOR_AVAILABLE, 90.0, STRONG_BULL, (), {10: 0.05}
        ),
    ]

    buckets = {bucket.direction: bucket for bucket in summarize_buckets(rows, (10,))}

    assert sum(bucket.sample_count for bucket in buckets.values()) == 2
    assert buckets[STRONG_BEAR].sample_count == 1
    assert buckets[STRONG_BULL].sample_count == 1
    assert buckets[NEUTRAL].sample_count == 0
    assert buckets[NEUTRAL].avg_return[10] is None


def test_summarize_buckets_computes_avg_median_and_positive_ratio() -> None:
    rows = [
        DailyBacktestRow(
            f"2026-01-{i + 1:02d}", FACTOR_AVAILABLE, 70.0, BULL, (), {10: value}
        )
        for i, value in enumerate([0.01, 0.02, 0.03, 0.10])
    ]

    bull = next(b for b in summarize_buckets(rows, (10,)) if b.direction == BULL)

    assert bull.sample_count == 4
    assert bull.avg_return[10] == pytest.approx(0.04)
    assert bull.median_return[10] == pytest.approx(0.025)
    assert bull.positive_ratio[10] == pytest.approx(1.0)


# --- End-to-end replay --------------------------------------------------------


def _full_fixture(span_days: int):
    taiex, pcr, tx, institutional = _dense_fixtures(END, span_days)
    vix = [
        _observation(
            "taifex_taiwan_vix_close_v1",
            END - timedelta(days=offset),
            {"close": 15 + offset * 0.01},
            "VIX",
        )
        for offset in range(span_days, -1, -1)
    ]
    cash, turnover = _cash_and_turnover(END, span_days)
    return taiex, pcr, tx, vix, institutional, cash, turnover


def test_build_score_series_scores_every_taiex_day_and_clears_all_8_factors() -> None:
    taiex, pcr, tx, vix, institutional, cash, turnover = _full_fixture(span_days=100)
    start = END - timedelta(days=20)

    results = build_score_series(
        taiex_observations=taiex,
        pcr_observations=pcr,
        tx_observations=tx,
        vix_observations=vix,
        institutional_observations=institutional,
        cash_observations=cash,
        turnover_observations=turnover,
        start_date=start,
        end_date=END,
    )

    assert [row.target_date for row in results] == [
        (start + timedelta(days=i)).isoformat() for i in range(21)
    ]
    # 80 days of fixture history before `start` clears every raw warm-up
    # (60 days for MA60) and gives each percentile factor dozens of points.
    assert all(result.status == FACTOR_AVAILABLE for result in results)
    assert all(not result.market_score.missing_factor_ids for result in results)


def test_run_layer1_backtest_buckets_every_available_day_exactly_once() -> None:
    taiex, pcr, tx, vix, institutional, cash, turnover = _full_fixture(span_days=100)
    start = END - timedelta(days=20)

    report = run_layer1_backtest(
        taiex_observations=taiex,
        pcr_observations=pcr,
        tx_observations=tx,
        vix_observations=vix,
        institutional_observations=institutional,
        cash_observations=cash,
        turnover_observations=turnover,
        start_date=start,
        end_date=END,
    )

    assert report.scored_days == 21
    assert report.available_days == 21
    assert sum(bucket.sample_count for bucket in report.buckets) == 21

    # The TAIEX fixture ends exactly at END, so the final backtest day has no
    # future close left for any horizon...
    last_row = report.daily_rows[-1]
    assert last_row.target_date == END.isoformat()
    assert all(value is None for value in last_row.forward_returns.values())
    # ...while the earliest day (20 trading days before END) exactly fits the
    # 20-day horizon using the fixture's own final close.
    first_row = report.daily_rows[0]
    assert first_row.target_date == start.isoformat()
    assert first_row.forward_returns[20] is not None

    text = format_report(report)
    assert "Model version: v0.1" in text
    assert f"Backtest period: {start.isoformat()} ~ {END.isoformat()}" in text

    payload = report.as_dict()
    assert payload["scored_days"] == 21
    assert set(payload["monotonic"]) == {"5", "10", "20"}


def test_run_layer1_backtest_rejects_a_primary_horizon_outside_the_horizon_list() -> (
    None
):
    taiex, pcr, tx, vix, institutional, cash, turnover = _full_fixture(span_days=100)
    start = END - timedelta(days=20)

    with pytest.raises(ValueError):
        run_layer1_backtest(
            taiex_observations=taiex,
            pcr_observations=pcr,
            tx_observations=tx,
            vix_observations=vix,
            institutional_observations=institutional,
            cash_observations=cash,
            turnover_observations=turnover,
            start_date=start,
            end_date=END,
            horizons=(5, 10),
            primary_horizon=20,
        )
