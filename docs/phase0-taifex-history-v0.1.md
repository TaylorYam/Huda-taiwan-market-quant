# TAIFEX 歷史資料邊界補查 v0.1

查核日期：2026-09-16（Asia/Taipei）
範圍：Phase 0 Issue 2 的 TXO Put/Call Ratio（PCR）歷史查詢、TAIFEX 年度 TX 行情 ZIP、Taiwan VIX 免費查詢窗口，以及三大法人期貨未平倉資料的公開查詢窗口與歷史資料申請路徑。
來源：TAIFEX 官方頁面與檔案；另檢查使用者提供的 `20260915.txt` 樣本。未購買或申請任何資料。

## 結論

| 項目 | 已驗證 | 邊界／待查 |
|---|---|---|
| TXO PCR | 官方日期表單 POST 可按日期下載；抽查上市前、上市首段、2025 休市日附近及最新區段。首個可取資料日為 2001-12-24；最新樣本至 2026-09-15。 | 起訖日期相差最多 30 個曆日且兩端包含（每段最多涵蓋 31 個曆日）；估計全期需 292 段。本次未遍歷全部區段，因此完整缺漏率未知。 |
| TX 年行情 | 官方年度選單列出 1998–2025 共 28 年；全檔檢查 1998、2024、2025 三份 ZIP。1998 TX 首末資料日為 1998-07-21–12-31；2025 最新年檔為 2025-01-02–12-31。 | 三份檔案的 TX 主鍵皆無重複；2024、2025 日期集合符合官方年曆。其餘 25 年未逐檔檢查；1998 年歷史官方日曆缺失，未能完成其交易日缺漏判定。 |
| Taiwan VIX | 免費每日收盤頁顯示 2026/06–09 月份；最新資料日為 2026-09-15。指數專區「3年」圖表實測窗口為 2023-09-16 至 2026-09-15。使用者提供的 2026-09-15 盤中 TXT 樣本有 1,141 筆、每 15 秒一筆。 | 盤中樣本末筆與 `Last 1 min AVG` 均為 27.29，但這不能證明它等於免費日收盤頁的日收盤值；日收盤下載檔完整 payload、精確首末筆及回應格式仍未核實，三年圖表也未驗證 CSV 匯出。付費歷史商品另列，不視為免費資料。 |
| 三大法人期貨 OI | 官方「區分各期貨契約－依日期」頁註明資料起日 2008-04-07，且自 2012-05-01 起只供查詢日前三年。 | 超出公開查詢窗口的舊資料走「公開資料申購表」／TAIFEX E-Data Shop 歷史資料路徑；本次未申請、未購買、未驗證交付檔。 |

## PCR：日期回補入口、窗口限制與抽樣

[TAIFEX 臺指選擇權 Put/Call 比查詢／下載頁](https://www.taifex.com.tw/cht/3/dlPcRatio) 的查詢表單 POST 至 `/cht/3/pcRatio`，下載則 POST 至 [`/cht/3/pcRatioDown`](https://www.taifex.com.tw/cht/3/pcRatioDown)，日期欄位為 `queryStartDate`、`queryEndDate`（`YYYY/MM/DD`），下載表單另含空值 `down_type`。日期放在 POST body，不是 URL query string。頁面註明週到期與各到期月份 TXO 契約合併計算。

UI 實測起訖相差 30 日的 `2026/08/17–2026/09/16` 可查；相差 31 日的 `2026/08/16–2026/09/16` 遭拒並顯示「查詢區間不可超過30日!」。兩個端點都納入查詢，因此每段可含最多 31 個曆日。TAIFEX [OpenAPI Swagger](https://openapi.taifex.com.tw/) 的 `GET /PutCallRatio` 沒有日期參數，只回單一最新快照；不能替代長期日期回補。該端點欄位為 `Date`、成交量、成交量比率、Put/Call OI 與 OI 比率。

官方網頁 CSV 抽樣結果如下；資料列日期皆唯一：

| 查詢區間 | 筆數與資料日期 | 交易日核對 |
|---|---|---|
| 2001/11/24–2001/12/23 | 0 筆 | 臺指選擇權上市前區間無資料。 |
| 2001/12/24–2002/01/23 | 22 筆，資料日期 2001/12/24–2002/01/23 | 日期唯一；官方沿革記載上市日為 2001/12/24，首列相符。上市日 Put/Call OI 為 90/683 口、OI PCR 13.18%，比率可由數量重算。 |
| 2025/05/15–2025/06/14 | 21 筆，資料日期 2025/05/15–2025/06/13 | 日期唯一；5/30 無列，對照[期交所 2025 行事曆](https://www.taifex.com.tw/file/taifex/CHINESE/4/2025Calendar_cv1.pdf)為端午節補假休市。 |
| 2026/08/17–2026/09/16 | 22 筆，資料日期 2026/08/17–2026/09/15 | 日期唯一；查詢日 9/16 尚無當日收盤列。最新列 OI 為 81,556/94,956 口、OI PCR 85.89%，比率可由數量重算。 |

從 2001/12/24 至 2026/09/16 共 9,033 個曆日；以每段最多 31 個曆日且首尾不重疊估算，需 292 次請求。四段抽樣資料日期唯一，但沒有遍歷所有請求，也未取得全期交易日覆蓋率；因此不能宣稱全期間完整。OpenAPI 實測為 HTTP 200、3,394 bytes，`Last-Modified` 為 2026-09-15 22:36 UTC（台北時間 2026-09-16 06:36），最新資料日為 2026-09-15。官方政府資料開放平台[資料集 11322](https://data.gov.tw/dataset/11322)標示每日更新、免費及政府資料開放授權條款第 1 版；期交所[網站使用條款](https://www.taifex.com.tw/cht/edu/userTerms)說明已授權政府資料開放平台的資料屬例外。單一請求頻率限制、下載 CSV 實際位元組／編碼仍未核實，若進行回補應序列執行並設失敗退避。空白日期不能自動當成 PCR=0 或中性訊號。

## TX 年度行情 ZIP：年度範圍與代表檔完整檢查

[TAIFEX 期貨每日交易行情下載頁](https://www.taifex.com.tw/cht/3/dlFutDailyMarketView) 的年度選單實測列出 1998–2025，共 28 個年度；頁面說明歷史年度提供 ZIP。本次全檔檢查 1998、2024、2025 三份年檔，未逐年下載其餘 25 份。

三份 CSV 均以 Big5 讀取。1998 ZIP 為 12,586 bytes；包內 `1998_fut.csv` 為 46,453 bytes，共 625 筆 TX 列、125 個日期，日期範圍 1998-07-21 至 1998-12-31；第一列到期月份為 199809。以交易日期、契約、到期月份組合檢查，重複鍵為 0；125 個日期每一天均有至少一筆正成交量 TX 列。TAIFEX 官方沿革記載期貨市場於 1998-07-21 開市，與檔案首日相符。1998 年官方交易日曆未取得，因此不能據此宣稱沒有缺少交易日。

最新年度 2025 ZIP 為 9,669,941 bytes；`2025_fut.csv` 為 45,000,613 bytes、6,055 筆 TX 列、243 個日期，首末日期為 2025-01-02–2025-12-31。2024 ZIP 為 9,274,958 bytes；`2024_fut.csv` 為 42,492,338 bytes、6,755 筆 TX 列、242 個日期，首末日期為 2024-01-02–2024-12-31。兩年以交易日期、契約、到期月份及盤別作鍵均無重複；日期集合與 TAIFEX 官方年度行事曆及臨時休市公告相符。兩年資料含一般與盤後交易時段；若移除盤別，同日契約與到期月份將被誤判為重複。近年 CSV 標頭有 19 欄、每筆資料解析為 20 欄，最後一欄無標題且為空，另各有一筆空白列；解析器不可假設檔頭與資料列欄數相同。1998 檔則為 16 欄且沒有盤別欄，三種 schema 不可直接視為一致。

2024、2025 每個有 TX 日期都有正成交量資料；2024 日期集合包括官方公告的 7/24–25、10/2–3、10/31 颱風休市，並與官方年曆相符；2025 日期集合符合年度開休市表，1/22 是農曆年前最後交易日。1998 檔有 11 個星期六交易日期，不可用現代週一至週五規則判定缺日。年度選單中其餘 25 份 ZIP 未下載、未逐年檢查。

代表 CSV 的 SHA-256（用於後續核對下載內容）：

- 1998 `1998_fut.csv`: `1c2d690a1fb000da730c2d8535c00b6e4cea25c9b6915e0e5175e88e92804be5`
- 2024 `2024_fut.csv`: `cb087e4e5a1607a89fad7ca370c53b9d2793a1d7a26495fa49680e567cdd8c5c`
- 2025 `2025_fut.csv`: `ad37930e535bc49fa39e8329eab306101f659882914aa57b1e2768b7eaaa8d64`

TAIFEX 另一官方[最後結算價頁](https://www.taifex.com.tw/cht/5/futIndxFSP)註記 TX 資料自 1998 年 9 月開始，不應誤讀為每日行情 ZIP 的起始月份：1998 日行情 ZIP 實際含 1998-07-21。完整的年度 ZIP 缺列率與資料修訂狀態仍未知。

## 三大法人期貨 OI：公開查詢窗口與舊資料路徑

TAIFEX [區分各期貨契約－依日期頁](https://www.taifex.com.tw/cht/3/futContractsDateView)的官方註記分別說明：本表資料起日為 2008-04-07；自 2012-05-01 起，公開頁只提供查詢日前三年的資料；若需歷史資料，應填寫公開資料申購表申請。這是**免費公開頁的回查窗口**，不是歷史資料起日，也不代表 2008 年後的所有 OI 歷史檔都能直接由目前的日期表下載。

TAIFEX [交易歷史資料申請頁](https://www.taifex.com.tw/cht/3/hisAppForm)將「期貨三大法人資料(含 OI)」列在可申購項目中，並指示至 [E-Data Shop](https://edatashop.taifex.com.tw/) 線上申購；實際可供申購的起迄期間另見官方「交易歷史資料價格及起迄時間一覽表」。本次沒有填表、下單或取得舊檔，所以申購商品目前的可訂期間、價格、實際交付欄位與授權範圍均**未驗證**。

也嘗試在依日期下載頁送出 2008-04-07 單日查詢，但沒有取得 CSV 下載或可讀的錯誤訊息；因此不把該次嘗試當成對舊日伺服器行為的實測結論。三年窗口與申購路徑的判斷來自該頁明載的官方註記及官方申請頁。

## Taiwan VIX：免費窗口與歷史商品需分開

[TAIFEX 前 3 個月每日收盤 VIX 頁](https://www.taifex.com.tw/cht/7/vixDaily3MNew) 的免費頁面月份列表實測可見 2026/06、07、08、09，並確認最新資料日為 2026-09-15；欄位標示為交易日期及臺指選擇權波動率指數。此處只能確認頁面顯示當月與前三個月，日收盤頁下載檔的完整 payload、月份內精確首末筆及 CSV 回應格式尚未核實，不應寫成已完成日收盤 CSV 驗證。

另檢查使用者提供的 `20260915.txt` 盤中樣本（SHA-256：`1e21aa72777ea5c6bfc618ba0ed9cf0b3d59f610624c6b5546fc0c42149d0281`）。檔案以 Big5／CP950 解碼後有 1,141 筆報價，時間從 09:00:00.000 到 13:45:00.000，時間戳唯一且每筆間隔 15 秒；欄位值介於 27.01–27.76。最後一筆 13:45 報價為 27.29，尾端另列的 `Last 1 min AVG` 也是 27.29。資料列含空白欄位，因此實際 tab 分欄數多於標頭名稱數；解析器需保留並明確處理空欄。

這是單一日期的**盤中**樣本，末筆及最後一分鐘平均值不能直接當成已驗證的每日收盤序列，也不能據此推論其他日期或日收盤頁的 payload。TAIFEX 當月盤中頁為 [VIX 盤中查詢](https://www.taifex.com.tw/cht/7/vixMinNew)；它與上方每日收盤頁是不同資料口徑。

TAIFEX [指數專區](https://www.taifex.com.tw/indes/index.aspx) 明示可查最近三年。本次點選「3年」實測圖表日期為 2023-09-16 至 2026-09-15；再將起日提前至 2023-09-15 搜尋，頁面拒絕日期範圍。這是圖表查詢窗口，不代表已驗證可匯出同一期間 CSV，也不等於已取得連續日資料。

TAIFEX [E-Data Shop VIX 新版歷史商品](https://edatashop.taifex.com.tw/zh/product/detail/40283ab7890b3664018924255bf2000f) 頁面列示可申購期間自 2007-01-01 至申購日前一完整月份，月資料，NT$3,000／半年，並有限定使用方式；這是付費產品規格，不是免費歷史窗口，也未在本次購買或取得檔案。免費日收盤頁還註明自 2020-11-23 起新增「收盤前 1 分鐘平均」揭示；公開頁目前可見欄位未證明該平均值另有獨立欄位，故不可假設 2020-11-23 前後欄位與口徑完全相同。

## 尚待驗證

1. 若需要全期 PCR 連續性，按不重疊的 31 個曆日區段 POST 官方日期表單（下一段從前段結束日翌日開始），預估需 292 次；記錄每段原始回應、欄位、日期唯一性與交易日曆缺列原因。完成前不宣稱 2001 年以來全期完整。
2. 如需跨完整 TX 歷史做回測，從年度選單逐步稽核其餘 25 個 ZIP（1999–2023），同時保留格式變化、盤別與契約月；目前只有 1998、2024、2025 全檔檢查，1998 年官方交易日曆仍未知。
3. VIX 已檢查一份使用者提供的 2026-09-15 盤中 TXT（1,141 筆、15 秒頻率，末筆及 `Last 1 min AVG` 均為 27.29）；它不是日收盤頁資料。日收盤頁的 `20260915(txt)` payload、日收盤值欄位與完整月份資料仍未核實，三年圖表也未驗證可匯出。採用前需分別確認兩種檔案內容與口徑，不把盤中末值或 2020-11-23 起新增的收盤前 1 分鐘平均值混作已驗證的日收盤值。
4. 若模型需要三年前的法人期貨 OI，先在歷史資料申請頁確認 OI 商品的最新可訂區間、價格、欄位與使用限制；在任何申購決定前，不把公開三年窗口外的資料視為已可得。

## 官方來源

- [TAIFEX 臺指選擇權 Put/Call 比（日期查詢與 CSV）](https://www.taifex.com.tw/cht/3/dlPcRatio)
- [TAIFEX OpenAPI Swagger（PutCallRatio）](https://openapi.taifex.com.tw/)
- [TAIFEX 政府資料開放平台資料集 11322](https://data.gov.tw/dataset/11322)
- [TAIFEX 網站使用條款](https://www.taifex.com.tw/cht/edu/userTerms)
- [TAIFEX 臺指選擇權上市日期（2001-12-24）](https://www.taifex.com.tw/file/taifex/event/cht/taifex25year/02_spotlight.html)
- [TAIFEX 選擇權每日行情查詢起日（2001-12-24）](https://www.taifex.com.tw/cht/3/optDailyMarketSummary)
- [TAIFEX 期貨每日行情與年度 ZIP 下載](https://www.taifex.com.tw/cht/3/dlFutDailyMarketView)
- [TAIFEX 2024 年度交易行事曆](https://www.taifex.com.tw/file/taifex/CHINESE/11/attach/%E5%8F%B0%E6%9C%9F%E4%BA%A4%E5%AD%97%E7%AC%AC1120003542%E8%99%9F%E5%87%BD.pdf)
- [TAIFEX 2025 年度交易行事曆修正版](https://www.taifex.com.tw/file/taifex/CHINESE/11/attach/%E5%8F%B0%E6%9C%9F%E4%BA%A4%E5%AD%97%E7%AC%AC1140001929%E8%99%9F%E5%87%BD.pdf)
- [TAIFEX 2025 年行事曆（端午節補假）](https://www.taifex.com.tw/file/taifex/CHINESE/4/2025Calendar_cv1.pdf)
- [TAIFEX 1998 年期貨市場開市沿革](https://www.taifex.com.tw/cht/4/historyOfTrading)
- [TAIFEX 2024/07/24–25 凱米颱風休市公告](https://www.taifex.com.tw/cht/11/newsDetail?idx=15240&newsType=1)
- [TAIFEX 2024/10/02–03 山陀兒颱風休市公告](https://www.taifex.com.tw/cht/11/newsDetail.do?idx=15394&thetype=2)
- [TAIFEX 2024/10/31 康芮颱風休市公告](https://www.taifex.com.tw/cht/11/newsDetail?idx=15446&newsType=1)
- [TAIFEX 期貨三大法人 OI 依日期查詢、資料窗口註記](https://www.taifex.com.tw/cht/3/futContractsDateView)
- [TAIFEX 交易歷史資料申請（含期貨三大法人資料）](https://www.taifex.com.tw/cht/3/hisAppForm)
- [TAIFEX E-Data Shop](https://edatashop.taifex.com.tw/)
- [TAIFEX VIX 前 3 個月每日收盤頁](https://www.taifex.com.tw/cht/7/vixDaily3MNew)
- [TAIFEX VIX 盤中查詢頁](https://www.taifex.com.tw/cht/7/vixMinNew)
- [TAIFEX 指數專區（最近三年日期查詢）](https://www.taifex.com.tw/indes/index.aspx)
- [TAIFEX E-Data Shop VIX 新版歷史商品](https://edatashop.taifex.com.tw/zh/product/detail/40283ab7890b3664018924255bf2000f)
- [TAIFEX TX 最後結算價資料起始月份註記](https://www.taifex.com.tw/cht/5/futIndxFSP)
