# Historical Data Window Policy v0.1

本文件定義 Market Direction Model v0.1 在建立歷史資料與回測期間時的起始區間原則。

## 核心想法

第一步不先假設一定可以回測 8 年或 10 年，而是實際抓取 8 個核心因子的官方免費歷史資料，確認每一份資料最早可以穩定取得到哪一天。

然後以 **核心因子中歷史期間最短的資料** 作為完整模型共同資料區間的基準。

例如：

```text
TAIEX                  2000-
外資現貨               2004-
外資台指期淨部位       2010-
Put/Call Ratio         2007-
Taiwan VIX             2015-
```

如果 Taiwan VIX 是最晚才開始的核心資料，則完整 8 因子模型的共同資料區間原則上從 Taiwan VIX 可用日開始。

這樣可以避免：

- 不同日期使用不同數量的因子
- 早期分數與近期分數定義不同
- 回測結果因缺值補法而失真

---

## 實際執行步驟

### Step 1：逐項抓取資料

對 8 個核心因子實際測試官方來源：

1. TAIEX 價格（MA20 / MA60、20 日動能）
2. 外資 5 日現貨買賣超
3. 外資台指期淨多空部位
4. 外資期貨淨部位 5 日變化
5. 期現貨價差 Basis
6. OI Put/Call Ratio
7. Taiwan VIX

其中 MA 與 20 日動能共用 TAIEX 原始行情，因此原始資料來源數量少於因子數量。

### Step 2：建立資料可用性表

每份資料至少記錄：

| 欄位 | 說明 |
|---|---|
| dataset | 資料名稱 |
| source | TWSE / TAIFEX |
| earliest_date | 最早可取得日期 |
| latest_date | 最新日期 |
| frequency | 日資料等更新頻率 |
| missing_ratio | 缺值比例 |
| stable | 是否適合自動化 |
| notes | 格式變更、特殊情況 |

### Step 3：找出共同資料起點

```text
raw_common_start = max(各核心資料 earliest_date)
```

也就是選擇「最晚開始的那份核心資料」作為完整模型的原始共同起點。

---

## 重要：原始資料起點不等於正式回測起點

部分因子需要歷史資料才能計算。

例如：

- MA60 至少需要 60 個交易日
- 20 日動能至少需要 20 個交易日
- 5 日累計／變化至少需要 5 個交易日
- 歷史百分位若使用 3 年 rolling window，則需要更長的歷史 warm-up period

因此必須區分：

```text
原始資料共同起點
        ↓
Warm-up / Lookback period
        ↓
第一個可正式產生完整 Market Score 的日期
        ↓
正式 Backtest Start
```

如果 v0.1 使用 3 年歷史百分位，理想做法是：

```text
先抓到足夠的前置歷史資料
→ 用來建立當時可知的百分位分布
→ 不把 warm-up 資料當成正式回測樣本
```

因此正式回測起始日期應由程式根據所有因子的最大 lookback requirement 自動決定，而不是直接等於 `raw_common_start`。

---

## 如果最短資料把回測壓得太短怎麼辦？

先不要自動刪除因子。

第一輪先以完整 8 因子模型的共同期間做回測。

若最短資料導致有效樣本明顯不足，例如只能剩下很短的牛市或單一市場環境，再另外比較：

```text
Model A：完整 8 因子，較短歷史
Model B：移除限制資料長度的因子，較長歷史
```

比較兩者的：

- Score 單調性
- 5 / 10 / 20 日 forward return
- 不同市場 Regime 穩定度
- Out-of-Sample 表現

只有在證據顯示某個因子造成資料期間過短、但又沒有提供足夠額外判斷力時，才考慮從核心模型移除。

---

## v0.1 決策原則

目前先採用：

> **先抓資料，再由最短的核心資料決定完整模型的共同原始區間。**

接著考慮各因子的 lookback / warm-up requirement，決定真正的正式回測起始日。

不要為了硬湊 8～10 年而使用品質較差、非官方或大量補值的資料。

資料品質與模型定義一致性優先於回測年份長度。

---

## 目前現況（2026-09-17 確認）：兩個因子有免費回補，但是會捲動的 3 年窗口，2010 仍不可達

Taiwan VIX 與法人期貨 OI（外資台指期淨部位、淨部位 5 日變化兩個因子的資料源）**確實有免費的歷史回補管道**，但先前的探測只測到「OpenAPI 沒有日期參數」與「log2data 月檔只有近 3～4 個月」，漏看了網站上另外兩個支援日期查詢的端點：

- 法人期貨 OI：`https://www.taifex.com.tw/cht/3/futContractsDateDown`（表單 POST，欄位 `queryStartDate`／`queryEndDate`／`commodityId`）。2026-09-17 實測 `commodityId=TXF`、`2023/10/02` 可查到真實資料（外資及陸資淨未平倉 -7012 口，含自營商／投信／外資三類多空口數與契約金額）。頁面前端 JS 寫死允許區間為 `2023/09/17`～`2026/09/17`。
- Taiwan VIX：`https://www.taifex.com.tw/indes/index.aspx/GetStockDayPrices`（JSON POST，欄位 `syid=TAIWANVIX`／`flag=MS`／`startDate`／`endDate`）。2026-09-17 實測 2023 年 10 月整月可查到每日收盤（例如 2023/10/02 = 13.99），測 2010/01 則回傳空陣列（無錯誤，純粹沒有資料）。

兩者都是**查詢當下往前推約 3 年的 rolling window**，不是固定的歷史起點：現在（2026-09）回補最早可拿到約 2023-09；若延後到 2027 年才做，最早只能拿到約 2024-09，2023 年的資料會從免費查詢窗口永久消失、沒有其他管道補回來。**因此若要保留 2023 年至今的資料，需要儘快執行一次性回補，不能無限期擱置。** 2010 仍在 3 年窗口之外，不論何時回補都拿不到；付費 E-Data Shop 對 VIX 最早只到 2007-01-01，法人期貨 OI 的付費歷史商品條件未知。

**修正後的共同起點分析**：目前的 collector（`taifex_vix.py`、`taifex_institutional.py`）只走「最新快照」端點，沒有使用上述兩個支援日期查詢的端點，因此**目前**這兩個因子的 `earliest_date` 仍等於 collector 第一次寫入的日期（約 2026-09-16／17）。但這是 collector 尚未實作回補功能的問題，不是資料源本身的限制。若補上使用這兩個端點的一次性回補，`earliest_date` 可以立即改善到約 2023-09；套用本文件的 `raw_common_start = max(各核心資料 earliest_date)` 公式，v0.1 共同起點可以達到約 **2023 年**，而不是 2026 年，但仍到不了 2010 年。

**v0.1 決定**：2010 在不付費、不改變模型必要因子設計的前提下不可達，維持 out of scope。但共同起點回到約 2023 年是免費且可行的，屬於獨立的實作待辦——幫 `taifex_vix.py`、`taifex_institutional.py` 加上使用 `futContractsDateDown`／`GetStockDayPrices` 的一次性回補邏輯。這項工作有時效性：rolling window 會持續往前捲動，愈晚做能拿到的歷史愈短。

## 後續進度（2026-09-17 稍後）：VIX／法人期貨 OI 回補已實作；外資現貨因子解除大部分閘門

上述一次性回補邏輯已實作（`fetch_vix_range`／`fetch_institutional_futures_range` 與對應的 `scripts/backfill_taifex_*_range.py`），待實際執行回補後即可把這兩個因子的 `earliest_date` 從 2026-09 改善到約 2023-09。

同一天另外解除了外資現貨因子（15% 權重）的版本定義閘門：查證發現 BFI82U 的鉅額交易口徑在 2004-04-07（不含鉅額）與 2008-06-05（含鉅額）之間轉換過，轉換後到 2026-09-14 為止 18 年樣本皆與 FMTQIK 一致；因此設定 `FOREIGN_CASH_VERIFIED_START = 2010-01-01`，該日期後的資料可正常計算。詳見 [`phase0-cash-factor-source-verification-v0.1.md`](phase0-cash-factor-source-verification-v0.1.md)。

**這不改變本文件先前的結論**：外資現貨因子的 2010 起點早於 VIX／法人期貨 OI 的 ~2023 起點，因此共同起點的瓶頸仍然是 VIX 與法人期貨 OI，不是外資現貨。8 個因子中，目前只有法人期貨 OI／VIX 的歷史回補尚未實際執行；其餘因子（含外資現貨）在有原始資料的前提下都已能正常算分——已用合成資料端對端驗證，`missing_factor_ids` 可以完全清空。

---

## Probe 結果與下一步

第一輪官方資料盤點與 Phase 0 補查分別見 [Data Availability Probe v0.1](data-availability-probe-v0.1.md) 與 [Phase 0 Source Research](phase0-source-research-v0.1.md)。除股數口徑的免費 T86 外，已找到免費 BFI82U 外資買賣金額日報表（頁面標示自 2004-04-07 起）及免費 FMTQIK 市場成交金額資料；外資分類／發布版本、同日交易類型口徑與可回補最早日仍須驗證。TAIFEX 外資期貨部位歷史頁只提供近三年、免費 Taiwan VIX 日期查詢最多近三年；PCR 可查歷史下界和 TX 年度 ZIP 首筆尚待實測。各資料集缺值率尚未計算。

下一步和驗收條件已排入 [`roadmap-v0.1.md`](roadmap-v0.1.md) Phase 0–1：先確認現貨流因子的金額或股數口徑，並決定是否申請／訂閱延伸歷史；在完整下載並比對交易日、公布時間與缺值後，再計算共同資料起點及正式回測起點。不能只因查詢頁顯示近三年，就假定已有足夠的三年暖機期和後續回測樣本。
