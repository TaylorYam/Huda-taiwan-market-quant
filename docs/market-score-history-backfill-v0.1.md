# Market Score 歷史回補 v0.1

`scripts/backfill_market_scores.py` 會把已保存的日資料逐日重播成
Market Score，讓 dashboard 的 Market Score 與各因子趨勢圖有歷史曲線。

## 回補規則

- 每個交易日都使用 `src.backtest.layer1.build_score_series`，只讓該日及之前的
  `observation_date` 進入計算；有 `published_at` 的資料也必須在該日以前已發布。
- 缺資料會保留為 `unavailable`，不會用 0 或中性分數補齊。圖表會保留日期狀態，
  但只畫 `available` 的數值。
- 回補會先查詢同一 `model_version`、同一日期範圍已存在的 Market Score。已有結果
  的日期會跳過，以免歷史重播產生另一個 hash 後遮住正式的即時結果。
- 預設是 dry run；只有 workflow 的 `write=true` 才會寫入 Supabase。
- `refresh_unavailable=true` 會保留既有的 available 結果，只重新計算既有的
  unavailable 日期；回放摘要會列出缺少的因子與最多 10 筆日期診斷。

## 執行方式

GitHub Actions → **Market Score range backfill** → Run workflow，輸入例如：

```text
start_date: 2023-09-18
end_date: 2026-09-17
write: false
```

先看 dry run 的 `available_days`、`unavailable_days` 與 `reason_counts`。確認範圍
後再以相同日期執行 `write: true`。目前 dashboard 最多讀取 1000 筆，足以涵蓋本次
725 個交易日的資料窗口。2026-09-21 的展示回放寫入 724 個可用日期；2023-09-25
因官方法人 OI rolling window 沒有更早資料，保留為 unavailable，不用虛構前值。

這是展示用的歷史重播。資料窗口政策目前仍標示 3 年百分位暖機尚未完成，因而這些
結果不能當作正式回測有效性證據；正式回測仍須等暖機與 forward window 條件滿足後
再執行 `scripts/run_backtest_layer1.py`。
