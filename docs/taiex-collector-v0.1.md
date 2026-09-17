# TAIEX Collector v0.1

- 狀態：Phase 1 implementation
- 日期：2026-09-16
- 追蹤：[Issue #14](https://github.com/TaylorYam/Huda-taiwan-market-quant/issues/14)

`src/data/twse_taiex.py` 使用 TWSE `MI_5MINS_HIST` 月查詢 JSON，將官方每日開／高／低／收指數轉成 `twse_taiex_daily_v1` observation。`collect_taiex_range()` 提供含起訖月份的按月回填。資料契約的交易日使用 ISO `YYYY-MM-DD`；TWSE 報表的原始日期（例如 `113/01/02`）保存在 `source_date`，不覆蓋來源字串。數值單位固定為 `index_points`。

每個月查詢的完整回應以 SHA-256 寫入 observation，parser 會驗證呼叫端提供的 hash 與回應一致。`publication_label` 使用 `month:YYYY-MM`，parser 會拒絕跨月或重複交易日；相同回應重跑由 SQLite store 去重。若同一月份來源內容修訂，呼叫端必須用 `supersedes_id` 追加新版本。解析失敗或 HTTP 失敗會拋出明確錯誤，收集流程不得寫入假數值。

這個收集器只處理 TAIEX OHLC。外資金額因子仍受 [Issue #5](https://github.com/TaylorYam/Huda-taiwan-market-quant/issues/5) 的 BFI82U／FMTQIK 版次與口徑缺口阻擋，不在此處拼接。
