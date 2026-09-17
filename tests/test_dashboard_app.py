from copy import deepcopy
from unittest.mock import MagicMock, patch

import pytest
from streamlit.testing.v1 import AppTest

from src.dashboard.app import display_score, factor_rows


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_SECRET_KEY", raising=False)


def run_app(monkeypatch, record=None, error=None, source=None):
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SECRET_KEY", "sb_secret_never_render_this")
    store = MagicMock()
    store.__enter__.return_value = store
    store.get_latest_market_score.return_value = record
    store.get_latest_source_quality.return_value = source
    if error:
        store.get_latest_market_score.side_effect = error
    with patch("src.dashboard.app.DashboardDataStore", return_value=store):
        app = AppTest.from_file("streamlit_app.py").run()
    assert not app.exception
    return app, store


def test_missing_credentials_do_not_connect():
    with patch("src.dashboard.app.DashboardDataStore") as factory:
        app = AppTest.from_file("streamlit_app.py").run()
    assert not app.exception
    assert "尚未設定" in app.error[0].value
    factory.assert_not_called()


def test_empty_score_still_displays_source_quality(monkeypatch):
    app, store = run_app(monkeypatch)
    assert "empty" in app.info[0].value
    assert len(app.dataframe[0].value) == 5
    assert set(app.dataframe[0].value["品質狀態"]) == {"empty"}
    assert store.get_latest_source_quality.call_count == 5


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
        "https://user:pass@example.supabase.co",
    ],
)
def test_invalid_url_is_rejected_without_connection(monkeypatch, url):
    monkeypatch.setenv("SUPABASE_URL", url)
    monkeypatch.setenv("SUPABASE_SECRET_KEY", "sb_secret_never_render_this")
    with patch("src.dashboard.app.DashboardDataStore") as factory:
        app = AppTest.from_file("streamlit_app.py").run()
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
    assert app.metric[0].value == ("72 / 100" if score else "unavailable")
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
        app = AppTest.from_file("streamlit_app.py").run()
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
