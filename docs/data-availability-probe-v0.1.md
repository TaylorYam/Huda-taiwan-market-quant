# Data Availability Probe v0.1

## 範圍與方法

盤點起始日期：2026-09-15（Asia/Taipei）；Phase 0 補查至 2026-09-16。依 `factor-model-v0.1.md` 的 8 個核心因子，合併共用 TAIEX 行情的均線與 20 日動能，檢查官方 TWSE / TAIFEX 網頁、OpenAPI 與歷史資料申請頁，並檢視使用者提供的一日 VIX 盤中 TXT 樣本。後續實測結果分別記錄於 [TWSE 現貨口徑補查](phase0-cash-market-scope-v0.1.md) 與 [TAIFEX 歷史窗口補查](phase0-taifex-history-v0.1.md)。

「最早可查日期」、「查詢頁目前可回溯的窗口」和「本次實際量到的缺值率」是不同欄位。本次未下載每個來源的完整日序列與交易日曆，因此缺值率一律標為未測，不以目前 API 有回資料推定全期間完整。其他日資料樣本最新至 2026-09-14；VIX 每日收盤頁確認最新資料日為 2026-09-15，另檢視同日盤中樣本，但未驗證日收盤下載 payload 或值。

## 結果摘要

| Dataset | Source | Earliest / public window | Latest tested | Frequency | Missing | Automation |
|---|---|---|---|---|---|---|
| TAIEX OHLC（MA20/MA60、20 日動能） | TWSE | 1999-01-05 起 | 2026-09-14 | 日 | 未測 | 月查詢及 CSV；可回填 |
| 外資現貨流（免費 T86 股數） | TWSE | 2012-05-02 起 | 2026-09-14 | 日 | 未測 | 指定日期 JSON；金額口徑不符 v0.1 |
| 外資現貨買賣超金額（公開 BFI82U） | TWSE | 2004-04-07 起（頁面標示） | 2026-09-14 樣本與 CSV 入口已核對 | 日 | 未測 | 免費金額候選；樣本交易範圍與 FMTQIK 註記相符，免費表與 E-Shop 版次映射、早期分類與逐日回補仍待驗證 |
| 外資現貨買賣超金額（E-Shop 歷史產品） | TWSE E-Shop | 2004-02-19 起；付費 | 未下載 | 日 | 未測 | 每月訂閱；14:50／19:40 版本範圍不同 |
| 市場成交金額（外資比率分母） | TWSE FMTQIK | 1990-01-04 起（頁面標示） | 2022-10-24 樣本已核對 | 日 | 未測 | 免費 CSV／月報；TWSE 上市市場，不含 OTC／期貨；已查樣本交易類型／外幣換算註記與 BFI82U 相符，起始日及全期完整度未測 |
| 外資 TX 未平倉淨部位 | TAIFEX | 歷史起於 2008-04-07；公開查詢近 3 年 | 2026-09-14 | 日 | 未測 | OpenAPI 只回最新快照；舊檔需申請 |
| TX 行情（Basis） | TAIFEX | 官方年檔選單列 1998–2025；已全檔檢查 1998、2024、2025 ZIP | 2025 最新年度年檔（資料至 2025-12-31） | 日／分盤別 | 1998：無重複鍵；2024/25：日期集合符合官方日曆、含盤別無重複鍵 | 2025 年最新年檔範圍 2025-01-02–12-31；另 25 年未逐檔檢查，1998 日曆缺漏未知 |
| TXO OI Put/Call Ratio | TAIFEX | 已核驗 CSV 含 2001-12-24 起始列 | 2026-09-14 | 日 | 未測 | 單次區間上限 30 日；OpenAPI 快照 21 筆，長期完整覆蓋率未測 |
| Taiwan VIX（日收盤） | TAIFEX | 免費頁近 4 個月、指數查詢近 3 年；付費歷史商品自 2007 年 | 2026-09（本次未測單日值） | 日 | 未測 | 公開頁可累積；付費商品 NT$3,000／半年 |

### 逐項來源與欄位

| 原始資料集（支援因子） | 官方來源／實測結果 | 最早可得／查詢窗口 | 頻率、欄位與自動化 | 缺值率與注意事項 |
|---|---|---|---|---|
| TAIEX 指數 OHLC（MA20/MA60、20 日動能） | [TWSE 發行量加權股價指數歷史資料](https://www.twse.com.tw/zh/indices/taiex/mi-5min-hist.html?myear=)；月份查詢及 CSV 下載。官方標示資料自 1999-01-05 起，實測查詢早於此日會拒絕，並成功讀取 2000-01、2024-01 樣本。 | 1999-01-05 起；依月份查詢 | 日資料：日期、開盤、最高、最低、收盤指數。按月查詢可自動化；頁面也提供 CSV。 | 未測。足以支援 3 年視窗；擷取時應固定查詢月與本地交易日期。 |
| 外資現貨流（T86 股數） | 免費 [TWSE T86 三大法人買賣超日報](https://www.twse.com.tw/fund/T86?date=20260914&response=json&selectType=ALL)；實測 2026-09-14 回傳 JSON。 | 免費 T86 可查至 2012-05-02；測試更早日期時來源拒絕。數值為股數，不是模型所需的買賣超金額。 | 每交易日；逐證券買進／賣出／買賣超股數，含外資及陸資與外資自營商等分類。 | 未測。T86 註明為當日原始成交統計，不含錯帳、更正帳號調整。不得把股數直接當成金額。 |
| 外資現貨流（公開 BFI82U 金額） | 免費 [TWSE 三大法人買賣金額統計表 BFI82U](https://www.twse.com.tw/zh/trading/foreign/bfi82u.html)；可查日報並有 CSV 入口。查到 2004 樣本有外資買進、賣出、買賣差額，單位為元；2022-10-24 與 2026-09-14 報表註記含一般、零股、盤後定價、鉅額，排除拍賣／標購。 | 頁面標示自 2004-04-07 起；供應起日不是已驗證的逐日完整歷史。 | 市場彙總金額，不是個股明細；2004 報表列「外資」，目前欄位拆分外資及陸資（不含外資自營商）與外資自營商。 | 已查報表的交易類型與外幣換算註記和 FMTQIK 樣本相符；免費報表對應哪個 E-Shop 版次、早期分類、查詢連續性及完整度仍待核。見[現貨口徑補查](phase0-cash-market-scope-v0.1.md)。 |
| 外資現貨買賣超金額（E-Shop 歷史商品） | TWSE [三大法人買賣金額統計表](https://eshop.twse.com.tw/zh/product/detail/d31c1b9570ae47058ec83a0bb1ffa419) 提供歷史訂購路徑。 | 商品起點 2004-02-19；可訂單筆最多 5 年。 | 日資料；官方頁列 14:50 不含綜合帳戶／鉅額、19:40 含綜合帳戶／鉅額；2026-05-29 起格式變更。內用 NT$1,000／月、外部使用 NT$1,500／月。 | 未下載。公開 BFI82U 也有金額資料，是否需要付費歷史商品須看免費頁的範圍與版次能否滿足，不表示已選購。 |
| 市場成交金額（外資比率分母） | TWSE [FMTQIK 每日市場成交資訊](https://www.twse.com.tw/zh/trading/historical/fmtqik.html)；月報／CSV 含每日成交金額及加權指數。已查 2017-09-20 與 2022-10-24 樣本。 | 官方頁標示自 1990-01-04 起；尚未測起始日或完整缺值。 | TWSE 上市市場，含一般、零股、盤後定價與鉅額，排除拍賣／標購；外幣成交值按 15:30 公告匯率換算。 | 目前查到的 BFI82U 報表樣本與 FMTQIK 在列示交易類型及外幣換算說明相符；不能外推至所有歷史日期／E-Shop 版次。不包含 OTC 或期貨成交額。見[現貨口徑補查](phase0-cash-market-scope-v0.1.md)。 |
| 外資 TX 未平倉淨部位（及 5 日變化） | TAIFEX [三大法人區分期貨契約資料](https://www.taifex.com.tw/cht/3/futContractsDateView)；[OpenAPI 規格](https://openapi.taifex.com.tw/) 的 `MarketDataOfMajorInstitutionalTradersDetailsOfFuturesContractsBytheDate` 可取得最新快照。實測最新快照為 2026-09-14，共 66 列；以契約 `臺股期貨`、法人 `外資及陸資` 取 `OpenInterest(Net)`。 | 官方頁標示資料自 2008-04-07 起；一般歷史查詢僅提供查詢日前三年，較早資料需填公開資料申購表。OpenAPI 端點沒有日期查詢參數，只回最新快照。 | 每交易日。欄位含契約、法人、買／賣／淨交易量與買／賣／淨未平倉口數。OpenAPI 適合每日增量保存；直接 API 不適合回填。 | 未測。每日 13:45 公布前的資料不完整；16:15 最後一批才含國外成分證券 ETF／境外指數 ETF 交易量。回測須選定一致的公布版本與 as-of 時間。最後結算日未平倉量自 2008-12-17 起不含當月份到期商品。 |
| TX 期貨行情（Basis） | TAIFEX [期貨每日行情查詢](https://www.taifex.com.tw/cht/3/futDailyMarketReport?commodityId=TX)、[年度行情下載](https://www.taifex.com.tw/cht/3/dlFutDailyMarketView) 及 OpenAPI `DailyMarketReportFut`。年度 ZIP 表單 POST `/cht/3/futDataDown`（`down_type=2`、`his_year`）；選單列 1998–2025 共 28 年。 | 1998、2024、2025 三份全檔稽核：1998 首末 TX 日期 1998-07-21–12-31（625 列／125 日期）；2024 為 2024-01-02–12-31（6,755 列／242 日期）；2025 為 2025-01-02–12-31（6,055 列／243 日期）。 | Big5 CSV。1998 標頭 16 欄；2024/25 標頭 19 欄、資料列 20 欄，末欄無標題且為空。近年一般／盤後資料應用交易時段納入主鍵；TX 價格與 Basis 需固定近月及轉倉規則。 | 三檔各自重複鍵 0；2024/25 日期集合與官方行事曆及臨時休市公告相符。1998 每一個日期至少有正成交量 TX 列，但歷史官方交易日曆未取得，不能判定逐日缺漏；其餘 25 年未稽核。見[TAIFEX 歷史窗口補查](phase0-taifex-history-v0.1.md)。 |
| TXO OI Put/Call Ratio | TAIFEX [Put/Call Ratio 官方頁](https://www.taifex.com.tw/cht/3/dlPcRatio) 網頁表單 POST 支援日期區間；OpenAPI `GET /PutCallRatio` 無日期參數，只回最新快照。官方頁合併週到期與月契約。 | 最早可取列 2001-12-24；最新樣本資料日 2026-09-15。UI 限制為起訖相差最多 30 個曆日、端點含在內（每段最多 31 日），全期估計 292 個不重疊區段；只抽查代表區段，連續完整度未驗證。 | 每交易日；買賣權成交量、成交量 PCR、Put OI、Call OI、OI PCR。歷史回補欄位、端點與樣本結果見[TAIFEX 歷史窗口補查](phase0-taifex-history-v0.1.md)。 | 抽查 2001 上市初期、2025 端午補假週及最新區段，資料列無重複；2025/05/30 缺列由官方行事曆確認為休市。空值不可當作 PCR=0；需以交易日曆驗證完整下載後的覆蓋率。 |
| Taiwan VIX（日收盤／盤中分開） | 免費[每日收盤頁](https://www.taifex.com.tw/cht/7/vixDaily3MNew)可見 2026/06–09 月，最新資料日 2026-09-15；[指數專區](https://www.taifex.com.tw/indes/index.aspx)「3年」圖表窗口為 2023-09-16–2026-09-15。另有[盤中頁](https://www.taifex.com.tw/cht/7/vixMinNew)。 | 免費每日收盤頁：當月與前三個月；圖表查詢：最近三年。使用者提供的 2026-09-15 盤中 TXT 僅驗證一個交易日。付費歷史商品頁列示起自 2007-01-01、至申購日前一完整月份，NT$3,000／半年。 | 盤中樣本以 Big5／CP950 解碼後有 1,141 筆、09:00–13:45 每 15 秒一筆，唯一時間戳；VIX 範圍 27.01–27.76，末筆與 `Last 1 min AVG` 皆為 27.29。日收盤頁的 CSV payload、首末列及日收盤值仍未驗證；付費商品不代表已取得資料。 | 盤中最後一筆／最後一分鐘平均，不等於已驗證的日收盤序列。日收盤下載頁與盤中查詢是不同窗口及口徑；解析器還須容忍盤中檔標頭與資料列欄數不同及空白欄。三年圖表未驗證匯出；VIX 與其他因子仍需同交易日對齊。 |

## 對共同回測期間的影響

1. **目前不能鎖定完整 8 因子回測起日。** TAIFEX 外資期貨部位的官網歷史查詢只有近三年，舊資料須申請；VIX 免費檢視最多近三年，官方更長 VIX 歷史需購買；PCR 已驗證 2001-12-24 起始樣本及 30 日查詢上限，但整段歷史完整度尚未驗證。
2. **v0.1 金額比率可能不需購買外資金額資料。** 免費 BFI82U 公開日報表提供金額欄位，FMTQIK 提供每日市場成交金額，均可作為原定金額比率的候選資料來源。公開 BFI82U 的鉅額交易版次與早期分類仍待對帳；T86 股數不得冒充金額。只有免費歷史／版本無法滿足需求時才評估 E-Shop 付費商品。
3. **TAIFEX OpenAPI 多為最新快照。** 外資期貨、TX 行情與 PCR 要用 OpenAPI 建正式歷史庫，需從現在起每日按交易日保存、去重，保存抓取時間與來源日期；快照端點不等於可回補的歷史 API。
4. `data-window-policy-v0.1.md` 設定 3 年百分位窗。僅有近 3 年資料會消耗全部歷史做暖機，無法再留出完整回測樣本和未來 5／10／20 日標籤。應先取得超過暖機窗的重疊歷史，或開始累積資料後再做具代表性的回測。

## 建議的 v0.1 資料路線

- **先驗證無付費金額 MVP：** 用 TWSE TAIEX、公開 BFI82U 金額日報、FMTQIK 成交金額分母和 TAIFEX 免費快照／查詢作候選；先固定資料版次並按同日核對現貨分子、分母涵蓋範圍。T86 只另存為股數資料，不替代金額因子。把每次拉取的 `source_date`、`retrieved_at`、單位、版本、契約及盤別保存下來；不得把缺值默認為中性。
- **平行建立歷史資料請求清單：** 向 TAIFEX 申請 2008-04-07 起的外資期貨歷史資料，測試 PCR 的起訖日期與最早可查日，並探測可供下載的期貨行情最早年度。若要符合現貨金額比率及延長 VIX 回測，再依預算決定是否訂閱 TWSE 金額表、TAIFEX VIX 歷史商品。
- **下載完整序列後再計算缺值率。** 以 TAIEX 交易日作基準，逐資料集比對預期交易日、重複日、缺列、空值、修訂值與可用發布時間；完成後才更新正式共同起點及回測起點。

## 使用與自動化注意事項

本探測只讀取官方公開頁面/API，沒有抓取或提交付費歷史檔。TWSE 網路資訊商店條款禁止未經同意以自動化裝置、腳本或爬蟲下載商店軟體或資料；E-Shop 資料若採用，需按訂閱條款取用。其他公開 endpoint 的使用方式與再散布限制，也應在部署排程或公開 Dashboard 前按各來源使用條款確認。各來源都可能調整頁面、欄位與下載格式，擷取程式應驗證回應日期及必要欄位，失敗時回報 unavailable，不應靜默補值。

## 官方來源

- [TWSE 指數歷史頁](https://www.twse.com.tw/zh/indices/taiex/mi-5min-hist.html?myear=)
- [TWSE T86 三大法人買賣超日報](https://www.twse.com.tw/fund/T86?response=html)
- [TWSE BFI82U 公開金額查詢及 CSV](https://www.twse.com.tw/zh/trading/foreign/bfi82u.html)
- [TWSE FMTQIK 每日市場成交資訊](https://www.twse.com.tw/zh/trading/historical/fmtqik.html)
- [TWSE 三大法人買賣金額統計表（商品規格與價格）](https://eshop.twse.com.tw/zh/product/detail/d31c1b9570ae47058ec83a0bb1ffa419)
- [TWSE 網路資訊商店使用條款](https://eshop.twse.com.tw/zh/home/terms)
- [TAIFEX 三大法人期貨部位](https://www.taifex.com.tw/cht/3/futContractsDateView)
- [TAIFEX OpenAPI](https://openapi.taifex.com.tw/)
- [TAIFEX OpenAPI：三大法人期貨契約日資料](https://openapi.taifex.com.tw/v1/MarketDataOfMajorInstitutionalTradersDetailsOfFuturesContractsBytheDate)
- [TAIFEX OpenAPI：TX 每日行情](https://openapi.taifex.com.tw/v1/DailyMarketReportFut)
- [TAIFEX OpenAPI：Put/Call Ratio](https://openapi.taifex.com.tw/v1/PutCallRatio)
- [TAIFEX 每日期貨行情查詢](https://www.taifex.com.tw/cht/3/futDailyMarketReport?commodityId=TX)
- [TAIFEX 每日期貨行情下載與年度 ZIP](https://www.taifex.com.tw/cht/3/futDailyMarketView)
- [TAIFEX Put/Call Ratio](https://www.taifex.com.tw/cht/3/dlPcRatio)
- [TAIFEX 免費 VIX 日收盤（前 3 個月）](https://www.taifex.com.tw/cht/7/vixDaily3MNew)
- [TAIFEX 指數專區日期查詢](https://www.taifex.com.tw/indes/index.aspx)
- [TAIFEX VIX 歷史資料商品](https://edatashop.taifex.com.tw/zh/product/detail/40283ab7890b3664018924255bf2000f)
