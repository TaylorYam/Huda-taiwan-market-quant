# TWSE 現貨金額因子來源查證 v0.1

查核日期：2026-09-16（Asia/Taipei）。範圍：TWSE 官方免費 BFI82U、FMTQIK 查詢頁與報表，以及 TWSE Data E-Shop 公開商品說明／樣本連結。只查閱公開頁面與報表，未購買、申購或訂閱資料。本文件不判定自動化抓取、保存或再散布權利，也不宣稱歷史序列完整。

## 結論

本次可重現查到：免費 BFI82U 在頁面所列起日 2004-04-07 有日報；2004-04-06 日報無符合條件的資料。FMTQIK 同時顯示 2004-04-06 是交易日，故 BFI82U 前一日空白是它尚未提供該日資料，不能解讀成休市。2004-04-07 的免費 BFI82U 註記不含鉅額交易，但同日 FMTQIK 註記含鉅額。2022-10-24 與 2026-09-14 的 BFI82U 及 FMTQIK 月報均已保存配對列與報表註記；在這兩個已查樣本日，兩報表的主要交易類別與外幣換算說明相符。歷史分類和 E-Shop 版次仍未解決。欄位分類亦從早期「外資」改為現行拆列「外資及陸資（不含外資自營商）」與「外資自營商」。

E-Shop 說明列出每日 14:50（不含綜合帳戶及鉅額）及 19:40（含綜合帳戶及鉅額）兩版，也列出 BFI82U 與 BFIBGU 兩個檔案碼，但未將任一檔案碼對應到產製時間。公開 CSV 樣本在本次執行環境中未能取得可讀位元組，因此無法檢查樣本內容或用其建立映射。不得只憑檔名、鉅額註記或樣本連結順序猜測映射。

因此，現貨因子的**歷史序列實作仍應阻擋在版本定義**：至少要固定來源（免費報表或特定 E-Shop 檔案）、報表時間／版次、外資分類處理、涵蓋交易類型及有效起點。可記錄免費來源的探測結果，但不應把它當成口徑已跨期一致的歷史因子。

## 免費 BFI82U 查詢實測

官方查詢頁標示「本資訊自民國 93 年 4 月 7 日起提供」，並提供「列印 / HTML」及「CSV 下載」。此為官方標示起日；本次只驗證列出的樣本日期，不代表 2004-04-07 之後每日均有資料或無缺漏。

| 交易日 | HTML 查詢 URL | CSV 查詢 URL | 本次觀察 |
|---|---|---|---|
| 2004-04-06 | [BFI82U 2004-04-06 HTML](https://www.twse.com.tw/fund/BFI82U?response=html&dayDate=20040406&weekDate=20040405&monthDate=20040406&type=day) | [BFI82U 2004-04-06 CSV](https://www.twse.com.tw/fund/BFI82U?response=csv&dayDate=20040406&weekDate=20040405&monthDate=20040406&type=day) | 查詢回覆「很抱歉，沒有符合條件的資料!」。FMTQIK 同日有成交列，故這是 BFI82U 起始日前無資料，不是非交易日。 |
| 2004-04-07 | [BFI82U 2004-04-07 HTML](https://www.twse.com.tw/fund/BFI82U?response=html&dayDate=20040407&weekDate=20040405&monthDate=20040407&type=day) | [BFI82U 2004-04-07 CSV](https://www.twse.com.tw/fund/BFI82U?response=csv&dayDate=20040407&weekDate=20040405&monthDate=20040407&type=day) | 報表存在，單位為元；列名是早期的「自營商、投信、外資、合計」。 |
| 2022-10-24 | [BFI82U 2022-10-24 HTML](https://www.twse.com.tw/fund/BFI82U?response=html&dayDate=20221024&weekDate=20221017&monthDate=20221024&type=day) | [BFI82U 2022-10-24 CSV](https://www.twse.com.tw/fund/BFI82U?response=csv&dayDate=20221024&weekDate=20221017&monthDate=20221024&type=day) | 報表存在，單位為元；使用現行拆分分類。買賣金額及註記列於下表與比對說明。 |
| 2026-09-14 | [BFI82U 2026-09-14 HTML](https://www.twse.com.tw/fund/BFI82U?response=html&dayDate=20260914&weekDate=20260914&monthDate=20260914&type=day) | [BFI82U 2026-09-14 CSV](https://www.twse.com.tw/fund/BFI82U?response=csv&dayDate=20260914&weekDate=20260914&monthDate=20260914&type=day) | 報表存在，單位為元；使用現行拆分分類。買賣金額及註記列於下表與比對說明。 |

2004-04-07 HTML 欄名為 `單位名稱`、`買進金額`、`賣出金額`、`買賣差額`；頁面單位為「元」。原始列如下：

| 單位名稱 | 買進金額（元） | 賣出金額（元） | 買賣差額（元） |
|---|---:|---:|---:|
| 自營商 | 1,900,305,020 | 2,496,451,006 | -596,145,986 |
| 投信 | 1,833,097,110 | 3,016,452,186 | -1,183,355,076 |
| 外資 | 15,673,391,640 | 9,255,777,003 | 6,417,614,637 |
| 合計 | 19,406,793,770 | 14,768,680,195 | 4,638,113,575 |

2004-04-07 報表註記逐項說明：自營商表示證券自營商專戶；投信表示本國投資信託基金；外資及陸資依頁面所列投資人管理辦法辦理登記；統計含一般、零股、盤後定價，不含鉅額、拍賣、標購；以當日原始成交情形統計，不以券商錯帳或更正帳號調整；投信部分不含當日綜合帳戶買賣金額。

2022-10-24 與 2026-09-14 的報表列名皆為「自營商(自行買賣)」、「自營商(避險)」、「投信」、「外資及陸資(不含外資自營商)」、「外資自營商」、「合計」。原始列如下，單位均為元：

| 日期 | 類別 | 買進金額 | 賣出金額 | 買賣差額 |
|---|---|---:|---:|---:|
| 2022-10-24 | 自營商(自行買賣) | 5,250,113,604 | 1,466,844,920 | 3,783,268,684 |
| 2022-10-24 | 自營商(避險) | 7,998,791,476 | 7,967,868,220 | 30,923,256 |
| 2022-10-24 | 投信 | 2,878,166,096 | 1,271,331,644 | 1,606,834,452 |
| 2022-10-24 | 外資及陸資(不含外資自營商) | 62,884,117,034 | 64,291,989,242 | -1,407,872,208 |
| 2022-10-24 | 外資自營商 | 30,428,830 | 29,364,110 | 1,064,720 |
| 2022-10-24 | 合計 | 79,011,188,210 | 74,998,034,026 | 4,013,154,184 |
| 2026-09-14 | 自營商(自行買賣) | 5,878,730,505 | 9,857,183,925 | -3,978,453,420 |
| 2026-09-14 | 自營商(避險) | 21,261,160,728 | 32,375,418,926 | -11,114,258,198 |
| 2026-09-14 | 投信 | 16,619,233,322 | 12,923,730,780 | 3,695,502,542 |
| 2026-09-14 | 外資及陸資(不含外資自營商) | 236,359,477,681 | 273,323,049,537 | -36,963,571,856 |
| 2026-09-14 | 外資自營商 | 0 | 0 | 0 |
| 2026-09-14 | 合計 | 280,118,602,236 | 328,479,383,168 | -48,360,780,932 |

兩個日期的 BFI82U 報表註記均指出：外資自營商金額已計入自營商金額，因此不納入三大法人合計；統計含一般、零股、盤後定價、鉅額，不含拍賣、標購；以當日原始成交資料統計，不依券商錯帳／更正帳號調整；外幣成交值以 TWSE 當日下午 3:30 公告匯率換算後加入成交金額。這些是已查日期的報表註記，不能外推到未查日期或所有 E-Shop 版次。

## FMTQIK 日期與欄位實測

FMTQIK 官方查詢頁標示自民國 79 年 1 月 4 日（1990-01-04）起提供，並提供 HTML、CSV。以 `date=YYYYMMDD` 查詢時，回覆是該月份報表；因此以下比較的是月報中的日期列，不是只回傳單日的文件。

HTML 欄名為 `日期`、`成交股數`、`成交金額`、`成交筆數`、`發行量加權股價指數`、`漲跌點數`。報表單位行為「元、股」；指數及漲跌點數欄如頁面顯示的小數值，沒有另列單位行。已核對列如下：

| 查詢日期 | 報表列日期 | 成交股數 | 成交金額（元） | 成交筆數 | 發行量加權股價指數 | 漲跌點數 |
|---|---|---:|---:|---:|---:|---:|
| 1990-01-04 | 79/01/04 | 1,134,514,582 | 121,774,345,167 | 351,190 | 9,853.15 | 0.00 |
| 1990-01-03 | 79/01 月報未見 79/01/03 列；月報第一列為 79/01/04 | — | — | — | — | — |
| 2004-04-06 | 93/04/06 | 6,776,486,321 | 161,013,125,824 | 1,177,379 | 6,635.54 | -47.19 |
| 2004-04-07 | 93/04/07 | 4,384,680,838 | 100,007,108,521 | 792,334 | 6,646.74 | 11.20 |
| 2022-10-24 | 111/10/24 | 5,107,731,268 | 180,359,486,515 | 1,442,269 | 12,856.98 | 37.78 |
| 2026-09-14 | 115/09/14 | 8,822,022,033 | 665,316,266,033 | 4,064,716 | 45,862.52 | -322.33 |

2004-04-06 的成交列證實該日 TWSE 集中市場有交易，並協助區分 BFI82U 前一日的無資料回覆與休市。1990-01-03 的查詢仍回傳 79 年 1 月報，第一個可見列是官方頁所列起日 1990-01-04；不能將起日前沒有列解讀為 1990-01-04 之後資料完整。

下列近年同日比較 URL 可供重現查詢；相應日期列已加入上方表格，報表註記於下段記錄：

| 交易日 | FMTQIK HTML 月報 | FMTQIK CSV 月報 | 比對狀態 |
|---|---|---|---|
| 2022-10-24 | [FMTQIK 2022-10 月報](https://www.twse.com.tw/exchangeReport/FMTQIK?date=20221024&response=html) | [FMTQIK 2022-10 CSV](https://www.twse.com.tw/exchangeReport/FMTQIK?date=20221024&response=csv) | 已保存 111/10/24 列與報表註記。 |
| 2026-09-14 | [FMTQIK 2026-09 月報](https://www.twse.com.tw/exchangeReport/FMTQIK?date=20260914&response=html) | [FMTQIK 2026-09 CSV](https://www.twse.com.tw/exchangeReport/FMTQIK?date=20260914&response=csv) | 已保存 115/09/14 列與報表註記。 |

非交易日檢查使用 [FMTQIK 2026-09-13 月報](https://www.twse.com.tw/exchangeReport/FMTQIK?date=20260913&response=html)。2026-09-13 為星期日，月報沒有 115/09/13 列，月報中在 115/09/11 後接 115/09/14。這與 2004-04-06 是交易日但 BFI82U 尚未提供資料的情況不同。

2022-10-24 與 2026-09-14 的 FMTQIK 月報均註明：當日統計含大盤、零股、盤後定價及鉅額，不含拍賣、標購；外幣成交值按 TWSE 當日下午 3:30 公告匯率換算後加入成交金額。與兩日 BFI82U 報表對照，已核對的交易類別及匯率註記一致，兩邊金額單位均為元；BFI82U 的分子類別是「外資及陸資（不含外資自營商）」，FMTQIK 則是全市場成交金額分母。BFI82U 另記載採當日原始成交、不依券商錯帳或更正帳號調整；FMTQIK 這兩份月報沒有相同文字註記，因此不把該項聲明視作已交叉確認。這兩日只代表樣本日期，不能推及完整歷史或 E-Shop 版次。

2004-04-07 的 BFI82U（明載不含鉅額）與同日 FMTQIK（明載含鉅額）至少在鉅額交易範圍不一致；且 BFI82U 早期分類「外資」與近年拆分列不同。因此，已核對的近年樣本只能證明特定日期的報表註記和欄位，不足以建立跨期完全可比的歷史因子。

## E-Shop 檔案碼、時間版次與樣本

TWSE Data E-Shop 商品頁提供以下明文資料：

- 商品「三大法人買賣金額統計表」的資料起始日為 2004-02-19，週期每日，格式 TEXT、CSV。
- 商品檔案碼列為 `BFI82U`、`BFIBGU`；商品資料內容描述為類別、買進金額、賣出金額、買賣超金額及合計。
- 每交易日 14:50 產製版不含綜合帳戶及鉅額；19:40 產製版含綜合帳戶及鉅額。
- 頁面各自提供 BFI82U、BFIBGU 的範例檔／CSV 範例連結，並提供自 2026-05-29 起的新版範例及新版格式說明。

商品頁把兩個檔案碼和兩個產製時間列在同一商品說明中，但未明確寫明哪個檔案碼是 14:50、哪個是 19:40。免費 BFI82U 近年報表註記含鉅額，能證明該報表日期包含鉅額，卻不能單獨證明免費報表就是 E-Shop 19:40 檔：E-Shop 19:40 另外明確寫含綜合帳戶，免費報表沒有明確標示與該付費檔相同的帳戶範圍。

本次嘗試透過官方商品頁的 BFI82U 與 BFIBGU CSV 範例連結讀取內容。Web 閱讀器拒絕 `application/octet-stream`；瀏覽器直接開啟 CSV 被用戶端阻擋；本機 PowerShell／curl 的 Schannel 握手未完成，Python 亦回報伺服器憑證缺少 Subject Key Identifier。這是本次環境無法取得可讀樣本內容的限制，不代表官方檔案對所有使用者或環境都不可下載。故本次沒有比較兩份 CSV 的資料列，也沒有取得任何可用來連結檔案碼與 14:50／19:40 的樣本證據。

免費 BFI82U 與 FMTQIK 查詢頁均提供 CSV 下載按鈕；上表已列出依官方端點與查詢參數組成的直接 CSV URL，方便人工重試。本次環境未取得可讀 CSV 位元組；直接 CSV URL 透過 Web 閱讀器查詢時回覆「URL is not safe to open」，該錯誤是閱讀器的安全限制，不是 TWSE 伺服器回覆，也不能據此判定 CSV 連結失效。因此上文所列欄名是 HTML 報表欄名，不宣稱已比較 HTML 與 CSV 欄名、編碼或數值一致性。官方提供 CSV 選項本身不代表批次自動化權利已確認。

## 因子實作判定與待解缺口

**判定：歷史現貨外資因子仍阻擋在版本定義。** 在完成明確定義前，不要將免費 BFI82U 與 FMTQIK 直接視為跨期同口徑資料來計算並回測「外資 5 日買賣超比例」。目前至少有下列未解項目：

1. 固定分子要用免費報表、E-Shop BFI82U 或 E-Shop BFIBGU；若用 E-Shop，須取得可核對的產品檔案定義及時間版次映射。
2. 定義 14:50／19:40 快照、綜合帳戶及鉅額交易納入規則，並確定分子和 FMTQIK 分母按同一交易類型對齊。
3. 定義歷史分類轉換：2004 年的「外資」與現行外資及陸資拆列，以及因外資自營商已併入自營商金額而不計入合計的規則，如何映射到模型的「外資」分子。
4. 以合法可取得的原始 CSV／TEXT 樣本核實 HTML 對照、檔案欄位、編碼、起始附近日期、修訂與缺值。官方列出的供應起日不等於每日無缺，也不等於已驗證序列完整。
5. 另行確認自動化收集、保存與展示的權利範圍；本次未購買或訂閱資料，權利狀態未知。

若先做即時資料原型，仍須標記來源為指定日期的「免費 BFI82U HTML 報表觀察值」，保留報表列名、單位、資料日期、抓取時間及交易範圍註記；不可把該原型描述成已驗證的歷史因子序列。

## 官方來源與可重現查詢

- [TWSE 免費 BFI82U 查詢頁](https://www.twse.com.tw/zh/trading/foreign/bfi82u.html)（頁面起始日、日期選擇器、HTML／CSV 下載入口）
- [BFI82U 2004-04-06 HTML](https://www.twse.com.tw/fund/BFI82U?response=html&dayDate=20040406&weekDate=20040405&monthDate=20040406&type=day)；[CSV](https://www.twse.com.tw/fund/BFI82U?response=csv&dayDate=20040406&weekDate=20040405&monthDate=20040406&type=day)
- [BFI82U 2004-04-07 HTML](https://www.twse.com.tw/fund/BFI82U?response=html&dayDate=20040407&weekDate=20040405&monthDate=20040407&type=day)；[CSV](https://www.twse.com.tw/fund/BFI82U?response=csv&dayDate=20040407&weekDate=20040405&monthDate=20040407&type=day)
- [BFI82U 2022-10-24 HTML](https://www.twse.com.tw/fund/BFI82U?response=html&dayDate=20221024&weekDate=20221017&monthDate=20221024&type=day)；[CSV](https://www.twse.com.tw/fund/BFI82U?response=csv&dayDate=20221024&weekDate=20221017&monthDate=20221024&type=day)
- [BFI82U 2026-09-14 HTML](https://www.twse.com.tw/fund/BFI82U?response=html&dayDate=20260914&weekDate=20260914&monthDate=20260914&type=day)；[CSV](https://www.twse.com.tw/fund/BFI82U?response=csv&dayDate=20260914&weekDate=20260914&monthDate=20260914&type=day)
- [TWSE Data E-Shop 三大法人買賣金額統計表商品頁](https://eshop.twse.com.tw/zh/product/detail/d31c1b9570ae47058ec83a0bb1ffa419)（起始日、檔案碼、時間版次、格式及官方樣本連結）
- [TWSE FMTQIK 查詢頁](https://www.twse.com.tw/zh/trading/historical/fmtqik.html)（頁面起始日、日期選擇器、HTML／CSV 下載入口）
- [FMTQIK 1990-01-04](https://www.twse.com.tw/exchangeReport/FMTQIK?date=19900104&response=html)；[FMTQIK 前一日參數 1990-01-03](https://www.twse.com.tw/exchangeReport/FMTQIK?date=19900103&response=html)
- [FMTQIK 1990-01-04 CSV](https://www.twse.com.tw/exchangeReport/FMTQIK?date=19900104&response=csv)；[FMTQIK 1990-01-03 CSV](https://www.twse.com.tw/exchangeReport/FMTQIK?date=19900103&response=csv)
- [FMTQIK 2004-04-06](https://www.twse.com.tw/exchangeReport/FMTQIK?date=20040406&response=html)；[FMTQIK 2004-04-07](https://www.twse.com.tw/exchangeReport/FMTQIK?date=20040407&response=html)
- [FMTQIK 2004-04-06 CSV](https://www.twse.com.tw/exchangeReport/FMTQIK?date=20040406&response=csv)；[FMTQIK 2004-04-07 CSV](https://www.twse.com.tw/exchangeReport/FMTQIK?date=20040407&response=csv)
- [FMTQIK 2022-10-24 HTML 月報](https://www.twse.com.tw/exchangeReport/FMTQIK?date=20221024&response=html)；[CSV](https://www.twse.com.tw/exchangeReport/FMTQIK?date=20221024&response=csv)
- [FMTQIK 2026-09-14 HTML 月報](https://www.twse.com.tw/exchangeReport/FMTQIK?date=20260914&response=html)；[CSV](https://www.twse.com.tw/exchangeReport/FMTQIK?date=20260914&response=csv)；[官方 OpenAPI 回應](https://openapi.twse.com.tw/v1/exchangeReport/FMTQIK)
- [FMTQIK 非交易日測試 2026-09-13 HTML](https://www.twse.com.tw/exchangeReport/FMTQIK?date=20260913&response=html)；[CSV](https://www.twse.com.tw/exchangeReport/FMTQIK?date=20260913&response=csv)
