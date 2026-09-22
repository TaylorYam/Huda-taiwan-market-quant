"""Read-only Streamlit dashboard; all Supabase access runs on the server."""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from datetime import datetime
from html import escape
from math import isfinite
from urllib.parse import urlsplit

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
from requests.exceptions import RequestException

from src.dashboard.data import DashboardDataStore
from src.dashboard.view_model import (
    FACTOR_CATEGORIES,
    FACTOR_EXPLANATIONS,
    FACTOR_LABELS,
)

SOURCE_DATASETS = {
    "twse_taiex_daily_v1": "TWSE 加權指數",
    "twse_foreign_cash_bfi82u_v1": "TWSE 外資現貨流",
    "twse_market_turnover_fmtqik_v1": "TWSE 市場成交金額",
    "taifex_institutional_futures_oi_v1": "TAIFEX 法人期貨部位",
    "taifex_tx_daily_contract_v1": "TAIFEX 台指期行情",
    "taifex_txo_oi_pcr_v1": "TAIFEX OI PCR",
    "taifex_taiwan_vix_close_v1": "TAIFEX Taiwan VIX",
}

SOURCE_ATTRIBUTION = (
    "資料來源："
    "[臺灣證券交易所 TWSE](https://www.twse.com.tw/)、"
    "[臺灣期貨交易所 TAIFEX](https://www.taifex.com.tw/)。"
    "本頁僅展示已儲存的公開資料與評分結果。"
)

TAIEX_DATASET_ID = "twse_taiex_daily_v1"
CHART_LIMIT = 1000

WARNING_ICON_SVG = """
<svg class="warning-icon" width="18" height="18" viewBox="0 0 24 24" role="img" aria-label="資料品質警示" style="vertical-align:-4px;color:#b45309">
  <path d="M12 3 2.8 20h18.4L12 3Z" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/>
  <path d="M12 9v5" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>
  <circle cx="12" cy="17.2" r="1" fill="currentColor"/>
</svg>
"""

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
        f"{number:.1f} / 100"
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
        if score is not None:
            score = round(score, 1)
        output.append(
            {"日期": target, "Market Score": score, "狀態": status or "unavailable"}
        )
    return pd.DataFrame(output, columns=["日期", "Market Score", "狀態"])


def previous_score_delta(
    record: Mapping[str, object] | None, rows: object
) -> float | None:
    """Return the change from the previous date that had an available score."""

    if not isinstance(record, Mapping) or record.get("status") != "available":
        return None
    current = _finite_number(record.get("score"), minimum=0, maximum=100)
    target = record.get("target_date")
    if current is None or not isinstance(target, str) or not target:
        return None
    candidates: list[tuple[str, float]] = []
    for row in _as_rows(rows):
        row_date = row.get("target_date")
        if not isinstance(row_date, str) or row_date >= target:
            continue
        if row.get("status") != "available":
            continue
        score = _finite_number(row.get("score"), minimum=0, maximum=100)
        if score is not None:
            candidates.append((row_date, score))
    if not candidates:
        return None
    return round(current - max(candidates, key=lambda item: item[0])[1], 1)


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
                if item[label] is not None:
                    item[label] = round(item[label], 1)
            else:
                item[label] = None
        output.append(item)
    return pd.DataFrame(output, columns=["日期", *FACTOR_LABELS.values()])


def factor_table_markup(record: Mapping[str, object] | None) -> str:
    """Render the persisted factor table inside the linked chart component."""

    if record is None:
        return ""
    rows = factor_rows(record)
    headers = ("分類", "因子", "狀態", "分數", "原因")
    header_markup = "".join(f"<th>{escape(header)}</th>" for header in headers)
    body_markup_rows = []
    for row in rows:
        cells = []
        for header in headers:
            value = row.get(header)
            cells.append(f"<td>{escape(str(value if value is not None else '—'))}</td>")
        body_markup_rows.append("<tr>" + "".join(cells) + "</tr>")
    body_markup = "".join(body_markup_rows)
    return (
        '<section class="factor-table" aria-label="分類與因子">'
        "<h2>分類與因子</h2>"
        f'<div class="table-scroll"><table><thead><tr>{header_markup}</tr></thead>'
        f"<tbody>{body_markup}</tbody></table></div>"
        '<p class="table-note">顯示已儲存的因子分數；目前持久化格式未包含原始值或分類總分，本頁不重新計算。</p>'
        "</section>"
    )


TRADINGVIEW_LIBRARY_URL = (
    "https://unpkg.com/lightweight-charts@4.2.2/"
    "dist/lightweight-charts.standalone.production.js"
)


def build_tradingview_kline_html(
    ohlc: pd.DataFrame,
    score_plot: pd.DataFrame | None = None,
    factor_plot: pd.DataFrame | None = None,
    factor_table: Mapping[str, object] | None = None,
    factor_explanations: Mapping[str, Mapping[str, str]] | None = None,
) -> str | None:
    """Build one linked Lightweight Charts component for all history panes.

    The price, Market Score, and selected factor panes share their visible date
    range and crosshair. Every pane keeps its own auto-scaled right axis.
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
    score_rows = []
    if score_plot is not None:
        for row in score_plot.to_dict("records"):
            date = row.get("日期")
            score = _finite_number(row.get("Market Score"), minimum=0, maximum=100)
            if isinstance(date, str) and date and score is not None:
                score_rows.append({"time": date, "value": score})
    payload = json.dumps(rows, ensure_ascii=False, separators=(",", ":"))
    score_payload = json.dumps(score_rows, ensure_ascii=False, separators=(",", ":"))
    factor_rows_payload: dict[str, list[dict[str, object]]] = {}
    if factor_plot is not None and not factor_plot.empty:
        factor_columns = [column for column in factor_plot.columns if column != "日期"]
        for factor_label in factor_columns:
            factor_rows_for_chart = []
            has_value = False
            for row in factor_plot.to_dict("records"):
                date = row.get("日期")
                if not isinstance(date, str) or not date:
                    continue
                value = _finite_number(row.get(factor_label), minimum=0, maximum=100)
                point: dict[str, object] = {"time": date}
                if value is not None:
                    point["value"] = round(value, 1)
                    has_value = True
                factor_rows_for_chart.append(point)
            if has_value:
                factor_rows_payload[factor_label] = factor_rows_for_chart
    factor_payload = json.dumps(
        factor_rows_payload, ensure_ascii=False, separators=(",", ":")
    )
    explanation_payload = json.dumps(
        {
            FACTOR_LABELS.get(factor_id, factor_id): dict(details)
            for factor_id, details in (
                factor_explanations or FACTOR_EXPLANATIONS
            ).items()
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )
    factor_table_html = factor_table_markup(factor_table)
    score_markup = (
        """<div class="score-title">Market Score（副圖）</div>
    <div id="score-chart" class="pane" aria-label="Market Score 趨勢圖"></div>"""
        if score_rows
        else ""
    )
    factor_markup = (
        """<section class="factor-panel" aria-label="各因子分數趨勢">
      <div class="factor-title">各因子分數趨勢</div>
      <div id="factor-tabs" class="factor-tabs" role="tablist"></div>
      <div id="factor-chart" class="pane" aria-label="選定因子趨勢圖"></div>
      <div id="factor-explanation" class="factor-explanation" aria-live="polite"></div>
    </section>"""
        if factor_rows_payload
        else ""
    )
    return (
        """<!doctype html>
<html lang="zh-Hant">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <style>
    :root { color-scheme: light; }
    html, body { margin: 0; padding: 0; background: #ffffff; }
    body { overflow: hidden; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; user-select: none; -webkit-user-select: none; caret-color: transparent; }
    .shell { width: 100%; height: 1320px; display: flex; flex-direction: column; background: #ffffff; }
    .legend { min-height: 50px; padding: 9px 14px 4px; box-sizing: border-box; color: #1f2937; font-size: 13px; line-height: 20px; }
    .title { font-weight: 700; letter-spacing: .01em; }
    .values { color: #4b5563; margin-left: 12px; }
    .values span { margin-right: 10px; }
    .fill-note { color: #b45309; font-size: 11px; }
    .values .positive { color: #0f9f91; }
    .values .negative { color: #e05252; }
    .range-controls { display: flex; gap: 5px; align-items: center; margin-top: 5px; overflow-x: auto; }
    .range-button { border: 1px solid #d1d5db; border-radius: 4px; background: #ffffff; color: #4b5563; padding: 3px 8px; font: inherit; font-size: 11px; cursor: pointer; }
    .range-button[aria-pressed="true"] { border-color: #2563eb; background: #eff6ff; color: #1d4ed8; font-weight: 600; }
    .pane { width: 100%; min-height: 0; user-select: none; -webkit-user-select: none; caret-color: transparent; }
    #price-chart { flex: 0 0 410px; min-height: 300px; }
    .score-title { height: 26px; padding: 5px 14px 0; box-sizing: border-box; color: #4b5563; font-size: 12px; border-top: 1px solid #e5e7eb; }
    #score-chart { flex: 0 0 150px; }
    .factor-table { flex: 0 0 245px; min-height: 0; padding: 10px 14px 8px; border-top: 1px solid #e5e7eb; box-sizing: border-box; }
    .factor-table h2 { margin: 0 0 6px; color: #1f2937; font-size: 16px; line-height: 22px; }
    .table-scroll { max-height: 188px; overflow: auto; border: 1px solid #e5e7eb; border-radius: 8px; }
    .factor-table table { width: 100%; border-collapse: collapse; color: #374151; font-size: 12px; }
    .factor-table th, .factor-table td { padding: 5px 8px; text-align: left; border-bottom: 1px solid #eef1f4; white-space: nowrap; }
    .factor-table th { position: sticky; top: 0; background: #f8fafc; color: #6b7280; font-weight: 600; }
    .factor-table tr:last-child td { border-bottom: 0; }
    .table-note { margin: 5px 0 0; color: #9ca3af; font-size: 11px; }
    .factor-panel { flex: 0 0 430px; min-height: 430px; display: flex; flex-direction: column; border-top: 1px solid #e5e7eb; }
    .factor-title { height: 26px; padding: 5px 14px 0; box-sizing: border-box; color: #4b5563; font-size: 12px; }
    .factor-tabs { display: flex; gap: 4px; height: 36px; padding: 2px 14px 5px; box-sizing: border-box; overflow-x: auto; }
    .factor-tab { flex: 0 0 auto; border: 1px solid #d1d5db; border-radius: 5px; background: #ffffff; color: #4b5563; padding: 3px 9px; font: inherit; font-size: 12px; cursor: pointer; }
    .factor-tab[aria-selected="true"] { border-color: var(--factor-color, #2563eb); background: #eff6ff; color: var(--factor-color, #1d4ed8); font-weight: 600; }
    #factor-chart { flex: 0 0 190px; min-height: 150px; }
    .factor-explanation { margin: 8px 14px 12px; padding: 9px 11px; border: 1px solid #e5e7eb; border-radius: 8px; background: #f8fafc; color: #374151; font-size: 12px; line-height: 1.55; }
    .factor-explanation-title { color: #111827; font-size: 13px; font-weight: 700; margin-bottom: 6px; }
    .factor-explanation-grid { display: grid; grid-template-columns: 80px 1fr; gap: 4px 10px; }
    .factor-explanation-grid dt { color: #6b7280; font-weight: 600; }
    .factor-explanation-grid dd { margin: 0; }
    @media (max-width: 720px) {
      .shell { height: 1320px; }
      #price-chart { flex-basis: 330px; }
      #score-chart { flex-basis: 130px; }
      .factor-panel { flex-basis: 455px; min-height: 455px; }
      #factor-chart { flex-basis: 170px; }
      .factor-explanation-grid { grid-template-columns: 68px 1fr; }
      .values { display: block; margin-left: 0; }
    }
  </style>
</head>
<body>
  <div class="shell">
    <div class="legend" id="legend">
      <span class="title">台灣加權指數 · Market Score</span>
      <span class="values" id="values"></span>
      <span class="fill-note" id="fill-note" aria-live="polite"></span>
      <div class="range-controls" id="range-controls" role="group" aria-label="顯示期間"></div>
    </div>
    <div id="price-chart" class="pane" aria-label="台指大盤日 K 線圖"></div>
    """
        + score_markup
        + factor_markup
        + factor_table_html
        + """
  </div>
  <script src="""
        + TRADINGVIEW_LIBRARY_URL
        + """></script>
  <script>
    const candleData = """
        + payload
        + """;
    const scoreData = """
        + score_payload
        + """;
    const factorData = """
        + factor_payload
        + """;
    const factorExplanations = """
        + explanation_payload
        + """;
    const scoreByTime = new Map(scoreData.map((point) => [point.time, point.value]));
    const alignedScoreByTime = new Map();
    const scoreFillData = [];
    let previousScore;
    const alignedScoreData = candleData.map((point) => {
      const score = scoreByTime.get(point.time);
      if (score !== undefined) previousScore = score;
      if (previousScore === undefined) return { time: point.time };
      alignedScoreByTime.set(point.time, previousScore);
      if (score === undefined) scoreFillData.push({ time: point.time, value: previousScore });
      return score === undefined ? { time: point.time } : { time: point.time, value: score };
    });
    const priceElement = document.getElementById('price-chart');
    const valuesElement = document.getElementById('values');
    const fillNoteElement = document.getElementById('fill-note');
    const scoreElement = document.getElementById('score-chart');
    const factorTabsElement = document.getElementById('factor-tabs');
    const factorElement = document.getElementById('factor-chart');
    const factorExplanationElement = document.getElementById('factor-explanation');
    const rangeControlsElement = document.getElementById('range-controls');
    const interactionOptions = {
      crosshair: {
        mode: LightweightCharts.CrosshairMode.Normal,
        // Keep the horizontal price guide/label, but do not draw the
        // blinking vertical guide that looks like a text caret on click.
        vertLine: { visible: false, labelVisible: false },
        horzLine: { visible: true, labelVisible: true }
      },
      handleScroll: {
        mouseWheel: false,
        pressedMouseMove: true,
        horzTouchDrag: true,
        vertTouchDrag: false
      },
      handleScale: {
        mouseWheel: false,
        pinch: true,
        axisPressedMouseMove: true,
        axisDoubleClickReset: true,
        axisLabelPressedMouseMove: true
      }
    };
    const chartOptions = (showTimeAxis) => ({
      autoSize: true,
      layout: { background: { color: '#ffffff' }, textColor: '#374151', fontSize: 12 },
      grid: {
        vertLines: { color: '#eef1f4' },
        horzLines: { color: '#eef1f4' }
      },
      rightPriceScale: {
        borderColor: '#d1d5db',
        autoScale: true,
        minimumWidth: 120,
        scaleMargins: { top: 0.08, bottom: 0.08 }
      },
      timeScale: {
        borderColor: '#d1d5db',
        rightOffset: 8,
        barSpacing: 8,
        minBarSpacing: 3,
        timeVisible: showTimeAxis,
        secondsVisible: false,
        visible: showTimeAxis,
        fixLeftEdge: false,
        fixRightEdge: false,
        rightBarStaysOnScroll: true
      },
      ...interactionOptions
    });
    const priceChart = LightweightCharts.createChart(priceElement, chartOptions(false));
    let mainChartWheelActive = false;
    const setMainChartWheelActive = (active) => {
      mainChartWheelActive = active;
      priceChart.applyOptions({ handleScale: { mouseWheel: active } });
      priceElement.dataset.wheelZoom = active ? 'enabled' : 'disabled';
    };
    const isPrimaryPointer = (event) => event.button === undefined || event.button === 0;
    priceElement.addEventListener('pointerdown', (event) => {
      if (isPrimaryPointer(event)) setMainChartWheelActive(true);
    });
    document.addEventListener('pointerdown', (event) => {
      if (!priceElement.contains(event.target)) setMainChartWheelActive(false);
    });
    document.addEventListener('selectstart', (event) => {
      if (event.target instanceof Element && event.target.closest('.shell')) {
        event.preventDefault();
      }
    });
    setMainChartWheelActive(false);
    const candles = priceChart.addCandlestickSeries({
      upColor: '#26a69a',
      downColor: '#ef5350',
      borderUpColor: '#26a69a',
      borderDownColor: '#ef5350',
      wickUpColor: '#26a69a',
      wickDownColor: '#ef5350',
      priceLineVisible: true,
      lastValueVisible: true
    });
    candles.setData(candleData);
    const latest = candleData[candleData.length - 1];
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
    const candleByTime = new Map(candleData.map((point) => [point.time, point]));
    priceChart.subscribeCrosshairMove((param) => {
      const point = param.seriesData.get(candles);
      renderValues(point || latest);
    });
    const charts = [priceChart];
    let scoreChart = null;
    let scoreSeries = null;
    let scoreFillSeries = null;
    if (scoreElement && scoreData.length) {
      scoreChart = LightweightCharts.createChart(scoreElement, chartOptions(true));
      scoreSeries = scoreChart.addLineSeries({
        color: '#2563eb',
        lineWidth: 2,
        priceLineVisible: false,
        lastValueVisible: true,
        crosshairMarkerVisible: true
      });
      scoreSeries.setData(alignedScoreData);
      if (scoreFillData.length) {
        scoreFillSeries = scoreChart.addLineSeries({
          color: '#93c5fd',
          lineWidth: 2,
          lineStyle: LightweightCharts.LineStyle.Dashed,
          priceLineVisible: false,
          lastValueVisible: false,
          crosshairMarkerVisible: false
        });
        scoreFillSeries.setData(scoreFillData);
      }
      scoreChart.applyOptions({
        rightPriceScale: { scaleMargins: { top: 0.12, bottom: 0.12 } }
      });
      scoreSeries.createPriceLine({
        price: 50,
        color: '#9ca3af',
        lineWidth: 1,
        lineStyle: LightweightCharts.LineStyle.Dashed,
        axisLabelVisible: false,
        title: '中性'
      });
      charts.push(scoreChart);
    }
    let factorChart = null;
    let factorSeries = null;
    let factorFillSeries = null;
    let selectedFactorByTime = new Map();
    let selectedFactorFilledTimes = new Set();
    const factorLabels = Object.keys(factorData);
    const factorPalette = [
      '#0f766e', '#d97706', '#7c3aed', '#dc2626',
      '#0891b2', '#65a30d', '#db2777', '#4f46e5'
    ];
    const factorColorByLabel = new Map(
      factorLabels.map((label, index) => [label, factorPalette[index % factorPalette.length]])
    );
    const updateFactorButtons = (selectedLabel) => {
      if (!factorTabsElement) return;
      factorTabsElement.querySelectorAll('button').forEach((button) => {
        button.setAttribute('aria-selected', button.dataset.factor === selectedLabel ? 'true' : 'false');
      });
    };
    const renderFactorExplanation = (factorLabel) => {
      if (!factorExplanationElement) return;
      const explanation = factorExplanations[factorLabel] || {};
      const row = (label, value) =>
        '<dt>' + label + '</dt><dd>' + (value || '—') + '</dd>';
      factorExplanationElement.innerHTML =
        '<div class="factor-explanation-title">' + factorLabel + ' · 因子說明</div>' +
        '<dl class="factor-explanation-grid">' +
        row('判斷用途', explanation.purpose) +
        row('資料窗口', explanation.window) +
        row('計算邏輯', explanation.logic) +
        row('分數方向', explanation.direction) +
        '</dl>';
    };
    const selectFactor = (factorLabel) => {
      if (!factorChart || !factorSeries) return;
      const rows = factorData[factorLabel] || [];
      const visibleRange = factorChart.timeScale().getVisibleRange();
      factorSeries.setData(rows);
      factorSeries.applyOptions({ color: factorColorByLabel.get(factorLabel) || factorPalette[0] });
      const filledRows = [];
      let previousValue;
      rows.forEach((point) => {
        if (point.value !== undefined) {
          previousValue = point.value;
        } else if (previousValue !== undefined) {
          filledRows.push({ time: point.time, value: previousValue });
        }
      });
      if (factorFillSeries) {
        factorFillSeries.setData(filledRows);
        factorFillSeries.applyOptions({ color: factorColorByLabel.get(factorLabel) || factorPalette[0] });
      }
      selectedFactorFilledTimes = new Set(filledRows.map((point) => point.time));
      selectedFactorByTime = new Map(
        [...rows.filter((point) => point.value !== undefined), ...filledRows].map((point) => [point.time, point.value])
      );
      factorChart.priceScale('right').applyOptions({ autoScale: true });
      if (visibleRange) factorChart.timeScale().setVisibleRange(visibleRange);
      updateFactorButtons(factorLabel);
      renderFactorExplanation(factorLabel);
    };
    if (factorElement && factorLabels.length) {
      factorChart = LightweightCharts.createChart(factorElement, chartOptions(true));
      factorSeries = factorChart.addLineSeries({
        color: factorColorByLabel.get(factorLabels[0]) || factorPalette[0],
        lineWidth: 2,
        priceLineVisible: false,
        lastValueVisible: true,
        crosshairMarkerVisible: true,
        priceFormat: { type: 'price', precision: 1, minMove: 0.1 }
      });
      factorFillSeries = factorChart.addLineSeries({
        color: factorColorByLabel.get(factorLabels[0]) || factorPalette[0],
        lineWidth: 2,
        lineStyle: LightweightCharts.LineStyle.Dashed,
        priceLineVisible: false,
        lastValueVisible: false,
        crosshairMarkerVisible: false,
        priceFormat: { type: 'price', precision: 1, minMove: 0.1 }
      });
      factorLabels.forEach((factorLabel) => {
        const button = document.createElement('button');
        button.className = 'factor-tab';
        button.type = 'button';
        button.dataset.factor = factorLabel;
        button.setAttribute('role', 'tab');
        button.setAttribute('aria-selected', 'false');
        button.style.setProperty('--factor-color', factorColorByLabel.get(factorLabel) || factorPalette[0]);
        button.textContent = factorLabel;
        button.addEventListener('click', () => selectFactor(factorLabel));
        factorTabsElement.appendChild(button);
      });
      selectFactor(factorLabels[0]);
      charts.push(factorChart);
    }
    const rangeOptions = [
      ['1M', 22], ['3M', 65], ['6M', 130], ['1Y', 252], ['全部', null]
    ];
    let selectedRange = '3M';
    const updateRangeButtons = () => {
      if (!rangeControlsElement) return;
      rangeControlsElement.querySelectorAll('button').forEach((button) => {
        button.setAttribute('aria-pressed', button.dataset.range === selectedRange ? 'true' : 'false');
      });
    };
    const applyRange = (label, bars) => {
      selectedRange = label;
      const start = bars === null ? 0 : Math.max(0, candleData.length - bars);
      const visibleRange = { from: start, to: candleData.length + 8 };
      charts.forEach((chart) => chart.timeScale().setVisibleLogicalRange(visibleRange));
      updateRangeButtons();
    };
    if (rangeControlsElement) {
      rangeOptions.forEach(([label, bars]) => {
        const button = document.createElement('button');
        button.className = 'range-button';
        button.type = 'button';
        button.dataset.range = label;
        button.setAttribute('aria-pressed', 'false');
        button.textContent = label;
        button.addEventListener('click', () => applyRange(label, bars));
        rangeControlsElement.appendChild(button);
      });
    }
    let syncingRange = false;
    charts.forEach((source) => {
      source.timeScale().subscribeVisibleLogicalRangeChange(() => {
        if (syncingRange) return;
        const visibleRange = source.timeScale().getVisibleRange();
        if (!visibleRange) return;
        syncingRange = true;
        charts.forEach((target) => {
          if (target !== source) target.timeScale().setVisibleRange(visibleRange);
        });
        syncingRange = false;
      });
    });
    const timeKey = (time) => {
      if (typeof time === 'string') return time;
      if (time && typeof time === 'object' && 'year' in time) {
        return [time.year, String(time.month).padStart(2, '0'), String(time.day).padStart(2, '0')].join('-');
      }
      return null;
    };
    const clearCrosshairs = () => {
      priceChart.clearCrosshairPosition();
      if (scoreChart) scoreChart.clearCrosshairPosition();
      if (factorChart) factorChart.clearCrosshairPosition();
    };
    const syncCrosshair = (param) => {
      if (syncingCrosshair) return;
      syncingCrosshair = true;
      const key = timeKey(param.time);
      if (!key) {
        clearCrosshairs();
        renderValues(latest);
        if (fillNoteElement) {
          fillNoteElement.textContent = '';
          fillNoteElement.title = '';
        }
        syncingCrosshair = false;
        return;
      }
      const candle = candleByTime.get(key);
      const score = alignedScoreByTime.get(key);
      const factor = selectedFactorByTime.get(key);
      if (fillNoteElement) {
        const isFilled = scoreFillData.some((point) => point.time === key) || selectedFactorFilledTimes.has(key);
        fillNoteElement.textContent = isFilled ? ' · 前值遞補' : '';
        fillNoteElement.title = isFilled ? '此日期的圖表數值沿用前一筆可用值。' : '';
      }
      if (candle) {
        priceChart.setCrosshairPosition(candle.close, param.time, candles);
        renderValues(candle);
      } else {
        priceChart.clearCrosshairPosition();
      }
      if (scoreChart && scoreSeries && score !== undefined) {
        scoreChart.setCrosshairPosition(score, param.time, scoreSeries);
      } else if (scoreChart) {
        scoreChart.clearCrosshairPosition();
      }
      if (factorChart && factorSeries && factor !== undefined) {
        factorChart.setCrosshairPosition(factor, param.time, factorSeries);
      } else if (factorChart) {
        factorChart.clearCrosshairPosition();
      }
      syncingCrosshair = false;
    };
    priceChart.subscribeCrosshairMove(syncCrosshair);
    if (scoreChart) scoreChart.subscribeCrosshairMove(syncCrosshair);
    if (factorChart) factorChart.subscribeCrosshairMove(syncCrosshair);
    const initialRange = { from: Math.max(0, candleData.length - 65), to: candleData.length + 8 };
    priceChart.timeScale().setVisibleLogicalRange(initialRange);
    const initialVisibleRange = priceChart.timeScale().getVisibleRange();
    if (scoreChart && initialVisibleRange) {
      scoreChart.timeScale().setVisibleRange(initialVisibleRange);
    }
    if (factorChart && initialVisibleRange) {
      factorChart.timeScale().setVisibleRange(initialVisibleRange);
    }
    updateRangeButtons();
  </script>
</body>
</html>
"""
    )


def render_history_charts(
    store: DashboardDataStore,
    latest_score: dict | None = None,
    score_rows: object | None = None,
) -> None:
    """Render read-only trend views from persisted rows only."""

    st.header("歷史趨勢")
    if score_rows is None:
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

    factor_frame = factor_history_frame(score_rows)
    factor_columns = [column for column in factor_frame.columns if column != "日期"]
    factor_plot = (
        factor_frame.dropna(subset=factor_columns, how="all")
        if factor_columns
        else pd.DataFrame()
    )

    st.subheader("台灣加權指數 · Market Score")
    kline_html = build_tradingview_kline_html(
        ohlc,
        score_plot,
        factor_plot,
        latest_score,
        FACTOR_EXPLANATIONS,
    )
    if kline_html is None:
        st.info("目前沒有可繪製的 TAIEX OHLC 資料。")
    else:
        components.html(kline_html, height=1320, scrolling=False)
        st.caption(
            "操作：可用 1M／3M／6M／1Y／全部切換期間；滑鼠滾輪縮放，按住滑鼠左鍵左右拖曳；K 線、Market Score 與選定因子共用日期游標，各副圖 Y 軸依目前可見資料自動調整。"
        )
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
    if factor_plot.empty:
        st.info("目前沒有可繪製的 available 因子分數；缺值不會被當成 0。")
    elif factor_columns:
        st.caption("因子分頁已整合至上方圖表；切換因子後會保留日期範圍並同步十字游標。")


def render_score(record: dict | None, score_rows: object = ()) -> None:
    if record is None:
        st.info("尚無 Market Score（empty）。請由既有評分流程寫入結果後重新整理。")
        return
    status = record.get("status", "unavailable")
    score = display_score(record.get("score"), status)
    headline = (
        record.get("direction") if score != "unavailable" else "Market Score 尚不可用"
    )
    delta = previous_score_delta(record, score_rows)
    st.subheader("台灣加權指數 · Market Score")
    summary_columns = st.columns([1.2, 1, 1, 1])
    with summary_columns[0]:
        st.metric(
            "Market Score",
            score,
            delta=(f"{delta:+.1f}" if delta is not None else None),
        )
        if score == "unavailable":
            reason = str(record.get("reason") or "目前缺少必要因子資料")
            warning_title = f"資料品質需要注意：{reason}；請聯繫開發者。"
            st.markdown(
                '<div class="score-warning" title="{}">{}</div>'.format(
                    escape(warning_title),
                    WARNING_ICON_SVG + " <span>資料品質需要注意</span>",
                ),
                unsafe_allow_html=True,
            )
    with summary_columns[1]:
        st.metric("市場狀態", headline or "未記錄")
    with summary_columns[2]:
        st.metric("資料截至", record.get("target_date") or "未記錄")
    with summary_columns[3]:
        st.metric("模型版本", record.get("model_version") or "未記錄")
    st.caption("日變化比較上一個有有效 Market Score 的日期；資料截至只顯示交易日期。")
    if record.get("reason"):
        st.caption(f"評分狀態：{record['reason']}")


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
    st.markdown(SOURCE_ATTRIBUTION)
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
            latest_score = None
            try:
                latest_score = store.get_latest_market_score()
            except READ_ERRORS:
                st.error(
                    "無法讀取 Market Score。請維護者確認 market_scores 表、Data API 權限與網路連線。"
                )
            try:
                score_rows = store.get_market_score_history(limit=CHART_LIMIT)
            except READ_ERRORS:
                score_rows = []
                st.warning("無法讀取 Market Score 歷史，日變化與趨勢可能暫時無法顯示。")
            render_score(latest_score, score_rows)
            try:
                render_history_charts(store, latest_score, score_rows)
            except READ_ERRORS:
                st.warning("歷史趨勢暫時無法顯示；最新分數與來源狀態仍可查看。")
            try:
                with st.expander("資料來源狀態", expanded=False):
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
