# 近五年人工回補資料規格 v0.1

更新日期：2026-09-21（Asia/Taipei）

## 結論

若目標是把展示網站的每日資料延伸到近五年（建議先抓 `2021-09-01` 至目前最新交易日；目前已知資料到 `2026-09-18`，再依台股交易日篩選），目前真正的硬卡點只有兩項：

1. **外資台指期未平倉淨部位**：TAIFEX 公開日期查詢目前只能回溯約三年；較早資料需要官方歷史資料申請或 E-Data Shop 檔案。
2. **Taiwan VIX 日收盤**：免費圖表與查詢目前約三年；更早的日資料需要官方歷史資料申請或歷史商品檔案。

這兩項缺少時，Market Score 的完整五年曲線無法宣稱完整。其他資料集已有免費官方歷史入口，原則上不需要人工補檔。

## 請優先提供的兩類檔案

### A. 外資台指期未平倉淨部位

**最小需要範圍**：`2021-09-01` 至 `2023-09-24`。目前免費 rolling window 已涵蓋後段；若取得全段 `2021-09-01` 至目前最新交易日，驗證會更簡單。

每個交易日至少需要保留：

- 交易日期
- 契約：`臺股期貨`（TXF）
- 法人：`外資及陸資`
- 淨未平倉口數：`OpenInterest(Net)`
- 若檔案有提供：資料發布時間或版本（例如 13:45／16:15）

請保留原始檔，不要自行改欄名或補值。這個資料會用來計算外資台指期淨部位及其五日變化；沒有前置資料的第一個日期會明確標示為不可用，不會猜測成 0。

官方入口：[TAIFEX 三大法人區分期貨契約資料](https://www.taifex.com.tw/cht/3/futContractsDateView)；若查詢頁沒有目標日期，使用[歷史資料申請頁](https://www.taifex.com.tw/cht/3/hisAppForm)或官方 E-Data Shop。

### B. Taiwan VIX 日收盤

**最小需要範圍**：`2021-09-01` 至 `2023-09-24`。若取得全段 `2021-09-01` 至目前最新交易日，可直接和現有資料做重疊比對。

每個交易日至少需要保留：

- 交易日期
- Taiwan VIX 日收盤值
- 若檔案有提供：收盤前 1 分鐘平均值、來源時間或版本

請保留官方原始 CSV／TXT／ZIP，不要把缺日改成 0，也不要把盤中值當成日收盤值。

官方入口：[TAIFEX 指數專區](https://www.taifex.com.tw/indes/index.aspx)；若目標日期不在免費窗口，使用[歷史資料申請頁](https://www.taifex.com.tw/cht/3/hisAppForm)或[官方 VIX 歷史商品](https://edatashop.taifex.com.tw/zh/product/detail/40283ab7890b3664018924255bf2000f)。

## 不必人工找的資料

| 資料 | 官方免費入口 | 目前判斷 |
| --- | --- | --- |
| TAIEX 日 OHLC | [TWSE 加權指數歷史資料](https://www.twse.com.tw/zh/indices/taiex/mi-5min-hist.html?myear=) | 可按月份回補，官方資料自 1999-01-05 起 |
| 外資現貨買賣超金額 | [TWSE BFI82U](https://www.twse.com.tw/zh/trading/foreign/bfi82u.html) | 有日報與 CSV；需固定報表版本並做口徑核對 |
| 市場成交金額 | [TWSE FMTQIK](https://www.twse.com.tw/zh/trading/historical/fmtqik.html) | 有月報與 CSV，官方資料自 1990-01-04 起 |
| 台指期日行情 | [TAIFEX 歷史資料](https://www.taifex.com.tw/cht/3/futDailyMarketReport) | 年度檔與日期查詢可支援五年 |
| TXO Put/Call Ratio | [TAIFEX Put/Call Ratio](https://www.taifex.com.tw/cht/3/dlPcRatio) | 已完成長期分段稽核，仍需最後對交易日曆 |

BFI82U 仍要記錄報表版本（14:50／19:40 版本可能有涵蓋差異），但它目前不是五年回補的硬卡點。

## 檔案交付方式

請將原始檔依下列結構整理；檔名可以保留供應商原名：

```text
manual-backfill/
├─ taifex_institutional_oi/
│  ├─ 2021-09.csv
│  ├─ 2021-10.csv
│  └─ ...
├─ taifex_vix/
│  ├─ 2021-09.csv
│  ├─ 2021-10.csv
│  └─ ...
├─ twse_bfi82u/       # 若自動回補仍有缺口再放
└─ twse_fmtqik/       # 若自動回補仍有缺口再放
```

每一批檔案請另外附一個簡短的 `manifest.csv` 或 `README.txt`，記錄：來源網址、查詢起訖日、下載日期、資料版本，以及是否為 CSV／TXT／ZIP。不要把 Supabase 連線字串、GitHub Secret 或任何密碼放進資料夾。

拿到 A、B 兩類檔案後，專案會先做三件事：保留原檔 checksum、解析成標準日資料、以 TAIEX 交易日逐日列出缺值／重複／版本差異，通過後才重跑 Market Score。

## 「五年展示」和「五年正式回測」的差別

五年展示只要求五年內各因子有資料；因此補齊 `2021-09` 起的 OI 與 VIX 後即可處理。

正式回測目前使用三年 rolling percentile。若要求「五年前的第一天就已有完整三年暖機」，原始資料還要再往前約三年，約需八年資料；否則前段會保留為暖機期，不能當成完整可用訊號。這是計算規則造成的限制，不是資料抓取失敗。

## 目前可量化的阻塞狀態

- 既有近三年展示回補：`724 / 725` 個候選交易日可用。
- 唯一剩餘邊界缺口：`2023-09-25` 的外資台指期淨部位五日變化，因免費歷史窗口前沒有可驗證的前置 OI 列。
- 取得上述兩類人工檔案後，才可判斷五年範圍內是否還有個別交易日的來源缺列；在此之前不會用前值或 0 偽造這兩個因子。
