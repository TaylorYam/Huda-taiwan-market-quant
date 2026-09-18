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

## 回測資料品質與空窗口

共同起點的計算只能使用 `quality_status=available` 且具有可解析觀測日期與必要
數值欄位的資料列。`pending`、`source_empty`、`fetch_failed`、`parse_failed`、
`invalid` 等狀態不得以零值或中性值填補；它們應保留在資料品質稽核中，並在評分日
標為不可用。若某段期間沒有任何可用 TAIEX 收盤，回測報告應輸出零樣本與空的每日
列，單調性保持「無法判斷」，不應把缺資料解讀成模型表現。

正式回測起點仍須同時滿足共同原始起點、原始指標 warm-up、百分位歷史窗口與所有
必要因子的可用性。回測標籤的 forward window 則需要在報告終點之後額外讀取資料；
這段延伸資料用來計算未來 5／10／20 個實際交易日，不會擴大報告所宣告的訊號期間。

---

## 目前現況（2026-09-18 更新）：回補端點與程式已具備，正式共同起點待實際回補

Taiwan VIX 與法人期貨 OI（外資台指期淨部位、淨部位 5 日變化兩個因子的資料源）已有免費的日期查詢端點：

- 法人期貨 OI：`https://www.taifex.com.tw/cht/3/futContractsDateDown`，使用
  `queryStartDate`／`queryEndDate`／`commodityId` 查詢。
- Taiwan VIX：`https://www.taifex.com.tw/indes/index.aspx/GetStockDayPrices`，使用
  `syid`／`flag`／`startDate`／`endDate` 查詢。

兩者都是查詢當下往前推約 3 年的 rolling window，不是固定的歷史起點。2026-09
可取得的最早日期約為 2023-09；2010 仍在窗口外，因此在不付費且不改變必要因子
設計的前提下不可達。窗口會持續往前捲動，延後回補會失去較早資料。

一次性回補邏輯已實作於 `fetch_vix_range`／`fetch_institutional_futures_range`，
對應入口為 `scripts/backfill_taifex_*_range.py`。這些入口會驗證日期範圍、解析欄位、
保留品質狀態並按觀測日寫入；**程式已具備不等於正式 Supabase 已完成回補**。在實際
回補並通過品質稽核前，正式資料庫的 `earliest_date` 仍以已保存的可用觀測為準。
完成回補後，這兩個來源才可把完整模型的共同原始起點推回約 2023 年。

外資現貨因子已通過 BFI82U／FMTQIK 口徑查證，`FOREIGN_CASH_VERIFIED_START` 設為
2010-01-01；計算仍要求兩個來源都有完整 5 個交易日的可用窗口，不以 T86 或零值
替代。8 個因子與 point-in-time 歷史百分位已有合成資料端對端測試，但尚未用足量的
正式歷史資料產出模型有效性的結論。

---

## Probe 結果與下一步

第一輪官方資料盤點與 Phase 0 補查分別見 [Data Availability Probe v0.1](data-availability-probe-v0.1.md) 與 [Phase 0 Source Research](phase0-source-research-v0.1.md)。目前已具備 TAIEX、PCR、TX、VIX、法人期貨 OI、BFI82U 與 FMTQIK 的資料入口及品質狀態；來源的可用日期、缺日與回補完整性仍須以保存後的品質報告確認。

下一步和驗收條件已排入 [`roadmap-v0.1.md`](roadmap-v0.1.md) Phase 1–3：先執行 VIX／法人期貨 OI 一次性回補並比對交易日、發布時間與缺值，再計算共同資料起點及正式回測起點；資料量足夠後才執行 `scripts/run_backtest_layer1.py` 產生真實 5／10／20 日報告。不能只因查詢頁顯示近三年，就假定已有足夠的暖機期和後續回測樣本。
