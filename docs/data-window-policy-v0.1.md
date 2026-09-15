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

## 下一步

實際對 TWSE / TAIFEX 資料來源進行 Data Availability Probe，產出一張表：

```text
Dataset | Source | Earliest | Latest | Missing | Automation | Notes
```

找到真正限制完整模型回測期間的資料集，再正式鎖定 Backtest Window。
