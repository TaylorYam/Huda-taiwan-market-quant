# Phase 1 Storage Interface v0.1

- 狀態：Draft implementation boundary
- 日期：2026-09-16
- 追蹤：[Issue #12](https://github.com/TaylorYam/Huda-taiwan-market-quant/issues/12)

Phase 1 以 `SQLiteObservationStore` 實作 [ADR 0001](adr/0001-phase-1-storage-boundary.md) 的本機開發邊界。收集器與因子層只依賴 `ObservationStore` 介面及 `Observation` 信封，不直接組 SQL 或管理 SQLite connection。

## Observation 信封

`Observation` 對應 [Data Contract v0.1](data-contract-v0.1.md) 的共同欄位：資料集、交易日、官方原始來源日期／URL／列鍵、發布與有效時間、擷取／寫入時間、來源版次、64 位十六進位 payload SHA-256、parser 版本、JSON `values`、品質狀態與稽核備註。`source_date` 保留官方原字串；只有 `observation_date` 正規化為交易日。`values` 保持來源單位，空值由 `quality_status` 與 `quality_notes` 說明，不補成 0 或中性分數。

時間驗證規則為：`observation_date` 使用 `YYYY-MM-DD`；`source_date` 保留非空官方格式；`retrieved_at`／`ingested_at` 必須含時區且為 UTC；其他來源時間若存在也必須含時區。

## 寫入語義

`SQLiteObservationStore.write_observation()` 以以下欄位組成 logical identity：

版本識別使用 `dataset_id + observation_date + source_record_key + publication_label + source_revision`；修訂 lineage 的基礎識別則保留前四欄，讓不同 `source_revision` 能以 `supersedes_id` 串接。

- 同一 identity 與相同 payload hash 重跑時回傳既有 ID，增加 `retrieval_count` 並以時間較晚者更新 `last_retrieved_at`。
- 同一版本 identity 但 payload 改變時，呼叫端必須明確提供 `supersedes_id`；儲存層追加新列，不覆寫舊值。
- 新 `source_revision` 也可追加版本，但已有同一資料集／日期／列鍵／publication label 的版本時必須提供 `supersedes_id`；它必須指向同一 lineage。不存在或跨資料集／日期／列鍵的指向會拒絕。
- 七個 `quality_status` 使用資料契約的封閉集合。不可用狀態仍保存觀察信封，但不會產生有效數值的假替代。

資料庫預設路徑為 `data/market.sqlite3`，並由 `.gitignore` 排除。CSV／Parquet 與 GitHub Actions artifacts 仍是匯出或短期除錯用途，不是 Phase 1 的第二寫入真相。

## 尚未包含的範圍

- 每次 HTTP retry 的完整 retrieval event（目前先以 `retrieval_count` 與 `last_retrieved_at` 保留最小稽核資訊）。
- factor results、Market Score、CSV 匯出與正式排程的外部持久化服務。
- 原始 payload 內容保存；是否保存由來源授權及後續 Accepted ADR 決定，目前只保存 payload hash 與欄位稽核資訊。

以上項目要在新增資料來源或啟用正式排程前另立 Issue／ADR，不得繞過目前的 observation contract。
