# TAIFEX 歷史資料邊界補查 v0.1

查核日期：2026-09-17（Asia/Taipei）
範圍：Phase 0 Issue 2 的 TXO Put/Call Ratio（PCR）歷史查詢、TAIFEX 年度 TX 行情 ZIP、Taiwan VIX 免費查詢窗口，以及三大法人期貨未平倉資料的公開查詢窗口與歷史資料申請路徑。
來源：TAIFEX 官方頁面與檔案。只整理日等級資料；未購買或申請任何資料。

## 結論

| 項目 | 已驗證 | 邊界／待查 |
|---|---|---|
| TXO PCR | 官方日期表單 POST 可按日期下載；完整分段稽核已覆蓋 2001-12-24 至 2026-09-17：292 段、6,090 列、6,090 個唯一日期、0 錯誤、0 重複；最新資料日為 2026-09-16。 | 起訖日期相差最多 30 個曆日且兩端包含（每段最多 31 個曆日）。本次已確認來源窗口連續回應且日期不重複，但尚未用完整官方交易日曆逐日判定所有無資料日的原因。 |
| TX 年行情 | 官方年度選單列出 1998–2025 共 28 年；完整稽核 28 份 ZIP 共 84,828 筆 TX 列、6,819 個年度日期、0 個年度內重複鍵，所有年度每個 TX 日期都有正成交量列。1998 首末資料日為 1998-07-21–12-31；2025 最新年檔為 2025-01-02–12-31。2026 年則由官方日期查詢頁補回 2026-01-01–09-17 的 172 個交易日。 | 全檔稽核確認 CP950 解析、年度首末日與 schema 轉換；1998 官方歷史交易日曆仍未取得，因此不能只靠檔案判定逐日缺漏，也不能把年度日期數直接當成交易日曆。2026 年度 ZIP 尚未列出，但現行回補已由日期頁補齊至覆蓋率報告終點。 |
| Taiwan VIX 日收盤 | 免費每日收盤頁顯示 2026/06–09 月份；月檔 `202609new.txt` 實測含 2026-09-15 日列，VIX 收盤 27.29、收盤前 1 分鐘平均 27.29。**2026-09-17 另實測指數專區背後的 `indes/index.aspx/GetStockDayPrices` JSON API（`syid=TAIWANVIX`、`flag=MS`）可回補 2023 年 10 月整月每日收盤（例如 2023/10/02 = 13.99）**，證實 log2data 月檔以外還有可用的日期查詢端點。 | `GetStockDayPrices` 對 2010/01 回傳空陣列，確認查詢窗口約為當下往前 3 年（rolling），不是固定歷史起點；晚做回補會讓較舊的月份永久超出窗口。CSV／log2data 月檔仍只有近 3～4 個月，兩者是互補而非同一機制。付費歷史商品另列，不視為免費資料。 |
| 三大法人期貨 OI | 官方「區分各期貨契約－依日期」頁註明資料起日 2008-04-07，且自 2012-05-01 起只供查詢日前三年。2026-09-17 實測 OpenAPI 最新 JSON 快照，欄位含 `Date`、`ContractCode`、`Item`、`OpenInterest(Long/Short/Net)`；篩選 `臺股期貨`／`外資及陸資` 後，2026-09-16 淨未平倉為 -76,351 口。**同日另實測網頁版依日期下載表單 `cht/3/futContractsDateDown`（`commodityId=TXF`），可回補 2023/10/02 的完整三大法人資料（含外資及陸資淨未平倉 -7,012 口）**，證實 OpenAPI 以外還有可用的歷史查詢管道。 | 前端 JS 寫死允許區間為 2023/09/17～2026/09/17，同樣是約 3 年的 rolling window，超出窗口的舊資料仍須走「公開資料申購表」／E-Data Shop；OpenAPI 本身沒有日期參數的結論不變，但不能再據此宣稱「完全無法回填舊日」。本次未申請、未購買付費歷史商品，交付檔內容仍未驗證。 |

## PCR：日期回補入口、窗口限制與抽樣

[TAIFEX 臺指選擇權 Put/Call 比查詢／下載頁](https://www.taifex.com.tw/cht/3/dlPcRatio) 的查詢表單 POST 至 `/cht/3/pcRatio`，下載則 POST 至 [`/cht/3/pcRatioDown`](https://www.taifex.com.tw/cht/3/pcRatioDown)，日期欄位為 `queryStartDate`、`queryEndDate`（`YYYY/MM/DD`），下載表單另含空值 `down_type`。日期放在 POST body，不是 URL query string。頁面註明週到期與各到期月份 TXO 契約合併計算。

UI 實測起訖相差 30 日的 `2026/08/17–2026/09/16` 可查；相差 31 日的 `2026/08/16–2026/09/16` 遭拒並顯示「查詢區間不可超過30日!」。兩個端點都納入查詢，因此每段可含最多 31 個曆日。TAIFEX [OpenAPI Swagger](https://openapi.taifex.com.tw/) 的 `GET /PutCallRatio` 沒有日期參數，只回單一最新快照；不能替代長期日期回補。該端點欄位為 `Date`、成交量、成交量比率、Put/Call OI 與 OI 比率。

官方網頁 CSV 抽樣結果如下；資料列日期皆唯一：

| 查詢區間 | 筆數與資料日期 | 交易日核對 |
|---|---|---|
| 2001/11/24–2001/12/23 | 0 筆 | 臺指選擇權上市前區間無資料。 |
| 2001/12/24–2002/01/23 | 22 筆，資料日期 2001/12/24–2002/01/23 | 日期唯一；官方沿革記載上市日為 2001/12/24，首列相符。上市日 Put/Call OI 為 90/683 口、OI PCR 13.18%，比率可由數量重算。 |
| 2025/05/15–2025/06/14 | 21 筆，資料日期 2025/05/15–2025/06/13 | 日期唯一；5/30 無列，對照[期交所 2025 行事曆](https://www.taifex.com.tw/file/taifex/CHINESE/4/2025Calendar_cv1.pdf)為端午節補假休市。 |
| 2026/08/18–2026/09/17 | 22 筆，資料日期 2026/08/18–2026/09/16 | 日期唯一；查詢日 9/17 尚無當日收盤列。 |

從 2001/12/24 至 2026/09/17 共 9,034 個曆日；以每段最多 31 個曆日且首尾不重疊估算，需 292 次請求。完成稽核前的四段抽樣資料日期唯一；完整執行結果另列如下。OpenAPI 沒有日期參數，只能作最新快照；日級 CSV 的實際編碼仍未由官方文件明載，正式回補仍應序列執行並設失敗退避。空白日期不能自動當作 PCR=0 或中性訊號。

### 全期分段稽核結果

2026-09-17 以 [`taifex-pcr-window-audit.yml`](../.github/workflows/taifex-pcr-window-audit.yml) 執行 [`35184984406`](https://github.com/TaylorYam/Huda-taiwan-market-quant/actions/runs/35184984406)，查詢 `2001-12-24` 至 `2026-09-17`。報告顯示 292 個窗口全部完成，回傳 6,090 筆日列，日期集合也是 6,090 個，沒有跨窗口重複日期或查詢錯誤；最早日為 2001-12-24，最新日為 2026-09-16。這證明官方分段端點在本次執行中可重現，不等於每一個曆日都應有交易列，也不替代官方交易日曆缺日核對。

本專案以 `python -m scripts.audit_taifex_pcr` 作為只讀稽核工具。它依每段最多 30 日差、端點包含的規則建立不重疊窗口，使用官方 `pcRatioDown` POST，按 MS950／UTF-8 解碼，記錄每段欄位、列數、日期範圍、錯誤與全域重複日期，將 JSON 報告寫入指定檔案。工具不寫入 observation store，也不把非交易日補成 0；GitHub Actions 的 `taifex-pcr-window-audit.yml` 僅手動啟動並保存報告 artifact。分段稽核已完成，但逐日交易日曆核對尚未完成，因此不能宣稱交易日覆蓋完整。

新版稽核 JSON 額外保留排序後的 `observed_dates`，供 `python -m scripts.reconcile_taifex_pcr_audit --audit pcr-window-audit.json --calendar taifex-calendar.json --output pcr-calendar-reconciliation.json` 離線比對。舊版 2026-09-17 全期 artifact 只有筆數，沒有逐日日期清單，不能用它推導缺日；取得官方日曆後須重新產生新版稽核報告，或提供同等逐日原始證據。日曆檔必須是 JSON object，包含 `source`、`start_date`、`end_date`、`dates`，起訖須與稽核請求區間完全相同，`source` 須可供人工核對官方出處。若未提供日曆，可省略 `--calendar` 產出 `unknown` 報告；窗口錯誤、舊版計數報告、部分區間日曆均不能判為通過。`missing_dates` 與 `unexpected_dates` 只是待解釋的日期差集，不自行判斷休市原因，也不補 PCR=0。

## TX 年度行情 ZIP：年度範圍與全檔稽核

[TAIFEX 期貨每日交易行情下載頁](https://www.taifex.com.tw/cht/3/futDailyMarketView)（舊入口仍為 `/cht/3/dlFutDailyMarketView`）的年度選單實測列出 1998–2025，共 28 個年度；頁面說明歷史年度提供 ZIP。年度下載表單 POST 至 `/cht/3/futDataDown`，參數為 `down_type=2`、`his_year=YYYY`。GitHub Actions [全期稽核 run 35186014961](https://github.com/TaylorYam/Huda-taiwan-market-quant/actions/runs/35186014961) 逐年下載並解析 28 份 ZIP：84,828 筆 TX 列、6,819 個年度日期、0 個錯誤、0 個年度內重複鍵；每個年度的 TX 日期都有至少一筆正成交量列。

年度摘要如下；「欄數」是該年度 CSV 所見資料列欄數（包含檔案控制／空白列），不是只計 TX 列。2026 年尚無年度 ZIP，因此由 `scripts/backfill_free_factor_range.py` 使用官方 `futDailyMarketReport` 日期 POST、只保存日盤「一般」資料，並保留來源 payload hash 與 parser version：

| 年度 | TX 列 | 日期 | 首日–末日 | 資料列欄數 |
|---:|---:|---:|---|---|
| 1998 | 625 | 125 | 1998-07-21–12-31 | 16 |
| 1999 | 1,330 | 266 | 1999-01-05–12-28 | 16 |
| 2000 | 1,355 | 271 | 2000-01-04–12-30 | 16 |
| 2001 | 1,220 | 244 | 2001-01-02–12-31 | 16 |
| 2002 | 1,240 | 248 | 2002-01-02–12-31 | 16 |
| 2003 | 1,245 | 249 | 2003-01-02–12-31 | 16 |
| 2004 | 1,250 | 250 | 2004-01-02–12-31 | 16 |
| 2005 | 1,235 | 247 | 2005-01-03–12-30 | 16 |
| 2006 | 1,240 | 248 | 2006-01-02–12-29 | 16 |
| 2007 | 1,274 | 247 | 2007-01-02–12-31 | 16 |
| 2008 | 1,745 | 249 | 2008-01-02–12-31 | 16 |
| 2009 | 1,942 | 251 | 2009-01-05–12-31 | 16 |
| 2010 | 1,917 | 251 | 2010-01-04–12-31 | 16 |
| 2011 | 1,957 | 247 | 2011-01-03–12-30 | 16 |
| 2012 | 1,975 | 250 | 2012-01-02–12-28 | 16 |
| 2013 | 1,843 | 246 | 2013-01-02–12-31 | 16 |
| 2014 | 1,952 | 248 | 2014-01-02–12-31 | 16 |
| 2015 | 1,975 | 244 | 2015-01-05–12-31 | 16／17 |
| 2016 | 2,033 | 244 | 2016-01-04–12-30 | 16／17 |
| 2017 | 2,888 | 246 | 2017-01-03–12-29 | 18／19 |
| 2018 | 6,318 | 247 | 2018-01-02–12-28 | 1／20 |
| 2019 | 6,526 | 242 | 2019-01-02–12-31 | 1／20 |
| 2020 | 6,873 | 245 | 2020-01-02–12-31 | 1／20 |
| 2021 | 6,552 | 244 | 2021-01-04–12-30 | 1／20 |
| 2022 | 6,914 | 246 | 2022-01-03–12-30 | 1／20 |
| 2023 | 6,594 | 239 | 2023-01-03–12-29 | 1／20 |
| 2024 | 6,755 | 242 | 2024-01-02–12-31 | 1／20 |
| 2025 | 6,055 | 243 | 2025-01-02–12-31 | 1／20 |

1998–2016 的年度檔沒有交易時段欄；2017 起出現交易時段欄，2018–2025 為一般／盤後兩種時段，故後續資料主鍵必須保留盤別。2018–2025 各有一筆單欄終止／控制列，解析時已排除。完整 JSON 僅作為 Actions artifact 保存，程式與此文件保留可重跑的摘要。

三份 CSV 均以 Big5／CP950 讀取。1998 ZIP 為 12,586 bytes；包內 `1998_fut.csv` 為 46,453 bytes，共 625 筆 TX 列、125 個日期，日期範圍 1998-07-21 至 1998-12-31；第一列到期月份為 199809。以交易日期、契約、到期月份組合檢查，重複鍵為 0；125 個日期每一天均有至少一筆正成交量 TX 列。TAIFEX 官方沿革記載期貨市場於 1998-07-21 開市，與檔案首日相符。1998 年官方交易日曆未取得，因此不能據此宣稱沒有缺少交易日。

最新年度 2025 ZIP 為 9,669,941 bytes；`2025_fut.csv` 為 45,000,613 bytes、6,055 筆 TX 列、243 個日期，首末日期為 2025-01-02–2025-12-31。2024 ZIP 為 9,274,958 bytes；`2024_fut.csv` 為 42,492,338 bytes、6,755 筆 TX 列、242 個日期，首末日期為 2024-01-02–2024-12-31。兩年以交易日期、契約、到期月份及盤別作鍵均無重複；日期集合與 TAIFEX 官方年度行事曆及臨時休市公告相符。兩年資料含一般與盤後交易時段；若移除盤別，同日契約與到期月份將被誤判為重複。近年 CSV 標頭有 19 欄、每筆資料解析為 20 欄，最後一欄無標題且為空，另各有一筆空白列；解析器不可假設檔頭與資料列欄數相同。1998 檔則為 16 欄且沒有盤別欄，三種 schema 不可直接視為一致。

2024、2025 日期集合包括官方公告的 7/24–25、10/2–3、10/31 颱風休市，並與官方年曆相符；2025 年 1/22 是農曆年前最後交易日。1998 檔有 11 個星期六交易日期，不可用現代週一至週五規則判定缺日。臺灣證券交易所 60 週年史料記載民國 87 年 4 月 4 日起星期六交易延長至中午 12 時，民國 90 年 1 月才配合週休二日停止星期六交易；這能解釋 1998 年出現星期六交易的歷史背景，但不是 TAIFEX 1998 年逐日休市清單。TAIFEX 現行行事曆頁只提供目前年度，仍未找到 1998 官方交易日曆。全期稽核只證明官方年度檔可下載、可解析及檔內鍵不重複，因此仍不能宣稱 1998 逐日完整。

代表 ZIP 的 SHA-256（用於後續核對下載內容；不是包內 CSV hash）：

- 1998 `1998_fut.csv`: `1c2d690a1fb000da730c2d8535c00b6e4cea25c9b6915e0e5175e88e92804be5`
- 2024 `2024_fut.csv`: `cb087e4e5a1607a89fad7ca370c53b9d2793a1d7a26495fa49680e567cdd8c5c`
- 2025 `2025_fut.csv`: `ad37930e535bc49fa39e8329eab306101f659882914aa57b1e2768b7eaaa8d64`

TAIFEX 另一官方[最後結算價頁](https://www.taifex.com.tw/cht/5/futIndxFSP)註記 TX 資料自 1998 年 9 月開始，不應誤讀為每日行情 ZIP 的起始月份：1998 日行情 ZIP 實際含 1998-07-21。完整的年度 ZIP 缺列率與資料修訂狀態仍未知。

## 三大法人期貨 OI：公開查詢窗口與舊資料路徑

TAIFEX [區分各期貨契約－依日期頁](https://www.taifex.com.tw/cht/3/futContractsDateView)的官方註記分別說明：本表資料起日為 2008-04-07；自 2012-05-01 起，公開頁只提供查詢日前三年的資料；若需歷史資料，應填寫公開資料申購表申請。這是**免費公開頁的回查窗口**，不是歷史資料起日，也不代表 2008 年後的所有 OI 歷史檔都能直接由目前的日期表下載。

TAIFEX [交易歷史資料申請頁](https://www.taifex.com.tw/cht/3/hisAppForm)將「期貨三大法人資料(含 OI)」列在可申購項目中，並指示至 [E-Data Shop](https://edatashop.taifex.com.tw/) 線上申購；實際可供申購的起迄期間另見官方「交易歷史資料價格及起迄時間一覽表」。本次沒有填表、下單或取得舊檔，所以申購商品目前的可訂期間、價格、實際交付欄位與授權範圍均**未驗證**。

也嘗試在依日期下載頁送出 2008-04-07 單日查詢，但沒有取得 CSV 下載或可讀的錯誤訊息；因此不把該次嘗試當成對舊日伺服器行為的實測結論。三年窗口與申購路徑的判斷來自該頁明載的官方註記及官方申請頁。

2026-09-17 另以官方 OpenAPI 端點 [`MarketDataOfMajorInstitutionalTradersDetailsOfFuturesContractsBytheDate`](https://openapi.taifex.com.tw/v1/MarketDataOfMajorInstitutionalTradersDetailsOfFuturesContractsBytheDate) 直接實測 JSON。回應是最新快照，沒有日期查詢參數；以 `ContractCode=臺股期貨`、`Item=外資及陸資` 篩選後，2026-09-16 列的 `OpenInterest(Net)` 為 `-76351`。欄位同時提供多空未平倉口數與淨交易量，足以支援每日增量保存及 5 日變化因子。**這個 OpenAPI 端點本身不提供歷史回補，但同日另外實測網頁版 `依日期` 下載表單背後的 `cht/3/futContractsDateDown`（POST，欄位 `queryStartDate`／`queryEndDate`／`commodityId=TXF`）可查到 2023/10/02 的完整資料（外資及陸資淨未平倉 -7,012 口），前端 JS 寫死允許區間為 2023/09/17～2026/09/17，即約 3 年的 rolling window。** 三年內的歷史已由 `scripts/backfill_free_factor_range.py` 寫入 Supabase，並在 2026-09-18 覆蓋率報告確認 729 個可用日期（2023-09-18..2026-09-17）；超出 3 年 rolling window 的資料仍需申請或購買官方歷史檔案。

## Taiwan VIX：免費日收盤窗口與歷史商品需分開

[TAIFEX 前 3 個月每日收盤 VIX 頁](https://www.taifex.com.tw/cht/7/vixDaily3MNew) 的免費頁面月份列表實測可見 2026/06、07、08、09。月份檔可由下載連結重現，例如 [`202609new.txt`](https://www.taifex.com.tw/file/taifex/Dailydownload/vix/log2data/202609new.txt)；檔案是含標頭與分隔線的 tab-separated 純文字，資料列實際以七欄對齊，日期／時間在前兩欄、VIX 收盤在第五欄、收盤前 1 分鐘平均在第七欄。2026-09-15 日列的有效欄位為 `20260915`、`13450000`、`27.29`、`27.29`，因此日收盤 VIX 已直接驗證為 27.29。

目前只納入日等級資料；盤中 TXT 與分時查詢不作為本項資料來源，也不拿盤中末值替代日收盤。

TAIFEX [指數專區](https://www.taifex.com.tw/indes/index.aspx) 明示可查最近三年。本次點選「3年」實測圖表日期為 2023-09-16 至 2026-09-15。**進一步實測圖表背後的 JSON API `indes/index.aspx/GetStockDayPrices`（POST，欄位 `syid=TAIWANVIX`、`flag=MS`、`startDate`、`endDate`）證實可直接匯出同一期間的日級 payload**：查詢 2023/10/01–2023/10/31 回傳 20 筆日資料（例如 2023/10/02 收盤 13.99），查詢 2010/01 則回傳空陣列（無錯誤，純粹超出窗口）。這證實圖表查詢窗口與可匯出的日級資料是同一件事，不是分開的兩個限制。

TAIFEX [E-Data Shop VIX 新版歷史商品](https://edatashop.taifex.com.tw/zh/product/detail/40283ab7890b3664018924255bf2000f) 頁面列示可申購期間自 2007-01-01 至申購日前一完整月份，月資料，NT$3,000／半年，並有限定使用方式；這是付費產品規格，不是免費歷史窗口，也未在本次購買或取得檔案。免費月檔的日列同時提供 VIX 與收盤前 1 分鐘平均，兩欄應分開保存。

本專案的 `taifex_vix` parser 已處理標頭／分隔線、七欄對齊、日期時間正規化、重複日期與不可用數值；`collect_vix_month` 可透過既有 ObservationStore 寫入日級 observation，GitHub Actions 的 `taifex-vix-daily-ingestion.yml` 只抓當月檔並以重跑去重，走的是 log2data 月檔（近 3～4 個月）。三年 rolling window 的 `GetStockDayPrices` 回補已由 `scripts/backfill_free_factor_range.py` 接上 Supabase 批次寫入；截至 2026-09-17 已保存 729 個可用日期（2023-09-18..2026-09-17）。免費來源仍到不了三年以上或 2010 年的歷史。

## 尚待驗證

1. PCR 2001-12-24–2026-09-17 已完成 292 段全期稽核；若要宣稱交易日覆蓋完整，仍需記錄官方交易日曆並解釋每個無資料日的原因。空白日期不能自動當成 PCR=0 或中性訊號。
2. **1998 年官方交易日曆 reconciliation：2026-09-17 決定 out of scope。** 原因：[`data-window-policy-v0.1.md`](data-window-policy-v0.1.md) 已確認 v0.1 模型的共同起點被 Taiwan VIX、法人期貨 OI 這兩個因子卡在約 2023 年（兩者都有約 3 年 rolling window 的免費回補管道，但共同起點仍取決於這兩個因子回補後的 earliest_date），1998–2001 年的 TX 資料不會被目前模型使用，逐日行事曆 reconciliation 對 v0.1 沒有實質意義。若未來因子必要性設計改變（例如把 VIX／法人期貨 OI 改為可選）而重新納入更長的 TX 歷史，才需要重新評估是否值得尋找 1998 年官方交易日曆。年度 ZIP 本身已完成 1998–2025 全檔解析（維持有效），但 2026 年度檔尚未出現在官方選單，且來源修訂狀態仍未知，這兩項仍是一般性資料維護待辦，與日曆 reconciliation 無關。
3. **VIX、法人期貨 OI 與 TX 2026 的免費回補已完成，需持續維護。** `GetStockDayPrices`／`futContractsDateDown` 與 TX 日期頁已接入一次性免費回補流程，並在 2026-09-18 的 Supabase 覆蓋率報告中各保存 729 個可用日期（2023-09-18..2026-09-17）。因為 rolling window 與日期頁都需要每日增量更新，不能把這段窗口視為固定歷史檔案。
4. 超出 3 年 rolling window 的歷史（VIX 更早於約 2023 年、法人期貨 OI 更早於約 2023 年）仍需走付費路徑：VIX 已知 E-Data Shop 最早 2007-01-01；法人期貨 OI 的付費歷史商品條件仍未驗證，需先在歷史資料申請頁確認可訂區間、價格、欄位與使用限制，任何申購決定前不把窗口外的資料視為已可得。

## 官方來源

- [TAIFEX 臺指選擇權 Put/Call 比（日期查詢與 CSV）](https://www.taifex.com.tw/cht/3/dlPcRatio)
- [TAIFEX OpenAPI Swagger（PutCallRatio）](https://openapi.taifex.com.tw/)
- [TAIFEX 政府資料開放平台資料集 11322](https://data.gov.tw/dataset/11322)
- [TAIFEX 網站使用條款](https://www.taifex.com.tw/cht/edu/userTerms)
- [TAIFEX 臺指選擇權上市日期（2001-12-24）](https://www.taifex.com.tw/file/taifex/event/cht/taifex25year/02_spotlight.html)
- [TAIFEX 選擇權每日行情查詢起日（2001-12-24）](https://www.taifex.com.tw/cht/3/optDailyMarketSummary)
- [TAIFEX 期貨每日行情與年度 ZIP 下載](https://www.taifex.com.tw/cht/3/futDailyMarketView)
- [TAIFEX 2024 年度交易行事曆](https://www.taifex.com.tw/file/taifex/CHINESE/11/attach/%E5%8F%B0%E6%9C%9F%E4%BA%A4%E5%AD%97%E7%AC%AC1120003542%E8%99%9F%E5%87%BD.pdf)
- [TAIFEX 2025 年度交易行事曆修正版](https://www.taifex.com.tw/file/taifex/CHINESE/11/attach/%E5%8F%B0%E6%9C%9F%E4%BA%A4%E5%AD%97%E7%AC%AC1140001929%E8%99%9F%E5%87%BD.pdf)
- [TAIFEX 2025 年行事曆（端午節補假）](https://www.taifex.com.tw/file/taifex/CHINESE/4/2025Calendar_cv1.pdf)
- [TAIFEX 1998 年期貨市場開市沿革](https://www.taifex.com.tw/cht/4/historyOfTrading)
- [TAIFEX 2024/07/24–25 凱米颱風休市公告](https://www.taifex.com.tw/cht/11/newsDetail?idx=15240&newsType=1)
- [TAIFEX 2024/10/02–03 山陀兒颱風休市公告](https://www.taifex.com.tw/cht/11/newsDetail.do?idx=15394&thetype=2)
- [TAIFEX 2024/10/31 康芮颱風休市公告](https://www.taifex.com.tw/cht/11/newsDetail?idx=15446&newsType=1)
- [TAIFEX 期貨三大法人 OI 依日期查詢、資料窗口註記](https://www.taifex.com.tw/cht/3/futContractsDateView)（下載表單 POST 至 `futContractsDateDown`，欄位 `queryStartDate`／`queryEndDate`／`commodityId`；2026-09-17 實測約 3 年 rolling window）
- [TAIFEX OpenAPI：三大法人期貨契約日資料](https://openapi.taifex.com.tw/v1/MarketDataOfMajorInstitutionalTradersDetailsOfFuturesContractsBytheDate)
- [TAIFEX 交易歷史資料申請（含期貨三大法人資料）](https://www.taifex.com.tw/cht/3/hisAppForm)
- [TAIFEX E-Data Shop](https://edatashop.taifex.com.tw/)
- [TAIFEX VIX 前 3 個月每日收盤頁](https://www.taifex.com.tw/cht/7/vixDaily3MNew)
- [TAIFEX VIX 盤中查詢頁](https://www.taifex.com.tw/cht/7/vixMinNew)
- [TAIFEX 指數專區（最近三年日期查詢）](https://www.taifex.com.tw/indes/index.aspx)（背後 JSON API `indes/index.aspx/GetStockDayPrices`，欄位 `syid=TAIWANVIX`／`flag=MS`／`startDate`／`endDate`；2026-09-17 實測約 3 年 rolling window，超出窗口回傳空陣列）
- [TAIFEX E-Data Shop VIX 新版歷史商品](https://edatashop.taifex.com.tw/zh/product/detail/40283ab7890b3664018924255bf2000f)
- [TAIFEX TX 最後結算價資料起始月份註記](https://www.taifex.com.tw/cht/5/futIndxFSP)
- [TWSE 60 週年特刊：交易制度沿革（星期六交易至民國 90 年）](https://www.twse.com.tw/staticFiles/product/publication/twse60/P5.pdf)

## 日級資料品質報告與行事曆邊界

新增 `python -m scripts.report_taifex_quality` 產生唯讀的日級 coverage／reconciliation JSON。輸入的 `datasets` 必須只包含 PCR probe、TX parser 或 VIX collector 實際回傳的日列；報告會保留各資料集的 `earliest_date`、`latest_date`、空列（`empty_dates`）、重複日（`duplicate_dates`）、品質狀態計數與 gate 結果。TX 同一交易日的不同契約／到期月份／盤別應以 `source_record_key` 區分，不能把合法的多契約列誤判為重複。

只有明確提供官方交易日曆日期清單時，報告才會計算 `missing_dates`、`unexpected_dates` 與 coverage 分母。未取得官方行事曆時，`calendar_boundary.status` 保留為 `unknown`、`missing_dates` 保留為 `null`、gate 為 `unknown`；工具不以平日規則、日期連續區間或前後資料推導交易日，也不把空列補成零值或有效觀察。現階段 1998 TX 邊界及跨完整歷史的逐日行事曆仍屬 unknown。
