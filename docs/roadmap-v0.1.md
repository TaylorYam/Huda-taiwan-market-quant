# Development Roadmap v0.1

本路線圖把 README、架構、因子模型、資料窗口、資料可用性探測與回測規格中的後續方向整理成有依賴關係的工作項目。此文件是執行順序與 Issue 草案索引；不取代版本化因子模型，也不代表已批准付費資料或已建立 GitHub Issues。

## 規格來源

- [Factor Model v0.1](factor-model-v0.1.md)：8 個核心因子、權重與初始評分定義，是模型行為的唯一來源。
- [Data Availability Probe v0.1](data-availability-probe-v0.1.md)：官方來源、已驗證窗口與尚未確認的資料缺口。
- [TWSE 現貨口徑補查](phase0-cash-market-scope-v0.1.md)：BFI82U／FMTQIK 樣本範圍、E-Shop 版次差異及未解問題。
- [TWSE 現貨金額因子來源查證](phase0-cash-factor-source-verification-v0.1.md)：核對起始日附近的實際報表、交易範圍差異及仍未知的檔案版次映射。
- [TAIFEX 歷史窗口補查](phase0-taifex-history-v0.1.md)：PCR 日期回補窗口、TX 年行情 ZIP 樣本全檔稽核、VIX 免費查詢窗口與法人 OI 公開窗口。
- [Phase 1 儲存方案評估](data-storage-options-v0.1.md)：本機開發與正式排程持久化的比較；本機 SQLite 邊界見 [ADR 0001](adr/0001-phase-1-storage-boundary.md)。
- [Phase 1 Storage Interface](storage-interface-v0.1.md)：SQLite observation schema、冪等重跑與追加修訂的實作契約。
- [Production Persistence Decision](production-persistence-decision-v0.1.md)：正式排程持久化的候選類型、驗收證據與 Accepted ADR 閘門。
- [TAIEX Collector v0.1](taiex-collector-v0.1.md)：TWSE 月查詢 JSON 到 TAIEX 日 OHLC observation 的解析與寫入邊界。
- [Data Window Policy v0.1](data-window-policy-v0.1.md)：共同歷史起點、暖機期與回測期間原則。
- [Backtest Spec v0.1](backtest-spec-v0.1.md)：as-of、未來報酬、兩層回測及驗證標準。
- [Architecture Overview](architecture.md)：資料收集、因子、評分、回測與展示的模組邊界。

## 執行順序

```text
資料口徑與歷史窗口決策
    → 可重現的資料收集與保存
    → 因子與總分
    → 分數辨識力回測
    → Dashboard 與每日自動執行
    → 通過驗證後才做策略層回測
```

### Phase 0 — 關閉資料與模型定義缺口

先解決會影響資料格式、因子單位或共同回測區間的問題。這些工作不需要付費即可先調查；任何訂閱或歷史資料購買仍須另行決定。

1. **外資現貨來源口徑已完成 v0.1 查證。** 免費 BFI82U／FMTQIK 的可用版本與交易範圍已記錄，`FOREIGN_CASH_VERIFIED_START` 設為 2010-01-01；計算仍要求兩個來源都有完整 5 個交易日窗口，不得以 T86 股數或零值替代。歷史更早的版次差異與來源授權仍保留在文件中。
2. **補完歷史窗口探測。** PCR 日期表單已完成 292 段全期稽核，回傳 6,090 個唯一日期；仍需用完整交易日曆解釋無資料日。TX 年檔 1998–2025 已完成 28 份全檔稽核；1998 官方交易日曆與 2026 年度檔仍未知，但 2026 年已由官方日期查詢頁補回。VIX、法人 OI 與 TX 2026 日級資料均已回補，並通過 Supabase 覆蓋率報告；共同原始起點為 2023-09-18。詳見[TAIFEX 歷史窗口補查](phase0-taifex-history-v0.1.md)。
3. **定義資料契約及保存方式。** [`data-contract-v0.1.md`](data-contract-v0.1.md) 已建立邏輯欄位、日期時區、單位、契約、盤別、發布時間、來源、修訂與缺值語義；[ADR 0001](adr/0001-phase-1-storage-boundary.md) 已確認 Phase 1 單機開發使用 Git 忽略的 SQLite。免費 MVP 的正式持久來源、傳輸與展示層由 [ADR 0002](adr/0002-free-tier-mvp-stack.md)、[ADR 0003](adr/0003-supabase-data-api-transport.md) 與 [ADR 0004](adr/0004-streamlit-demo-hosting.md) 記錄；正式無人值守每日流程仍須完成備份、還原、權限與配額驗證。
4. **模型邊界已落入實作與測試。** PCR 百分位方向、Basis 近月／轉倉規則、VIX 歷史窗口、必要因子缺值與 Market Score 區間端點均已在模型規格、評分程式與回測測試中固定；後續只可透過新模型版本調整。

**Phase 0 完成條件：** 核心欄位及單位已定義；每個必要資料源有可重現的最新查詢方式與已驗證的歷史下界；付費項目與授權限制標示清楚；模型邊界決策已記錄；未知項目不再被當成已確認假設。

### Phase 1 — 資料收集與歷史資料層

- 分別建立 TWSE 與 TAIFEX client，已完成 TAIEX、外資現貨、TX 行情、法人期貨 OI、PCR、VIX 的讀取和解析，並提供 VIX／法人 OI 一次性日期回補入口。
- 保存原始來源、交易日期、擷取時間、發布時間、單位與契約／盤別；把逐日增量更新設計成可重跑、可去重，並保留修訂痕跡。
- 建立交易日、重複列、缺欄、空值、日期不一致及資料過期檢查。來源失敗或資料尚未發布時標示 unavailable，不產生看似有效的分數。
- 對有限制的 TAIFEX 最新快照建立累積式資料流程；不得把只回最新資料的 OpenAPI 當成歷史回補 API。

**Phase 1 完成條件：** 使用一個明確日期範圍可以回填或載入資料；相同輸入重跑不會重複資料；每份資料可追到官方來源和擷取時間；品質報告能指出缺日及原因。

### Phase 2 — 因子、評分與市場狀態

- 按版本模型實作 8 個因子；MA20/MA60 與 20 日動能共用 TAIEX。保留因子原值、單位、分數及該分數採用的觀察窗口。
- 歷史百分位只用當日可知的過去資料；現貨 5 日比例、期貨淨部位及其 5 日變化、Basis 的交易日和合約處理方式均由規格固定。
- 套用權重並輸出分類分數、Market Score、狀態標籤及可讀理由。分數區間端點必須互斥且涵蓋 0–100；缺少必要因子時，不能默默當成 50 分或自動改權重。
- 加上邊界、非交易日、缺值、過期、合約轉換和 as-of 測試。先做核心計算測試，再做 Dashboard 測試。

**重要範圍界線：** RSI 不在目前 v0.1 八因子中；原始構想中的「RSI 與均線」Issue 應拆成均線屬 v0.1、RSI 留待新模型版本評估。投信、自營商、融資融券、Call Wall / Put Wall 可作輔助顯示，暫不進入總分。

### Phase 3 — 先驗證分數，再評估策略

1. 第一層回測已實作：每日分數對 TAIEX 未來 5／10／20 個交易日報酬，輸出五個分數區間的樣本數、平均／中位報酬、上漲比例及報酬分布；價格錨點、revision as-of 與 look-ahead 防護已納入測試。正式結論仍等待足量真實歷史資料。
2. 按資料量切分開發、驗證與 Out-of-Sample 區間；百分位逐日只看當時以前的資料。檢查高低分差異、分數單調性、不同市場環境及有效樣本數；不可用保留的 OOS 結果反覆調參。
3. 只有分數排序能力達到 [Backtest Spec](backtest-spec-v0.1.md) 的標準後，才做第二層模擬部位回測，並加入手續費、稅、滑價與期貨換月成本，對照 Buy & Hold。

**Phase 3 完成條件：** 報告列明模型版本、資料期間、暖機期、樣本數、缺值處理、資料發布時間規則、切分方式、5／10／20 日結果與限制；若未通過標準，產出有證據支持的模型修訂或停止結論，而不是直接進入實盤。

### Phase 4 — Dashboard、每日自動化與維運

- Dashboard 已顯示最新可用 Market Score、狀態、分類分數、因子證據、as-of 日期、資料最後更新時間及缺值／過期狀態；前端只呈現已計算的結果，不重算因子。
- 每日工作流程依 TWSE / TAIFEX 最終發布時間排程，以 Asia/Taipei 交易日處理資料；失敗時保留上一筆結果並明確標示舊資料，不能把舊資料當成今日分數。
- 擴充 CI：pytest、ruff 及資料／因子／評分邊界測試。排程部署前要確認 GitHub Actions 產物或資料庫的持久保存方式。
- Dashboard 使用 Streamlit Community Cloud 路線，入口與 port 設定已固定；外部部署 URL 與 server-side secret 驗收仍待操作者完成。
- 文字只描述市場狀態與支持它的因子證據；不輸出個人化買賣、進出場、商品選擇或部位建議。

**MVP 完成條件：** 每個有效交易日能重現資料更新、因子計算與結果頁；當必要來源缺失或過期時會顯示 unavailable／更新失敗，而不是發布錯誤總分；回測報告可用同一批已保存資料重跑。

### Phase 5 — v0.1 以外的擴充

- 先評估投信／自營商、融資融券、Call Wall / Put Wall 等輔助欄位是否增加解釋力，再決定顯示或納入新版本。
- RSI、KD、MACD 等重複型動能因子不直接疊加；若要加入，須有獨立假設、版本更新與 OOS 比較。
- Walk-forward、因子消融、交易成本敏感度與市場 Regime 分析，在基礎回測結果穩定後擴充；不在 v0.1 前置引入機器學習。

## GitHub Issue 草案

以下工作項目使用 `.github/ISSUE_TEMPLATE/task.md` 的格式；Phase 0 第一項已由 [Issue #5](https://github.com/TaylorYam/Huda-taiwan-market-quant/issues/5) 完成，第二項已建立為 [Issue #7](https://github.com/TaylorYam/Huda-taiwan-market-quant/issues/7)，其他項目仍是草案。重大資料保存或部署選擇套用 ADR proposal，按依賴順序逐項開 Issue。

| 順序 | Issue 標題 | 驗收條件 | 依賴 |
|---:|---|---|---|
| 1 | [#5 驗證外資現貨 5 日因子的金額來源與交易口徑](https://github.com/TaylorYam/Huda-taiwan-market-quant/issues/5) | 審閱[現貨口徑補查](phase0-cash-market-scope-v0.1.md)；驗證免費 BFI82U 起始附近查詢、版次／分類及逐日完整性，按合法可用樣本核對金額與 FMTQIK 分母；未解前保留版次欄位，不拼接異質序列 | Data Availability Probe、Phase 0 Source Research |
| 2 | [#7 補完 TAIFEX PCR、TX 行情與 VIX 歷史窗口探測](https://github.com/TaylorYam/Huda-taiwan-market-quant/issues/7) | 審閱[TAIFEX 歷史窗口補查](phase0-taifex-history-v0.1.md)；PCR 每段起訖相差最多 30 個曆日（含端點）並比對交易日；盤點官方 TX ZIP 年檔；驗證 VIX 免費日收盤頁與日級查詢窗口；未能驗證的項目保留未知 | Data Availability Probe、Phase 0 Source Research |
| 3 | [#9 決定 Phase 1 資料保存方案（ADR）](https://github.com/TaylorYam/Huda-taiwan-market-quant/issues/9) | 提交欄位／主鍵／時間語義／單位／修訂規則；審閱 [儲存方案比較](data-storage-options-v0.1.md) 與 [ADR 0001](adr/0001-phase-1-storage-boundary.md)；已確認被 Git 忽略的 SQLite 作為本機開發預設，正式每日排程前仍須選定持久化技術並新增 Accepted ADR | Issue 1–2 |
| 4 | [#12 建立 Phase 1 SQLite storage interface 與 schema](https://github.com/TaylorYam/Huda-taiwan-market-quant/issues/12) | observation envelope 可寫入；相同 payload 冪等；修訂追加並以 `supersedes_id` 追溯；不可用狀態不補值；SQLite 細節隔離於介面 | Issue 3 |
| 5 | [#14 建立 TAIEX 日行情收集器](https://github.com/TaylorYam/Huda-taiwan-market-quant/issues/14)（已合併） | 支援月查詢回填；保留官方原始日期、OHLC、單位、來源 URL、payload hash；錯誤不寫成有效觀察值；相同輸入可重跑 | Issue 3、4 |
| 6 | 建立外資現貨收集器（已合併） | BFI82U／FMTQIK 版次與交易口徑已通過 Issue #5 閘門；支援回填及單日更新；錯誤不寫成有效觀察值 | Issue 1、3、4 |
| 7 | 建立 TAIFEX TX、法人部位、PCR、VIX 收集器（已合併） | TX、PCR、VIX 日級入口與法人 OI／VIX 日期回補入口已合併；保留契約、交易時段、OI、來源 payload 與修訂關係 | Issue 2–4、6 |
| 8 | 建立資料品質報告與交易日覆蓋檢查（已合併） | 顯示各來源 earliest/latest、missing ratio、重複列、stale 狀態與失敗原因；未有官方日曆時保留 unknown | Issue 5–7 |
| 9 | 實作 v0.1 因子計算與必要測試（已合併） | 8 因子按版本規格計算；rolling/as-of、窗口暖機、basis 合約、缺值與邊界均有測試 | Issue 4–8、模型邊界決策 |
| 10 | 實作 Market Score 與市場狀態標籤（已合併） | 權重來自單一設定；分數區間互斥；缺必要因子不產生完整總分；輸出分項與解釋 | Issue 9 |
| 11 | 建立第一層分數辨識力回測（程式已合併） | 輸出 5／10／20 日分組統計、單調性、期間切分與限制；定義預測報酬價格錨點；無 look-ahead | Issue 8–10 |
| 12 | 評估 v0.1 並決定是否進入策略層 | 對照成功標準，提交保留／修訂／停止結論；只有通過後才開策略層回測 | Issue 11 |
| 13 | 建立 Dashboard MVP（已合併） | 顯示 score、狀態、因子證據、as-of／更新時間及 unavailable；展示層不計分；Streamlit 啟動設定與 port 一致 | Issue 10–11 |
| 14 | 建立 CI 與每日更新工作流程（已合併） | CI quality/tests 與 patch whitespace 已分線；TAIEX、VIX、PCR、TX、法人 OI 已有每日或手動入口；正式無人值守仍須通過 Supabase migration、備份與權限驗證 | Issue 5–10、13、18 |

## 目前狀態

- **已完成文件基礎：** 目標／架構、factor model、data window policy、backtest spec、第一輪 data availability probe。
- **儲存方案與介面：** 已比較本機 SQLite、CSV／Parquet、Git、Actions artifacts 與外部持久服務；[ADR 0001](adr/0001-phase-1-storage-boundary.md) 已接受 SQLite 作為 Phase 1 本機開發預設，[Issue #12](https://github.com/TaylorYam/Huda-taiwan-market-quant/issues/12) 已合併 observation interface 與 schema。[正式持久化決策矩陣](production-persistence-decision-v0.1.md) 已列出驗收條件；[ADR 0002](adr/0002-free-tier-mvp-stack.md)、[ADR 0003](adr/0003-supabase-data-api-transport.md) 與 [ADR 0004](adr/0004-streamlit-demo-hosting.md) 已記錄免費持久化、傳輸與展示路線；[Issue #18](https://github.com/TaylorYam/Huda-taiwan-market-quant/issues/18) 仍追蹤正式維運驗證。
- **Phase 0 進度：** Issue #5 的 BFI82U／FMTQIK 口徑查證已完成，外資現貨因子可從 2010-01-01 起計算；Issue #7 的 PCR 與 TX 年檔稽核已完成，VIX／法人 OI／TX 2026 日級資料與免費因子資料已實際回補並通過覆蓋率報告。八個資料源的共同原始起點為 2023-09-18；三年百分位的最早暖機日為 2026-09-18，因此正式 Layer 1 回測尚未就緒。
- **程式狀態（2026-09-18 更新）：** 已有 SQLite observation interface、schema、冪等與 revision 測試，TAIEX、VIX、PCR、TX、外資現貨與法人期貨 OI 的官方日級入口與回補工具，以及 Supabase Data API 寫入。8 個核心因子、Market Score、point-in-time 歷史百分位、Layer 1 回測引擎與 Streamlit 唯讀 Dashboard 均已實作；回測仍缺足量真實歷史資料以產出正式辨識力結論。
- **下一個工作包：** 先完成 Streamlit 公開展示部署與驗收，讓使用者能查看最新已儲存結果、因子狀態與來源品質；展示版穩定後，再處理每日資料更新與正式無人值守流程。#18 的備份／還原、權限分離、配額與來源條款驗證排到最後。資料窗口跨過三年百分位暖機、且 forward window 有足夠後續日期後，才產出 Layer 1 真實資料報告。
- **GitHub Issue 狀態：** Issue #5、#12、#14、#24 已完成並關閉；目前開啟的後續項目為 Issue #7、#9 與 #18。#9 的 Phase 1 邊界已由 ADR 0001 接受，正式排程持久化改由 #18 追蹤。Roadmap 其他工作項目仍是草案，不代表已建立 GitHub Issues。
