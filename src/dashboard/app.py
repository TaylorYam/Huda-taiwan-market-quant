"""Read-only Streamlit dashboard; all Supabase access runs on the server."""

from __future__ import annotations

import os
from datetime import datetime
from math import isfinite
from urllib.parse import urlsplit

import streamlit as st
from requests.exceptions import RequestException

from src.dashboard.data import DashboardDataStore
from src.dashboard.view_model import FACTOR_CATEGORIES, FACTOR_LABELS

SOURCE_DATASETS = {
    "twse_taiex_daily_v1": "TWSE 加權指數",
    "taifex_institutional_futures_oi_v1": "TAIFEX 法人期貨部位",
    "taifex_tx_daily_contract_v1": "TAIFEX 台指期行情",
    "taifex_txo_oi_pcr_v1": "TAIFEX OI PCR",
    "taifex_taiwan_vix_close_v1": "TAIFEX Taiwan VIX",
}

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


def factor_rows(record: dict) -> list[dict]:
    factors = record.get("factor_scores_json") or {}
    return [
        {
            "分類": FACTOR_CATEGORIES.get(factor_id, "其他"),
            "因子": FACTOR_LABELS.get(factor_id, factor_id),
            "狀態": factors.get(factor_id, {}).get("status", "unavailable"),
            "分數": display_score(
                factors.get(factor_id, {}).get("score"),
                factors.get(factor_id, {}).get("status", "unavailable"),
            ),
            "原因": factors.get(factor_id, {}).get("reason")
            or ("未儲存此因子" if factor_id not in factors else "—"),
        }
        for factor_id in dict.fromkeys([*FACTOR_LABELS, *factors])
    ]


def render_score(record: dict | None) -> None:
    if record is None:
        st.info("尚無 Market Score（empty）。請由既有評分流程寫入結果後重新整理。")
        return
    status = record.get("status", "unavailable")
    score = display_score(record.get("score"), status)
    st.subheader(
        record.get("direction") if score != "unavailable" else "Market Score 尚不可用"
    )
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


def render_sources(store: DashboardDataStore) -> None:
    st.subheader("來源資料品質與更新")
    rows = []
    timestamps = []
    for dataset_id, label in SOURCE_DATASETS.items():
        row = store.get_latest_source_quality(dataset_id)
        if row and row.get("last_retrieved_at"):
            timestamps.append(
                datetime.fromisoformat(row["last_retrieved_at"].replace("Z", "+00:00"))
            )
        rows.append(
            {
                "來源": label,
                "資料日期": row.get("observation_date") if row else "—",
                "紀錄": row.get("source_record_key") if row else "—",
                "品質狀態": row.get("quality_status") if row else "empty",
                "最後擷取時間": row.get("last_retrieved_at") if row else "未記錄",
                "品質說明": (row.get("quality_notes") or "—")
                if row
                else "尚無來源紀錄",
            }
        )
    st.text(
        f"來源資料最後更新時間：{max(timestamps).isoformat() if timestamps else '未記錄'}"
    )
    st.dataframe(rows, hide_index=True, width="stretch")
    st.caption(
        "每個來源僅列最近擷取的一筆紀錄，並非整批品質或分數使用證據。"
        "未寫入資料庫的失敗擷取不會出現在此；available 不代表資料仍新鮮，請核對日期。"
        "外資現貨來源契約尚未完成，未納入此來源清單。時間保留資料庫時區。"
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
    except ValueError:
        st.error("SUPABASE_URL 設定錯誤：請使用有效的 HTTPS 專案網址。")
        return
    if (
        parsed.scheme != "https"
        or not parsed.hostname
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
