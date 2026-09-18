"""Read-only Streamlit dashboard; all Supabase access runs on the server."""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from datetime import datetime
from math import isfinite
from urllib.parse import urlsplit

import altair as alt
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
from requests.exceptions import RequestException

from src.dashboard.data import DashboardDataStore
from src.dashboard.view_model import FACTOR_CATEGORIES, FACTOR_LABELS

SOURCE_DATASETS = {
    "twse_taiex_daily_v1": "TWSE 加權指數",
    "twse_foreign_cash_bfi82u_v1": "TWSE 外資現貨流",
    "twse_market_turnover_fmtqik_v1": "TWSE 市場成交金額",
    "taifex_institutional_futures_oi_v1": "TAIFEX 法人期貨部位",
    "taifex_tx_daily_contract_v1": "TAIFEX 台指期行情",
    "taifex_txo_oi_pcr_v1": "TAIFEX OI PCR",
    "taifex_taiwan_vix_close_v1": "TAIFEX Taiwan VIX",
}

TAIEX_DATASET_ID = "twse_taiex_daily_v1"
CHART_LIMIT = 1000

READ_ERRORS = (
    RequestException,
    RuntimeError,
    ValueError,
    TypeError,
    KeyError,
    AttributeError,
)


def display_score(value: object, status: str) -> str:
    """Never present an unavailable or invalid value as a numeric score."""
    if status != "available" or isinstance(value, bool):
        return "unavailable"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "unavailable"
    return (
        f"{number:g} / 100"
        if isfinite(number) and 0 <= number <= 100
        else "unavailable"
    )


def factor_rows(record: Mapping[str, object]) -> list[dict]:
    """Format persisted factor JSON without trusting its shape.

    Rows are persisted data and can outlive a model version, so a malformed
    factor must remain visible as unavailable instead of taking down the
    whole score section.
    """
    raw_factors = record.get("factor_scores_json")
    factors: Mapping[object, object] = (
        raw_factors if isinstance(raw_factors, Mapping) else {}
    )
    factor_ids = dict.fromkeys([*FACTOR_LABELS, *factors])
    rows = []
    for factor_id in factor_ids:
        raw_factor = factors.get(factor_id)
        factor = raw_factor if isinstance(raw_factor, Mapping) else {}
        malformed = factor_id in factors and not isinstance(raw_factor, Mapping)
        status = factor.get("status", "unavailable")
        rows.append(
            {
                "分類": FACTOR_CATEGORIES.get(factor_id, "其他"),
                "因子": FACTOR_LABELS.get(factor_id, str(factor_id)),
                "狀態": status,
                "分數": display_score(factor.get("score"), status),
                "原因": (
                    "資料格式錯誤"
                    if malformed
                    else factor.get("reason")
                    or ("未儲存此因子" if factor_id not in factors else "—")
                ),
            }
        )
    return rows


def _as_rows(value: object) -> list[Mapping[str, object]]:
    """Accept only list-like API payloads; malformed payloads become empty."""

    if not isinstance(value, list):
        return []
    return [row for row in value if isinstance(row, Mapping)]


def _finite_number(
    value: object, *, minimum: float | None = None, maximum: float | None = None
) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not isfinite(number):
        return None
    if minimum is not None and number < minimum:
        return None
    if maximum is not None and number > maximum:
        return None
    return number


def _latest_rows_by_date(
    rows: list[Mapping[str, object]],
) -> list[Mapping[str, object]]:
    """Keep the last persisted revision for a date, preserving missing dates."""

    latest: dict[str, Mapping[str, object]] = {}
    for row in rows:
        date_text = row.get("observation_date") or row.get("target_date")
        if isinstance(date_text, str) and date_text:
            latest[date_text] = row
    return [latest[key] for key in sorted(latest)]


def score_history_frame(rows: object) -> pd.DataFrame:
    """Build a score history with unavailable dates represented as missing."""

    output: list[dict[str, object]] = []
    latest: dict[str, Mapping[str, object]] = {}
    for row in _as_rows(rows):
        target = row.get("target_date")
        if isinstance(target, str) and target:
            latest[target] = row
    for target in sorted(latest):
        row = latest[target]
        status = row.get("status")
        score = (
            _finite_number(row.get("score"), minimum=0, maximum=100)
            if status == "available"
            else None
        )
        output.append(
            {"日期": target, "Market Score": score, "狀態": status or "unavailable"}
        )
    return pd.DataFrame(output, columns=["日期", "Market Score", "狀態"])


def taiex_ohlc_frame(rows: object) -> pd.DataFrame:
    """Build TAIEX OHLC rows; incomplete or non-available rows are omitted."""

    output: list[dict[str, object]] = []
    for row in _latest_rows_by_date(_as_rows(rows)):
        if row.get("quality_status") != "available":
            continue
        values = row.get("values_json")
        if not isinstance(values, Mapping):
            continue
        numbers = {
            field: _finite_number(values.get(field), minimum=0)
            for field in ("open", "high", "low", "close")
        }
        if any(value is None for value in numbers.values()):
            continue
        output.append({"日期": row["observation_date"], **numbers})
    return pd.DataFrame(output, columns=["日期", "open", "high", "low", "close"])


def factor_history_frame(rows: object) -> pd.DataFrame:
    """Build one column per factor, leaving unavailable scores as missing."""

    latest: dict[str, Mapping[str, object]] = {}
    for row in _as_rows(rows):
        target = row.get("target_date")
        if isinstance(target, str) and target:
            latest[target] = row
    output: list[dict[str, object]] = []
    for target in sorted(latest):
        row = latest[target]
        raw_factors = row.get("factor_scores_json")
        factors = raw_factors if isinstance(raw_factors, Mapping) else {}
        item: dict[str, object] = {"日期": target}
        for factor_id, label in FACTOR_LABELS.items():
            factor = factors.get(factor_id)
            if isinstance(factor, Mapping) and factor.get("status") == "available":
                item[label] = _finite_number(
                    factor.get("score"), minimum=0, maximum=100
                )
            else:
                item[label] = None
        output.append(item)
    return pd.DataFrame(output, columns=["日期", *FACTOR_LABELS.values()])


TRADINGVIEW_LIBRARY_URL = (
    "https://unpkg.com/lightweight-charts@4.2.2/"
    "dist/lightweight-charts.standalone.production.js"
)


def build_tradingview_kline_html(ohlc: pd.DataFrame) -> str | None:
    """Build a self-contained TradingView Lightweight Charts candlestick view.

    The library's price scale is deliberately left in auto-scale mode. That
    makes the right axis follow the highest and lowest candles in the current
    visible range whenever the user zooms or drags horizontally.
    """

    if ohlc.empty:
        return None
    rows = []
    for row in ohlc.to_dict("records"):
        date = row.get("日期")
        if not isinstance(date, str) or not date:
            continue
        numbers = {
            field: _finite_number(row.get(field), minimum=0)
            for field in ("open", "high", "low", "close")
        }
        if any(value is None for value in numbers.values()):
            continue
        rows.append({"time": date, **numbers})
    if not rows:
        return None
    payload = json.dumps(rows, ensure_ascii=False, separators=(",", ":"))
    return (
        """<!doctype html>
<html lang="zh-Hant">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <style>
    :root { color-scheme: light; }
    html, body { margin: 0; padding: 0; background: #ffffff; }
    body { overflow: hidden; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }
    .shell { width: 100%; height: 560px; display: flex; flex-direction: column; background: #ffffff; }
    .legend { height: 42px; padding: 8px 14px 0; box-sizing: border-box; color: #1f2937; font-size: 13px; line-height: 20px; }
    .title { font-weight: 700; letter-spacing: .01em; }
    .values { color: #4b5563; margin-left: 12px; }
    .values span { margin-right: 10px; }
    .values .positive { color: #0f9f91; }
    .values .negative { color: #e05252; }
    #chart { flex: 1; min-height: 0; }
  </style>
</head>
<body>
  <div class="shell">
    <div class="legend" id="legend">
      <span class="title">TSEC WEIGHTED INDEX · 1D</span>
      <span class="values" id="values"></span>
    </div>
    <div id="chart" aria-label="台指大盤日 K 線圖"></div>
  </div>
  <script src="""
        + TRADINGVIEW_LIBRARY_URL
        + """></script>
  <script>
    const data = """
        + payload
        + """;
    const chartElement = document.getElementById('chart');
    const valuesElement = document.getElementById('values');
    const chart = LightweightCharts.createChart(chartElement, {
      autoSize: true,
      layout: { background: { color: '#ffffff' }, textColor: '#374151', fontSize: 12 },
      grid: {
        vertLines: { color: '#eef1f4' },
        horzLines: { color: '#eef1f4' }
      },
      rightPriceScale: {
        borderColor: '#d1d5db',
        autoScale: true,
        scaleMargins: { top: 0.08, bottom: 0.08 }
      },
      timeScale: {
        borderColor: '#d1d5db',
        rightOffset: 8,
        barSpacing: 8,
        minBarSpacing: 3,
        timeVisible: false,
        secondsVisible: false,
        fixLeftEdge: false,
        fixRightEdge: false,
        rightBarStaysOnScroll: true
      },
      crosshair: { mode: LightweightCharts.CrosshairMode.Normal },
      handleScroll: {
        mouseWheel: false,
        pressedMouseMove: true,
        horzTouchDrag: true,
        vertTouchDrag: false
      },
      handleScale: {
        mouseWheel: true,
        pinch: true,
        axisPressedMouseMove: true,
        axisDoubleClickReset: true,
        axisLabelPressedMouseMove: true
      }
    });
    const candles = chart.addCandlestickSeries({
      upColor: '#26a69a',
      downColor: '#ef5350',
      borderUpColor: '#26a69a',
      borderDownColor: '#ef5350',
      wickUpColor: '#26a69a',
      wickDownColor: '#ef5350',
      priceLineVisible: true,
      lastValueVisible: true
    });
    candles.setData(data);
    const latest = data[data.length - 1];
    const renderValues = (point) => {
      if (!point) return;
      const cls = point.close >= point.open ? 'positive' : 'negative';
      valuesElement.innerHTML =
        '<span>開 ' + Number(point.open).toLocaleString(undefined, { maximumFractionDigits: 2 }) + '</span>' +
        '<span>高 ' + Number(point.high).toLocaleString(undefined, { maximumFractionDigits: 2 }) + '</span>' +
        '<span>低 ' + Number(point.low).toLocaleString(undefined, { maximumFractionDigits: 2 }) + '</span>' +
        '<span class="' + cls + '">收 ' + Number(point.close).toLocaleString(undefined, { maximumFractionDigits: 2 }) + '</span>';
    };
    renderValues(latest);
    chart.subscribeCrosshairMove((param) => {
      const point = param.seriesData.get(candles);
      renderValues(point || latest);
    });
    const start = Math.max(0, data.length - 180);
    chart.timeScale().setVisibleLogicalRange({ from: start, to: data.length + 8 });
  </script>
</body>
</html>
"""
    )


def build_market_score_chart(score_plot: pd.DataFrame) -> alt.TopLevelMixin | None:
    """Build the independent Market Score trend chart."""

    if score_plot.empty:
        return None
    score_data = score_plot.copy()
    score_data["日期"] = pd.to_datetime(score_data["日期"])
    zoom = alt.selection_interval(
        name="market_score_zoom", bind="scales", encodings=["x", "y"]
    )
    return (
        alt.Chart(score_data)
        .mark_line(point=True, color="#2563eb")
        .encode(
            x=alt.X("日期:T", title="日期"),
            y=alt.Y("Market Score:Q", title="分數", scale=alt.Scale(domain=[0, 100])),
            tooltip=[
                alt.Tooltip("日期:T", title="日期"),
                alt.Tooltip("Market Score:Q", title="Market Score", format=",.2f"),
            ],
        )
        .properties(height=220, title="Market Score 趨勢")
        .add_params(zoom)
    )


def render_history_charts(store: DashboardDataStore) -> None:
    """Render read-only trend views from persisted rows only."""

    st.header("歷史趨勢")
    try:
        score_rows = store.get_market_score_history(limit=CHART_LIMIT)
    except READ_ERRORS:
        st.warning("無法讀取 Market Score 歷史，暫不顯示評分趨勢圖。")
        score_rows = []
    score_frame = score_history_frame(score_rows)
    score_plot = score_frame.dropna(subset=["Market Score"])

    try:
        taiex_rows = store.get_observation_history(TAIEX_DATASET_ID, limit=CHART_LIMIT)
    except READ_ERRORS:
        st.warning("無法讀取 TAIEX 歷史，暫不顯示 K 線圖。")
        taiex_rows = []
    ohlc = taiex_ohlc_frame(taiex_rows)
    st.subheader("台指大盤 K 線 · TradingView 風格")
    kline_html = build_tradingview_kline_html(ohlc)
    if kline_html is None:
        st.info("目前沒有可繪製的 TAIEX OHLC 資料。")
    else:
        components.html(kline_html, height=560, scrolling=False)
        st.caption(
            "操作：滑鼠滾輪縮放時間範圍；按住滑鼠左鍵左右拖曳平移；右側價格軸會依目前可見 K 線自動調整。"
        )
    st.subheader("Market Score 趨勢")
    score_chart = build_market_score_chart(score_plot)
    if score_chart is not None:
        st.altair_chart(score_chart, use_container_width=True)
    if score_plot.empty:
        st.info(
            "目前沒有可繪製的 available Market Score；unavailable 日期不會被當成 0。"
        )
    elif not score_frame.empty and score_frame["狀態"].ne("available").any():
        st.caption("部分評分日期為 unavailable，已保留狀態但未繪入數值線。")
    if ohlc.empty:
        st.info("目前沒有完整的 TAIEX OHLC 資料可繪圖。")
    if len(ohlc) < len(_latest_rows_by_date(_as_rows(taiex_rows))):
        st.caption("部分日期缺少完整 OHLC 或品質不可用，已從 K 線排除。")

    try:
        factor_rows_history = store.get_market_score_history(limit=CHART_LIMIT)
    except READ_ERRORS:
        factor_rows_history = []
    factor_frame = factor_history_frame(factor_rows_history)
    st.subheader("各因子分數趨勢")
    factor_columns = [column for column in factor_frame.columns if column != "日期"]
    factor_plot = (
        factor_frame.dropna(subset=factor_columns, how="all")
        if factor_columns
        else pd.DataFrame()
    )
    if factor_plot.empty:
        st.info("目前沒有可繪製的 available 因子分數；缺值不會被當成 0。")
    else:
        factor_tabs = st.tabs(factor_columns)
        indexed_factor_plot = factor_plot.set_index("日期")
        for factor_id, factor_label, factor_tab in zip(
            FACTOR_LABELS, factor_columns, factor_tabs, strict=True
        ):
            with factor_tab:
                factor_series = indexed_factor_plot[factor_label]
                available = factor_series.dropna()
                category = FACTOR_CATEGORIES.get(factor_id, "其他")
                st.caption(f"{category} · {len(available)} 筆 available")
                if available.empty:
                    st.info("目前沒有可繪製的 available 分數；缺值不會被當成 0。")
                else:
                    st.line_chart(
                        factor_series,
                        y_label="因子分數",
                        height=300,
                    )


def render_score(record: dict | None) -> None:
    if record is None:
        st.info("尚無 Market Score（empty）。請由既有評分流程寫入結果後重新整理。")
        return
    status = record.get("status", "unavailable")
    score = display_score(record.get("score"), status)
    headline = (
        (record.get("direction") or "Market Score")
        if score != "unavailable"
        else "Market Score 尚不可用"
    )
    st.subheader(headline)
    st.metric("Market Score", score)
    st.text(f"狀態：{status} · 模型：{record.get('model_version', '未記錄')}")
    st.text(f"Target（評分日期）：{record.get('target_date', '未記錄')}")
    st.text(f"As-of（資訊截止）：{record.get('as_of') or '未記錄'}")
    st.text(f"分數寫入時間：{record.get('created_at') or '未記錄'}")
    if record.get("reason"):
        st.text(f"原因：{record['reason']}")
    st.subheader("分類與因子")
    st.dataframe(factor_rows(record), hide_index=True, width="stretch")
    st.caption(
        "顯示已儲存的因子分數；目前持久化格式未包含原始值或分類總分，本頁不重新計算。"
    )


def _parse_source_timestamp(value: object) -> tuple[str, datetime | None]:
    """Return a safe display value and comparable timestamp for one row."""
    if not isinstance(value, str) or not value:
        return ("未記錄" if value in (None, "") else "格式錯誤", None)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return "格式錯誤", None
    # Database timestamps are expected to carry a timezone. Treat a legacy
    # naive value as UTC for comparison while preserving its display string.
    if parsed.tzinfo is None:
        from datetime import timezone

        parsed = parsed.replace(tzinfo=timezone.utc)
    return value, parsed


def render_sources(store: DashboardDataStore) -> None:
    st.subheader("來源資料品質與更新")
    rows = []
    timestamps = []
    failed_reads = 0
    for dataset_id, label in SOURCE_DATASETS.items():
        try:
            row = store.get_latest_source_quality(dataset_id)
        except READ_ERRORS:
            failed_reads += 1
            row = None
        if not isinstance(row, Mapping):
            row = None
        retrieved_at, parsed_timestamp = _parse_source_timestamp(
            row.get("last_retrieved_at") if row else None
        )
        if parsed_timestamp is not None:
            timestamps.append(parsed_timestamp)
        rows.append(
            {
                "來源": label,
                "資料日期": row.get("observation_date") if row else "—",
                "紀錄": row.get("source_record_key") if row else "—",
                "品質狀態": row.get("quality_status") if row else "empty",
                "最後擷取時間": retrieved_at,
                "品質說明": (row.get("quality_notes") or "—")
                if row
                else "尚無來源紀錄",
            }
        )
    st.text(
        f"來源資料最後更新時間：{max(timestamps).isoformat() if timestamps else '未記錄'}"
    )
    st.dataframe(rows, hide_index=True, width="stretch")
    if failed_reads:
        st.warning(
            f"有 {failed_reads} 個來源無法讀取，表格中的 empty 不代表來源沒有資料。"
        )
    st.caption(
        "每個來源僅列最近擷取的一筆紀錄，並非整批品質或分數使用證據。"
        "未寫入資料庫的失敗擷取不會出現在此；available 不代表資料仍新鮮，請核對日期。"
        "時間保留資料庫時區；外資現貨分子與市場成交金額分母分開列示。"
    )


def main() -> None:
    st.set_page_config(page_title="Huda｜台指大盤", layout="wide")
    st.title("Huda｜台指大盤")
    st.caption("唯讀展示 · 最新已儲存結果 · 不提供下單或部位建議")
    st.button("重新整理", help="重新讀取最新已儲存結果與來源狀態")
    url = os.environ.get("SUPABASE_URL", "").strip()
    key = os.environ.get("SUPABASE_SECRET_KEY", "").strip()
    if not url or not key:
        st.error(
            "尚未設定資料連線。請在伺服器環境設定 SUPABASE_URL 與 SUPABASE_SECRET_KEY，再啟動頁面。"
        )
        return
    try:
        parsed = urlsplit(url)
        hostname = parsed.hostname
        _port = parsed.port
    except ValueError:
        st.error("SUPABASE_URL 設定錯誤：請使用有效的 HTTPS 專案網址。")
        return
    if (
        parsed.scheme != "https"
        or not hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
    ):
        st.error("SUPABASE_URL 設定錯誤：請使用不含帳密、查詢參數的 HTTPS 專案網址。")
        return
    # Never pass credentials, sessions, response bodies or raw exceptions to
    # Streamlit. Data API errors may include sensitive server information.
    try:
        with DashboardDataStore(url, key, timeout=10) as store:
            try:
                render_score(store.get_latest_market_score())
            except READ_ERRORS:
                st.error(
                    "無法讀取 Market Score。請維護者確認 market_scores 表、Data API 權限與網路連線。"
                )
            try:
                render_history_charts(store)
            except READ_ERRORS:
                st.warning("歷史趨勢暫時無法顯示；最新分數與來源狀態仍可查看。")
            try:
                render_sources(store)
            except READ_ERRORS:
                st.warning(
                    "無法讀取來源品質。請維護者確認 observations 表、Data API 權限與網路連線。"
                )
    except READ_ERRORS:
        st.error(
            "資料連線失敗。請維護者確認伺服器憑證、observations 表與 Supabase Data API 是否可用。"
        )


if __name__ == "__main__":
    main()
