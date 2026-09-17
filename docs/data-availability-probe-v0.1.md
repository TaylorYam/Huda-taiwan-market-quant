# Data Availability Probe v0.1

## 範圍與方法

盤點起始日期：2026-09-15（Asia/Taipei）；Phase 0 補查至 2026-09-17。依 `factor-model-v0.1.md` 的 8 個核心因子，合併共用 TAIEX 行情的均線與 20 日動能，檢查官方 TWSE / TAIFEX 網頁、OpenAPI 與歷史資料申請頁。本文件只整理日等級資料。後續實測結果分別記錄於 [TWSE 現貨口徑補查](phase0-cash-market-scope-v0.1.md) 與 [TAIFEX 歷史窗口補查](phase0-taifex-history-v0.1.md)。

「最早可查日期」、「查詢頁目前可回溯的窗口」和「本次實際量到的缺值率」是不同欄位。TAIFEX PCR 已完成全期分段下載，但尚未用完整官方交易日曆逐日核對無資料日；其他來源仍依各自實測範圍標示，不以目前 API 有回資料推定全期間完整。TAIFEX PCR 最新資料日為 2026-09-16；VIX 日收盤月檔已直接核實 2026-09-15 日列。

## 結果摘要

| Dataset | Source | Earliest / public window | Latest tested | Frequency | Missing | Automation |
|---|---|---|---|---|---|---|
| TAIEX OHLC（MA20/MA60、20 日動能） | TWSE | 1999-01-05 起 | 2026-09-14 | 日 | 未測 | 月查詢及 CSV；可回填 |
| 外資現貨流（免費 T86 股數） | TWSE | 2012-05-02 起 | 2026-09-14 | 日 | 未測 | 指定日期 JSON；金額口徑不符 v0.1 |
| 外資現貨買賣超金額（公開 BFI82U） | TWSE | 2004-04-07 起（頁面標示） | 2026-09-14 樣本與 CSV 入口已核對 | 日 | 未測 | 免費金額候選；樣本交易範圍與 FMTQIK 註記相符，免費表與 E-Shop 版次映射、早期分類與逐日回補仍待驗證 |
| 外資現貨買賣超金額（E-Shop 歷史產品） | TWSE E-Shop | 2004-02-19 起；付費 | 未下載 | 日 | 未測 | 每月訂閱；14:50／19:40 版本範圍不同 |
| 市場成交金額（外資比率分母） | TWSE FMTQIK | 1990-01-04 起（頁面標示） | 2022-10-24 樣本已核對 | 日 | 未測 | 免費 CSV／月報；TWSE 上市市場，不含 OTC／期貨；已查樣本交易類型／外幣換算註記與 BFI82U 相符，起始日及全期完整度未測 |
| 外資 TX 未平倉淨部位 | TAIFEX | 歷史起於 2008-04-07；公開查詢近 3 年 | 2026-09-14 | 日 | 未測 | OpenAPI 只回最新快照；舊檔需申請 |
| TX 行情（Basis） | TAIFEX | 官方年檔選單列 1998–2025；全檔稽核 28 份 ZIP，84,828 筆 TX 列、6,819 個年度日期、0 錯誤、0 重複鍵 | 2025 最新年度年檔（資料至 2025-12-31） | 日／分盤別 | 每年度 TX 日期都有正成交量列；1998–2016 無盤別，2017 起 schema 轉換，2018–2025 含一般／盤後 | 1998 年 TAIFEX 官方日曆仍未找到；TWSE 史料可解釋當年星期六交易背景但不能取代 TX 日曆；2026 年度檔尚未列出；價格與 Basis 仍需固定近月及轉倉規則 |
| TXO OI Put/Call Ratio | TAIFEX | 完整分段稽核涵蓋 2001-12-24 起；292 段、6,090 列、日期唯一 | 2026-09-16 | 日 | 交易日曆缺日原因未逐日核對 | 單次起訖日期差最多 30 日；OpenAPI 為最新快照；稽核報告見 [workflow run 35184984406](https://github.com/TaylorYam/Huda-taiwan-market-quant/actions/runs/35184984406) |
| Taiwan VIX（日收盤） | TAIFEX | 免費頁當月與前三個完整月份、指數查詢近 3 年；付費歷史商品自 2007 年 | 2026-09-15 | 日 | 2026-09 月檔 12 個資料日已由 parser dry-run 驗證；全期缺值率未測 | 月檔 tab-separated 純文字可累積；已提供 `taifex_vix` parser／ObservationStore collector 與平日 Actions 入口；任意日期 endpoint 未知；付費商品 NT$3,000／半年 |

### 逐項來源與欄位

| 原始資料集（支援因子） | 官方來源／實測結果 | 最早可得／查詢窗口 | 頻率、欄位與自動化 | 缺值率與注意事項 |
|---|---|---|---|---|
| TAIEX 指數 OHLC（MA20/MA60、20 日動能） | [TWSE 發行量加權股價指數歷史資料](https://www.twse.com.tw/zh/indices/taiex/mi-5min-hist.html?myear=)；月份查詢及 CSV 下載。官方標示資料自 1999-01-05 起，實測查詢早於此日會拒絕，並成功讀取 2000-01、2024-01 樣本。 | 1999-01-05 起；依月份查詢 | 日資料：日期、開盤、最高、最低、收盤指數。按月查詢可自動化；頁面也提供 CSV。 | 未測。足以支援 3 年視窗；擷取時應固定查詢月與本地交易日期。 |
| 外資現貨流（T86 股數） | 免費 [TWSE T86 三大法人買賣超日報](https://www.twse.com.tw/fund/T86?date=20260914&response=json&selectType=ALL)；實測 2026-09-14 回傳 JSON。 | 免費 T86 可查至 2012-05-02；測試更早日期時來源拒絕。數值為股數，不是模型所需的買賣超金額。 | 每交易日；逐證券買進／賣出／買賣超股數，含外資及陸資與外資自營商等分類。 | 未測。T86 註明為當日原始成交統計，不含錯帳、更正帳號調整。不得把股數直接當成金額。 |
| 外資現貨流（公開 BFI82U 金額） | 免費 [TWSE 三大法人買賣金額統計表 BFI82U](https://www.twse.com.tw/zh/trading/foreign/bfi82u.html)；可查日報並有 CSV 入口。查到 2004 樣本有外資買進、賣出、買賣差額，單位為元；2022-10-24 與 2026-09-14 報表註記含一般、零股、盤後定價、鉅額，排除拍賣／標購。 | 頁面標示自 2004-04-07 起；供應起日不是已驗證的逐日完整歷史。 | 市場彙總金額，不是個股明細；2004 報表列「外資」，目前欄位拆分外資及陸資（不含外資自營商）與外資自營商。 | 已查報表的交易類型與外幣換算註記和 FMTQIK 樣本相符；免費報表對應哪個 E-Shop 版次、早期分類、查詢連續性及完整度仍待核。見[現貨口徑補查](phase0-cash-market-scope-v0.1.md)。 |
| 外資現貨買賣超金額（E-Shop 歷史商品） | TWSE [三大法人買賣金額統計表](https://eshop.twse.com.tw/zh/product/detail/d31c1b9570ae47058ec83a0bb1ffa419) 提供歷史訂購路徑。 | 商品起點 2004-02-19；可訂單筆最多 5 年。 | 日資料；官方頁列 14:50 不含綜合帳戶／鉅額、19:40 含綜合帳戶／鉅額；2026-05-29 起格式變更。內用 NT$1,000／月、外部使用 NT$1,500／月。 | 未下載。公開 BFI82U 也有金額資料，是否需要付費歷史商品須看免費頁的範圍與版次能否滿足，不表示已選購。 |
| 市場成交金額（外資比率分母） | TWSE [FMTQIK 每日市場成交資訊](https://www.twse.com.tw/zh/trading/historical/fmtqik.html)；月報／CSV 含每日成交金額及加權指數。已查 2017-09-20 與 2022-10-24 樣本。 | 官方頁標示自 1990-01-04 起；尚未測起始日或完整缺值。 | TWSE 上市市場，含一般、零股、盤後定價與鉅額，排除拍賣／標購；外幣成交值按 15:30 公告匯率換算。 | 目前查到的 BFI82U 報表樣本與 FMTQIK 在列示交易類型及外幣換算說明相符；不能外推至所有歷史日期／E-Shop 版次。不包含 OTC 或期貨成交額。見[現貨口徑補查](phase0-cash-market-scope-v0.1.md)。 |
| 外資 TX 未平倉淨部位（及 5 日變化） | TAIFEX [三大法人區分期貨契約資料](https://www.taifex.com.tw/cht/3/futContractsDateView)；[OpenAPI 規格](https://openapi.taifex.com.tw/) 的 `MarketDataOfMajorInstitutionalTradersDetailsOfFuturesContractsBytheDate` 可取得最新快照。實測最新快照為 2026-09-14，共 66 列；以契約 `臺股期貨`、法人 `外資及陸資` 取 `OpenInterest(Net)`。 | 官方頁標示資料自 2008-04-07 起；一般歷史查詢僅提供查詢日前三年，較早資料需填公開資料申購表。OpenAPI 端點沒有日期查詢參數，只回最新快照。 | 每交易日。欄位含契約、法人、買／賣／淨交易量與買／賣／淨未平倉口數。OpenAPI 適合每日增量保存；直接 API 不適合回填。 | 未測。每日 13:45 公布前的資料不完整；16:15 最後一批才含國外成分證券 ETF／境外指數 ETF 交易量。回測須選定一致的公布版本與 as-of 時間。最後結算日未平倉量自 2008-12-17 起不含當月份到期商品。 |
| TX 期貨行情（Basis） | TAIFEX [期貨每日行情查詢](https://www.taifex.com.tw/cht/3/futDailyMarketReport?commodityId=TX)、[年度行情下載](https://www.taifex.com.tw/cht/3/dlFutDailyMarketView) 及 OpenAPI `DailyMarketReportFut`。年度 ZIP 表單 POST `/cht/3/futDataDown`（`down_type=2`、`his_year`）；選單列 1998–2025 共 28 年；[全期稽核 run 35186014961](https://github.com/TaylorYam/Huda-taiwan-market-quant/actions/runs/35186014961) 已逐年完成。 | 1998–2025 全檔稽核：84,828 筆 TX 列、6,819 個年度日期；1998 首末 1998-07-21–12-31（625／125），2024 為 6,755／242，2025 為 6,055／243。 | CP950 CSV；1998–2014 資料列 16 欄，2015–16 出現 16／17 欄，2017 為 18／19 欄，2018–2025 為 20 欄加一筆單欄終止列。2017 起保留交易時段，近年一般／盤後資料應用盤別納入主鍵；TX 價格與 Basis 需固定近月及轉倉規則。 | 28 年均無年度內重複鍵，且每個年度 TX 日期都有正成交量列；2024/25 日期集合與官方行事曆及臨時休市公告相符。1998 歷史官方交易日曆未取得，不能判定逐日缺漏；2026 年度檔尚未列出。見[TAIFEX 歷史窗口補查](phase0-taifex-history-v0.1.md)。 |
| TXO OI Put/Call Ratio | TAIFEX [Put/Call Ratio 官方頁](https://www.taifex.com.tw/cht/3/dlPcRatio) 網頁表單 POST 支援日期區間；下載端點為 `/cht/3/pcRatioDown`，欄位為日期、買／賣權成交量及比率、Put／Call OI 及比率；OpenAPI `GET /PutCallRatio` 無日期參數，只回最新快照。 | 最早可取列 2001-12-24；全期稽核最新資料日 2026-09-16。UI 起訖相差最多 30 個曆日、端點含在內；292 段、6,090 列、6,090 個唯一日期、0 錯誤／重複。 | 每交易日；官方頁合併週到期與月契約。回補按非重疊日曆區段完成；缺列保留為無資料，不補 0。 | 全期日期唯一性與端點可重現；仍需以交易日曆解釋無資料日，CSV 編碼尚未由官方文件明載。 |
| Taiwan VIX（日收盤） | 免費[每日收盤頁](https://www.taifex.com.tw/cht/7/vixDaily3MNew)可見 2026/06–09 月；月檔例如 [`202609new.txt`](https://www.taifex.com.tw/file/taifex/Dailydownload/vix/log2data/202609new.txt) 為含標頭／分隔線的 tab-separated 純文字，`20260915` 有效欄位為 VIX 27.29、收盤前 1 分鐘平均 27.29；[指數專區](https://www.taifex.com.tw/indes/index.aspx)「3年」圖表窗口為 2023-09-16–2026-09-15。 | 免費日收盤頁：當月與前三個完整月份；圖表查詢：最近三年。付費歷史商品頁列示起自 2007-01-01、至申購日前一完整月份，NT$3,000／半年。任意日期下載 endpoint 與 CSV 格式未知。 | 日級 parser 已處理七欄對齊，輸出交易日期、來源時間、VIX、收盤前 1 分鐘平均與 effective_at；月檔可按月份累積後自行篩選日期。 | 2026-09 月檔 12 個資料日已 dry-run 核實，但完整日序列缺值率未測；圖表尚未驗證可匯出日級資料。付費商品不代表已取得資料。 |

## 對共同回測期間的影響

1. **目前不能鎖定完整 8 因子回測起日。** TAIFEX 外資期貨部位的官網歷史查詢只有近三年，舊資料須申請；VIX 免費檢視最多近三年，官方更長 VIX 歷史需購買；PCR 已完成 2001-12-24 至 2026-09-17 的 292 段回補與日期唯一性檢查，但仍需交易日曆缺日核對。
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
