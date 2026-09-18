from copy import deepcopy
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from src.dashboard.app import (
    SOURCE_DATASETS,
    build_tradingview_kline_html,
    display_score,
    factor_history_frame,
    factor_rows,
    score_history_frame,
    taiex_ohlc_frame,
)


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_SECRET_KEY", raising=False)


def run_app(
    monkeypatch,
    record=None,
    error=None,
    source=None,
    score_history=None,
    taiex_history=None,
):
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SECRET_KEY", "sb_secret_never_render_this")
    store = MagicMock()
    store.__enter__.return_value = store
    store.get_latest_market_score.return_value = record
    store.get_latest_source_quality.return_value = source
    store.get_market_score_history.return_value = score_history or []
    store.get_observation_history.return_value = taiex_history or []
    if error:
        store.get_latest_market_score.side_effect = error
    with patch("src.dashboard.app.DashboardDataStore", return_value=store):
        app = AppTest.from_file("streamlit_app.py", default_timeout=30).run()
    assert not app.exception
    return app, store


def test_missing_credentials_do_not_connect():
    with patch("src.dashboard.app.DashboardDataStore") as factory:
        app = AppTest.from_file("streamlit_app.py", default_timeout=30).run()
    assert not app.exception
    assert "尚未設定" in app.error[0].value
    factory.assert_not_called()


def test_empty_score_still_displays_source_quality(monkeypatch):
    app, store = run_app(monkeypatch)
    assert "empty" in app.info[0].value
    assert len(app.dataframe[0].value) == 7
    assert set(app.dataframe[0].value["品質狀態"]) == {"empty"}
    assert store.get_latest_source_quality.call_count == 7


def test_source_failure_state_and_timestamp_are_displayed(monkeypatch):
    app, _ = run_app(
        monkeypatch,
        source={
            "observation_date": "2026-09-16",
            "source_record_key": "test-record",
            "quality_status": "invalid",
            "quality_notes": "missing_close",
            "last_retrieved_at": "2026-09-17T08:30:00Z",
        },
    )
    assert set(app.dataframe[0].value["品質狀態"]) == {"invalid"}
    assert set(app.dataframe[0].value["品質說明"]) == {"missing_close"}
    assert "2026-09-17T08:30:00+00:00" in " ".join(t.value for t in app.text)


@pytest.mark.parametrize(
    "url",
    [
        "http://example.supabase.co",
        "https://[bad",
        "https://example.supabase.co:not-a-port",
        "https://user:pass@example.supabase.co",
    ],
)
def test_invalid_url_is_rejected_without_connection(monkeypatch, url):
    monkeypatch.setenv("SUPABASE_URL", url)
    monkeypatch.setenv("SUPABASE_SECRET_KEY", "sb_secret_never_render_this")
    with patch("src.dashboard.app.DashboardDataStore") as factory:
        app = AppTest.from_file("streamlit_app.py", default_timeout=30).run()
    assert not app.exception
    assert "設定錯誤" in app.error[0].value
    factory.assert_not_called()


@pytest.mark.parametrize("status,score", [("available", 72), ("unavailable", None)])
def test_persisted_result_and_metadata(monkeypatch, status, score):
    record = {
        "status": status,
        "score": score,
        "direction": "偏多" if score else None,
        "target_date": "2026-09-17",
        "as_of": "2026-09-17T08:00:00+00:00",
        "created_at": "2026-09-17T08:05:00+00:00",
        "model_version": "v0.1",
        "reason": "missing_required" if score is None else None,
        "factor_scores_json": {
            "taiex_ma20_ma60_trend": {
                "status": "available",
                "score": 75,
                "reason": None,
            }
        },
    }
    before = deepcopy(record)
    app, _ = run_app(monkeypatch, record)
    assert app.metric[0].value == ("72.0 / 100" if score else "unavailable")
    assert len(app.dataframe[0].value) == 8
    assert "2026-09-17T08:05" in " ".join(t.value for t in app.text)
    assert "2026-09-17T08:00" in " ".join(t.value for t in app.text)
    assert record == before


def test_api_error_is_sanitized_and_quality_remains_visible(monkeypatch):
    app, _ = run_app(monkeypatch, error=RuntimeError("sb_secret_never_render_this"))
    assert "無法讀取 Market Score" in app.error[0].value
    assert "sb_secret_never_render_this" not in str(app)
    assert len(app.dataframe) == 1


def test_connection_error_is_sanitized(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SECRET_KEY", "sb_secret_never_render_this")
    with patch(
        "src.dashboard.app.DashboardDataStore",
        side_effect=RuntimeError("sb_secret_never_render_this"),
    ):
        app = AppTest.from_file("streamlit_app.py", default_timeout=30).run()
    assert not app.exception
    assert "資料連線失敗" in app.error[0].value
    assert "sb_secret_never_render_this" not in str(app)


@pytest.mark.parametrize(
    "value,status",
    [
        (50, "unavailable"),
        (None, "available"),
        (float("nan"), "available"),
        (101, "available"),
    ],
)
def test_invalid_scores_are_not_neutral(value, status):
    assert display_score(value, status) == "unavailable"


def test_absent_factors_are_explicitly_unavailable():
    rows = factor_rows({"factor_scores_json": {}})
    assert len(rows) == 8
    assert all(row["分數"] == "unavailable" for row in rows)


def test_malformed_factor_payload_is_visible_as_unavailable():
    rows = factor_rows(
        {
            "factor_scores_json": {
                "taiex_ma20_ma60_trend": ["unexpected", "payload"],
            }
        }
    )
    row = next(row for row in rows if row["因子"] == "TAIEX 均線趨勢")
    assert row["狀態"] == "unavailable"
    assert row["分數"] == "unavailable"
    assert row["原因"] == "資料格式錯誤"


def test_malformed_source_timestamp_does_not_hide_quality_table(monkeypatch):
    app, _ = run_app(
        monkeypatch,
        source={
            "observation_date": "2026-09-17",
            "quality_status": "available",
            "last_retrieved_at": "not-a-timestamp",
        },
    )
    assert len(app.dataframe) == 1
    assert app.dataframe[0].value.iloc[0]["最後擷取時間"] == "格式錯誤"


def test_score_history_does_not_turn_unavailable_into_zero():
    frame = score_history_frame(
        [
            {"target_date": "2026-09-16", "status": "available", "score": 68},
            {"target_date": "2026-09-17", "status": "unavailable", "score": None},
        ]
    )
    assert frame.loc[0, "Market Score"] == 68.0
    assert pd.isna(frame.loc[1, "Market Score"])
    assert frame["狀態"].tolist() == ["available", "unavailable"]


def test_display_scores_use_one_decimal_place():
    assert display_score(72.34, "available") == "72.3 / 100"
    assert display_score(72, "available") == "72.0 / 100"


def test_taiex_ohlc_frame_keeps_only_complete_available_rows():
    frame = taiex_ohlc_frame(
        [
            {
                "id": 1,
                "observation_date": "2026-09-16",
                "quality_status": "available",
                "values_json": {"open": 1, "high": 3, "low": 0.5, "close": 2},
            },
            {
                "id": 2,
                "observation_date": "2026-09-17",
                "quality_status": "invalid",
                "values_json": {"open": 2, "high": 4, "low": 1, "close": 3},
            },
            {
                "id": 3,
                "observation_date": "2026-09-18",
                "quality_status": "available",
                "values_json": {"open": 2, "high": 4, "low": 1},
            },
        ]
    )
    assert frame["日期"].tolist() == ["2026-09-16"]
    assert frame[["open", "high", "low", "close"]].iloc[0].tolist() == [
        1.0,
        3.0,
        0.5,
        2.0,
    ]


def test_factor_history_leaves_unavailable_factor_cells_missing():
    frame = factor_history_frame(
        [
            {
                "target_date": "2026-09-17",
                "factor_scores_json": {
                    "taiex_ma20_ma60_trend": {
                        "status": "available",
                        "score": 75,
                    },
                    "taiex_20d_momentum": {
                        "status": "unavailable",
                        "score": None,
                    },
                },
            }
        ]
    )
    assert frame.loc[0, "TAIEX 均線趨勢"] == 75
    assert pd.isna(frame.loc[0, "TAIEX 20 日動能"])


def test_factor_history_scores_are_display_rounded_to_one_decimal():
    frame = factor_history_frame(
        [
            {
                "target_date": "2026-09-17",
                "factor_scores_json": {
                    "taiex_20d_momentum": {
                        "status": "available",
                        "score": 49.0113,
                    }
                },
            }
        ]
    )
    assert frame.loc[0, "TAIEX 20 日動能"] == 49.0


def test_tradingview_kline_html_uses_visible_range_auto_scale_and_zoom():
    html = build_tradingview_kline_html(
        pd.DataFrame(
            [
                {
                    "日期": "2026-09-16",
                    "open": 1,
                    "high": 3,
                    "low": 0.5,
                    "close": 2,
                },
            ]
        )
    )
    assert html is not None
    assert "lightweight-charts@4.2.2" in html
    assert "addCandlestickSeries" in html
    assert "autoScale: true" in html
    assert "minimumWidth: 120" in html
    assert "mouseWheel: true" in html
    assert "pressedMouseMove: true" in html
    assert "setVisibleLogicalRange" in html
    assert "getVisibleRange" in html
    assert "setVisibleRange(visibleRange)" in html
    assert "Market Score" not in html


def test_tradingview_kline_html_links_market_score_pane():
    html = build_tradingview_kline_html(
        pd.DataFrame(
            [
                {
                    "日期": "2026-09-16",
                    "open": 1,
                    "high": 3,
                    "low": 0.5,
                    "close": 2,
                },
            ]
        ),
        pd.DataFrame([{"日期": "2026-09-16", "Market Score": 68}]),
    )
    assert html is not None
    assert 'id="score-chart"' in html
    assert "scoreData" in html
    assert "alignedScoreData = candleData.map" in html
    assert "let previousScore" in html
    assert "alignedScoreByTime" in html
    assert "scoreSeries.setData(alignedScoreData)" in html
    assert "subscribeVisibleLogicalRangeChange" in html
    assert "setCrosshairPosition" in html
    assert "scoreByTime" in html


def test_dashboard_renders_history_charts_without_recomputing(monkeypatch):
    score_history = [
        {
            "target_date": "2026-09-16",
            "status": "available",
            "score": 68,
            "factor_scores_json": {
                "taiex_ma20_ma60_trend": {"status": "available", "score": 75}
            },
        },
        {
            "target_date": "2026-09-17",
            "status": "unavailable",
            "score": None,
            "factor_scores_json": {},
        },
    ]
    taiex_history = [
        {
            "observation_date": "2026-09-16",
            "quality_status": "available",
            "values_json": {"open": 1, "high": 3, "low": 0.5, "close": 2},
        }
    ]
    app, store = run_app(
        monkeypatch,
        record={
            "status": "available",
            "score": 68,
            "direction": "偏多",
            "factor_scores_json": {
                "taiex_ma20_ma60_trend": {"status": "available", "score": 75}
            },
        },
        score_history=score_history,
        taiex_history=taiex_history,
    )
    assert not app.exception
    assert any("歷史趨勢" in header.value for header in app.header)
    subheaders = [item.value for item in app.subheader]
    assert (
        subheaders.index("台灣加權指數 · Market Score")
        < subheaders.index("分類與因子")
        < subheaders.index("各因子分數趨勢")
    )
    assert len(app.tabs) == 8
    assert store.get_market_score_history.call_count == 2
    store.get_observation_history.assert_called_once_with(
        "twse_taiex_daily_v1", limit=1000
    )


def test_source_api_error_keeps_other_source_rows_visible(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SECRET_KEY", "sb_secret_never_render_this")
    store = MagicMock()
    store.__enter__.return_value = store
    store.get_latest_market_score.return_value = None
    store.get_latest_source_quality.side_effect = iter(
        [RuntimeError("private detail")] + [None] * (len(SOURCE_DATASETS) - 1)
    )
    with patch("src.dashboard.app.DashboardDataStore", return_value=store):
        app = AppTest.from_file("streamlit_app.py", default_timeout=30).run()
    assert not app.exception
    assert len(app.dataframe) == 1
    assert "無法讀取" in app.warning[0].value
    assert "private detail" not in str(app)
