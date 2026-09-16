# Phase 0 官方資料來源補查 v0.1

查核日期：2026-09-15（Asia/Taipei）
範圍：Phase 0 Issue 1–2 的官方公開來源、歷史窗口、查詢入口與費用界線。除官方公開網頁查詢外，未購買或申購資料；沒有選定付費商品。

## 核心結論

| 資料 | 已查證 | 未解事項 |
|---|---|---|
| 外資現貨金額 | 免費 TWSE BFI82U 網頁標示自 2004-04-07 提供，日報含買進、賣出、買賣差額，單位元，並提供 CSV。2004-04-07 頁面確有「外資」合計列。 | E-Shop 商品列始日為 2004-02-19；自由頁與商品涵蓋起點、格式版本及交易類型尚未逐日對帳。自動抓取授權／穩定端點未核定。 |
| 成交金額分母 | 免費 TWSE FMTQIK 自 1990-01-04 提供，報表按月呈列每日成交金額與加權指數，有 CSV。 | BFI82U 的官方註記對鉅額交易有不同版本：與 FMTQIK 是否同口徑須先固定版本並做同日數值核對。 |
| 外資台指期部位 | 公開查詢資料起於 2008-04-07；一般查詢僅近三年，舊資料有官方申請／E-Data Shop 路徑。 | 舊檔版本、授權是否涵蓋自用儲存、CI 與報告展示仍待核對；未申購。 |
| TX 年行情 ZIP | 官方年度下拉選單最早可選 1998；TX 最後結算價資料頁標示自 1998-09 起。 | 未下載 ZIP 驗證其內 TX 日行情的契約欄位及第一筆日期。 |
| TXO PCR | 官方頁有起訖日期欄位及 CSV 下載，且註明週到期與月到期契約合併。 | 官方頁未標示歷史下界或最大查詢區間；未驗證早期日期是否可回補。 |
| Taiwan VIX | 免費指數頁可查最近三年；每日收盤頁含當月與前三個月。新版付費歷史商品標示 2007-01 起。 | 免費自動化回補、付費商品日收盤欄位／頻率仍需樣本確認；未申購。 |

## 1. TWSE 外資現貨分子與成交金額分母

### 免費外資買賣金額：BFI82U

[TWSE BFI82U 公開查詢頁](https://www.twse.com.tw/zh/trading/foreign/bfi82u.html) 的日報下拉選單最早到民國 93 年，頁面標示「自民國 93 年 4 月 7 日起提供」，並有 CSV 下載。實際查詢 2004-04-07 顯示「單位：元」及 `單位名稱／買進金額／賣出金額／買賣差額` 欄；當日「外資」列為買進 15,673,391,640 元、賣出 9,255,777,003 元、買賣差額 6,417,614,637 元。這證明公開頁能提供歷史市場彙總金額，可作現貨金額因子的候選分子；但它不是按個股明細，也尚未驗證自動批次回補權限或服務保證。

該 2004 報表類別名為「外資」；現行報表則拆為「外資及陸資（不含外資自營商）」和「外資自營商」。外資自營商也不納入三大法人合計，須在資料轉換中保留類別定義，不可直接假定歷史與現行列完全一致。

**鉅額交易註記存在官方版本差異。** 直接查閱公開頁的 2004-04-07 報表，註記為「本統計資訊含一般、零股、盤後定價，不含鉅額、拍賣、標購」。TWSE 官方搜尋索引所列 2026-09-11 BFI82U 報表則註記「含一般、零股、盤後定價、鉅額，不含拍賣、標購」。[E-Shop BFI82U/BFIBGU 商品頁](https://eshop.twse.com.tw/zh/product/detail/d31c1b9570ae47058ec83a0bb1ffa419) 也說明每日 14:50 產製版不含綜合帳戶及鉅額，19:40 版則包含兩者。故免費頁與付費檔可取得的日期雖已分別確認，但要以何種快照、BFI82U/BFIBGU 檔案版本作為歷史因子仍未確認。先記錄報表版本，再做相同日期與 FMTQIK 的數值／涵蓋範圍核對。

E-Shop 商品頁列每日頻率、TEXT/CSV、歷史起點 2004-02-19、單筆最多訂購五年；內部使用標價 NT$1,000／月，外部使用 NT$1,500／月。這是官方價格與交付條件，不代表已採購或已確認授權適用本專案。它比免費頁標示的 2004-04-07 早約六週；此差異仍未解釋。

### 免費大盤成交金額：FMTQIK

TWSE [每日市場成交資訊](https://www.twse.com.tw/zh/trading/historical/fmtqik.html) 標示自民國 79 年 1 月 4 日（1990-01-04）提供，並有 CSV 下載。官方 [FMTQIK 歷史報表](https://www.twse.com.tw/exchangeReport/FMTQIK?date=20170920&response=html) 顯示一個月份內逐日的 `成交金額`、`發行量加權股價指數` 等欄位；因此每日金額序列可用於建立候選的五交易日市場成交值分母。報表註記為：「當日統計資訊含大盤、零股、盤後定價及鉅額交易，不含拍賣、標購」；外幣證券成交值按 TWSE 當日 15:30 公告匯率換算後納入。

這是 TWSE 集中市場的成交額統計。TWSE 首頁的市場統計分類列有股票、ETF、權證與 TDR；頁面註明櫃檯市場資訊由櫃買中心提供、期貨市場資訊由期交所提供。因此 FMTQIK 不應描述成包含 OTC 櫃買市場或期貨的全台市場成交額。若規格採五日分母，實作應以 TWSE 交易日計算五日加總；分子 BFI82U 是否採同一鉅額／綜合帳戶口徑仍須數值核對。

### T86 股數序列

免費 [T86 三大法人買賣超日報](https://www.twse.com.tw/fund/T86?response=html) 的外陸資等欄位為股數，不是金額。查詢 2012-04-30 回覆早於民國 101 年 5 月 2 日，2012-05-02 則成功；故查詢下界為 2012-05-02，不能直接替代 BFI82U 的金額分子。[下界錯誤回覆](https://www.twse.com.tw/fund/T86?date=20120430&response=html)｜[下界日期查詢](https://www.twse.com.tw/fund/T86?date=20120502&response=html)

## 2. TAIFEX 歷史資料

- **外資期貨部位：**[依日期查詢頁](https://www.taifex.com.tw/cht/3/futContractsDateView) 標示起日 2008-04-07；自 2012-05-01 起公開頁限查詢日前三年，較早資料須走官方歷史資料申請流程。[歷史資料申請頁](https://www.taifex.com.tw/cht/3/hisAppForm) 連到 [E-Data Shop 三大法人期貨資料](https://edatashop.taifex.com.tw/zh/product/detail/40283ab78906834a018906bec6390000)，商品標示可訂 2008-04-07 至前一完整月份、NT$1,500／月及單人單機等限制。13:45 與 16:15 未平倉發布版涵蓋交易類型不同，回測需固定快照時點。未申購。
- **TXO PCR：**[官方查詢／CSV 頁](https://www.taifex.com.tw/cht/3/dlPcRatio) 有起訖日期，可選期間未明示最長範圍；預設最近約一個月。官方 [OpenAPI 文件](https://openapi.taifex.com.tw/) 的 `GET /PutCallRatio` 是當期資料入口，現有探測未見日期回填參數。最早可回補日期仍未知；不能拿最新快照推論歷史完整性。
- **Taiwan VIX：**[指數專區](https://www.taifex.com.tw/indes/index.aspx) 可查最近三年；[每日收盤頁](https://www.taifex.com.tw/cht/7/vixDaily3MNew) 提供當月與前三個月。[新版歷史商品](https://edatashop.taifex.com.tw/zh/product/detail/40283ab7890b3664018924255bf2000f) 標示 2007-01 起，價格 NT$3,000／半年，且歷史頻率有 2018-11-19、2020-11-23 的變更。免費批次回補能力及付費格式中的穩定日收盤欄位未驗證。未申購。
- **TX 年行情：**[每日行情／年度 ZIP 頁](https://www.taifex.com.tw/cht/3/dlFutDailyMarketView) 的年度選單最早可選 1998 年，逐日查詢最多一個月；[TX 最後結算價頁](https://www.taifex.com.tw/cht/5/futIndxFSP) 標示資料自 1998-09 起。年度選項已查到，ZIP 內容未下載核驗，故不能宣稱 ZIP 的精確第一筆日期或欄位。

## 待 Issue 驗收的未解事項

1. 固定 BFI82U 免費頁與 E-Shop 歷史檔的快照／檔案版本，確認 2004-02-19 到 2004-04-06 的差異及現行外資分類映射。
2. 對同一交易日核對 BFI82U 外資淨買金額與 FMTQIK 成交金額所含交易類型；官方註記出現不同 BFI82U 版本，尚未完成數值 reconciliation。
3. 實測 PCR 最早日期與分段區間；檢查 1998 TX ZIP 實際內容；確認各付費檔授權、資料保存和 CI 使用權（如評估採購）。
4. 以上「最早」包括官方標示日期、可選日期和查詢測試下界，均不等於已驗證每日無缺或檔案首筆。

## 官方來源

- [TWSE BFI82U 公開日報](https://www.twse.com.tw/zh/trading/foreign/bfi82u.html)；[BFI82U 官方報表視圖](https://www.twse.com.tw/fund/BFI82U?response=html&type=day)
- [TWSE E-Shop BFI82U/BFIBGU 範圍、版本及價格](https://eshop.twse.com.tw/zh/product/detail/d31c1b9570ae47058ec83a0bb1ffa419)
- [TWSE 每日市場成交資訊 FMTQIK](https://www.twse.com.tw/zh/trading/historical/fmtqik.html)；[每日列範例及涵蓋註記](https://www.twse.com.tw/exchangeReport/FMTQIK?date=20170920&response=html)；[TWSE 市場統計分類](https://www.twse.com.tw/zh/)
- [TAIFEX 期貨三大法人查詢](https://www.taifex.com.tw/cht/3/futContractsDateView)；[歷史資料申請](https://www.taifex.com.tw/cht/3/hisAppForm)；[三大法人 E-Data Shop](https://edatashop.taifex.com.tw/zh/product/detail/40283ab78906834a018906bec6390000)
- [TAIFEX PCR](https://www.taifex.com.tw/cht/3/dlPcRatio)；[TAIFEX OpenAPI](https://openapi.taifex.com.tw/)
- [TAIFEX VIX 指數專區](https://www.taifex.com.tw/indes/index.aspx)；[每日收盤](https://www.taifex.com.tw/cht/7/vixDaily3MNew)；[VIX 歷史商品](https://edatashop.taifex.com.tw/zh/product/detail/40283ab7890b3664018924255bf2000f)
- [TAIFEX TX 年度行情 ZIP](https://www.taifex.com.tw/cht/3/dlFutDailyMarketView)；[TX 最後結算價起始月](https://www.taifex.com.tw/cht/5/futIndxFSP)
