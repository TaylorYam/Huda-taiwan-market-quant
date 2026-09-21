# Daily automation source matrix (v0.1)

盤點日期：2026-09-21。本文只盤點目前 workflow 與 `scripts/collect_*.py`，不改變
來源 parser 或 scoring 行為。每日排程集中在
`daily-market-automation.yml`，使用 16:30 與 22:00 Asia/Taipei（分別為
`30 8` 與 `0 14` UTC）；各來源 workflow 保留手動入口，不再各自排程。

## 目前入口

| 資料 | dataset / 官方入口 | 目前 workflow 與排程 | 手動參數與預設 | 交易日風險 | 重複／修訂風險 |
|---|---|---|---|---|---|
| TAIEX | `twse_taiex_daily_v1`；TWSE `MI_5MINS_HIST` 月查詢 | `.github/workflows/taiex-daily-ingestion.yml`；手動入口。每日排程由 `daily-market-automation.yml` 統一執行 | `year`、`month` 必須成對；省略時抓 Asia/Taipei 當月。`collect_taiex_month.py --dry-run` 可只驗證 | 月查詢通常會回傳當月已發布列；月初若尚無資料，parser 會失敗；資料發布延遲則會抓到不完整月份 | 每日重抓整個當月，已寫列會造成 retrieval count 增加；同一 payload 去重，修訂追加 revision |
| 外資現貨現金 | `twse_foreign_cash_bfi82u_v1`；TWSE BFI82U 日報 | `.github/workflows/twse-free-factor-daily-ingestion.yml`；手動入口。每日排程由整合流程執行 | `date` 可指定 `YYYY-MM-DD`；省略取當日 Asia/Taipei。回補 workflow 仍使用 `start`、`end`、`write` | 週末／台灣假日沒有日列；BFI82U 有發布版本／時間差，整合流程的 16:30／22:00 會分兩次確認 | 日列 label 為 `day:YYYY-MM-DD`，相同 payload 可去重；單一整合流程避免獨立排程競爭 |
| TWSE 市場成交金額 | `twse_market_turnover_fmtqik_v1`；TWSE FMTQIK 月報 | `.github/workflows/twse-free-factor-daily-ingestion.yml`；手動入口。每日排程由整合流程執行 | `year`／`month` 可指定月份；若只指定 `date`，workflow 會取該日期月份；回補 workflow 仍使用 `start`、`end`、`write` | 月初空報表、假日執行與報表發布延遲都可能使單次任務失敗或只得到不完整月份 | 每日重抓當月仍會增加 retrieval count；單一整合流程避免與獨立排程重複寫入 |
| TAIFEX TX | `taifex_tx_daily_contract_v1`；TAIFEX 日期查詢頁（年度 ZIP 僅作已結束年度回補） | `.github/workflows/taifex-tx-daily-ingestion.yml`；手動入口。每日排程由整合流程執行 | `date`；省略時抓 Asia/Taipei 當日。`collect_taifex_tx_day.py --dry-run` 可只驗證；年度 ZIP 另由 `collect_taifex_tx.py` 與 archive audit 使用 | 日期查詢遇到台灣假日或資料尚未發布時會回傳空列／失敗，不能把前一日冒充為今日 | 日級 label 為 `daily:YYYY-MM-DD:一般`；年度 ZIP 的 `year:YYYY` label 保留給歷史回補，不在每日工作流混用 |
| 外資台指期 OI | `taifex_institutional_futures_oi_v1`；TAIFEX OpenAPI latest snapshot | `.github/workflows/taifex-institutional-daily-ingestion.yml` **只有手動 dispatch**，沒有 schedule。`write` 必填但預設 `false` | `write=true` 才執行 `collect_taifex_institutional --write`；不帶 `--write` 只讀驗證。沒有日期參數，永遠抓官方 latest。另有 `taifex-range-backfill.yml` 的 `start`、`end`、`write` | 假日仍可能回傳上一交易日；collector 沒有「應為今日」檢查，因此可靜默保存 stale 的 source date。OpenAPI 是最新快照，不是日期查詢 | latest collector label 為 `latest`；rolling-range backfill label 為 `day:YYYY-MM-DD`。同一交易日由兩條入口寫入時，Supabase identity 不相同，會留下語意重複列；需統一入口或在寫入前明確排除交集 |
| TXO PCR／OI PCR | `taifex_txo_oi_pcr_v1`；TAIFEX PCR 日期表單 | `.github/workflows/taifex-pcr-daily-ingestion.yml`；手動入口。每日排程由整合流程執行 | `date`；省略時取當日 Asia/Taipei。`collect_taifex_pcr.py --dry-run` 可只驗證 | 台灣假日（即使是平日）沒有該日期資料，parser 會失敗；整合流程會在 16:30／22:00 依序重試 | label 為 `day:YYYY-MM-DD`；相同 payload 去重，內容修訂追加 revision |
| Taiwan VIX | `taifex_taiwan_vix_close_v1`；TAIFEX `log2data/YYYYMMnew.txt` 月檔 | `.github/workflows/taifex-vix-daily-ingestion.yml`；手動入口。每日排程由整合流程執行 | `year`、`month` 必須成對；省略時抓 Asia/Taipei 當月。`collect_taifex_vix_month.py --dry-run` 可只驗證 | 月檔會包含當月已發布交易日；假日仍會重抓。月初沒有列時 parser 可能失敗；VIX 的 rolling-range 回補是另一個手動入口 | 月 collector label 為 `month:YYYY-MM`；整合流程統一每日寫入入口，避免和日級回補形成排程競爭 |

另外，`daily-market-score.yml` 保留手動入口，要求 `target_date` 與 `as_of`，作為人工重算／診斷用途；正式每日排程由 `daily-market-automation.yml` 在七個來源完成後直接執行評分。

## 共通寫入行為

七個 collector 最終都透過 `SupabaseRestObservationStore` 寫入 observation。精確
重跑的 identity 包含 dataset、交易日、source record key、publication label、
source revision 與 payload hash；因此同一 payload 通常回報 `duplicate` 並增加
`retrieval_count`，不會增加第二筆相同 payload。來源內容改變時，collector 會把
上一筆列放入 `supersedes_id`，追加一筆 revision。這保護了可追溯性，但不能取代
跨入口的 logical identity 設計：例如 institutional 的 `latest` 與 `day:date`、
VIX 的 `month:month` 與 `day:date` 會被視為不同列。

每日來源 workflow 不再各自排程；整合流程用單一 concurrency group 串行收集七個
來源後才評分。手動 collector、區間回補與手動 Market Score 仍沒有跨 workflow
共用鎖，因此操作時仍應避免和每日整合流程同時寫入。Supabase 的單列去重可降低
重複列，卻不能取代這項操作約束。

## 可直接整合的排程建議

1. 將七個來源與 Market Score 視為一個每日 run；由一個 orchestrator 在所有來源
   完成後才執行評分。若保留現有 workflow，至少要把 score job 改成依賴所有來源
   job，而不是讓使用者手動輸入 `target_date`／`as_of` 來猜測完成時間。
2. 排程時間應以最晚官方發布時間為準，並用 Asia/Taipei 的交易日規則決定目標日。
   現有 16:00 Taipei 的 `0 8 UTC` 應視為偏早的候選時間；建議在正式啟用前以連續
   交易日觀測各來源，選定足以涵蓋 BFI82U 最終版、TAIFEX PCR、TX 與 VIX 的時間，
   再把 UTC cron 固定下來。
3. 對 BFI82U、PCR 這類日查詢，不要把「今天沒有列」當成數值。先判定今天是否為
   官方交易日；非交易日時回報 skipped／unavailable，交易日但尚未發布則有限次重試，
   仍失敗就讓該來源失敗並阻止發布完整 score。institutional latest 則要檢查
   回應的 `source_date` 新鮮度，不能因 endpoint 成功就當成今日資料。
4. TX 目前年度應使用官方日期查詢／日級 collector，年度 ZIP 只作已結束年度回補。
   在日級入口整合前，應停用或改為只在年度檔可用時執行的 current-year annual
   schedule，避免每個平日都得到可預期的 2026 ZIP 失敗。
5. TAIEX、FMTQIK、VIX 現有腳本是「整月」收集器；若每日呼叫，功能上可依賴 hash
   去重，但會反覆讀取並更新整月 retrieval count。短期可接受並設 run summary，長期
   應提供以明確交易日為目標的增量入口，或只在月檔更新／回補時執行月收集器。
6. 統一 daily 與 backfill 的 publication label／logical key。尤其 institutional
   及 VIX 必須決定以 `day:YYYY-MM-DD` 或月／latest label 為正式序列，否則 coverage
   與 dashboard 會同時看到兩筆看似相同的資料。backfill 與 daily 不應在同一時間窗
   寫入同一來源；現有各自 concurrency group 不足以防止這種跨 workflow 競爭。
7. 每次 run 的摘要至少要列出每個 dataset 的 requested target、source_date、
   action（inserted／duplicate／revision）、quality status、缺日／stale 原因及
   最後可用日期。只有七源都通過交易日、日期新鮮度與品質閘門，才啟動
   `daily-market-score`；否則保留上一筆資料並明確標示本日 score unavailable。

## 優先缺口

- **P0：** 外資現貨與 FMTQIK 已有合併每日 workflow；institutional 仍沒有獨立排程且預設只讀。
  TX 獨立每日工作流已改用日期查詢；年度 ZIP 僅保留給已結束年度回補。
- **P0：** PCR／外資現貨的「當日日期」預設在台灣假日會失敗；institutional latest
  在假日則可能成功但保存 stale source date。兩者都需要交易日／新鮮度閘門。
- **P1：** 手動 collector、區間回補與手動 score 仍沒有跨 workflow 的完成順序；
  需要操作紀律避免和整合流程同時寫入。
- **P1：** 月 collector 的每日整月重抓造成寫入與 API 放大；VIX／institutional
  月／latest 與 rolling-range 的 publication label 不一致，存在語意重複列。

本文沒有新增 workflow，也沒有修改 `src/data` 或 scoring；它可作為整合每日流程時
逐項決定入口、目標日期與寫入 identity 的驗收清單。
