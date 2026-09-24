# Architecture Overview

## Purpose and scope

本系統用來每日自動整合台灣現貨、期貨、選擇權與波動風險資料，產生一個可解釋的台指大盤操作方向。

核心輸出：

- Market Score（0–100）
- 強多／偏多／中性／偏空／強空
- 各因子分數
- 簡短的判斷理由

第一版不以預測明日精確漲跌幅為目標，而是判斷目前市場 Regime。

## System context

主要使用者：

- 主管：每天查看目前台指大盤操作方向
- 專案維護者：維護資料抓取、評分邏輯、回測與網站

主要外部資料來源：

- TWSE：TAIEX、外資現貨買賣超、市場成交金額
- TAIFEX：台指期行情、法人期貨部位、選擇權 OI Put/Call Ratio、Taiwan VIX

## Components and boundaries

目前免費 MVP 架構：

```text
TWSE / TAIFEX
     ↓
GitHub Actions daily workflow
     ↓
Data Collectors
     ↓
Raw / Normalized Data
     ↓
Factor Engine
     ↓
Scoring Engine
     ↓
Market Direction Result
     ↓
Supabase Free PostgreSQL / Data API
     ↓
Streamlit Community Cloud 唯讀 Dashboard
```

### Data Collectors

負責：

- 每日從官方免費來源抓取資料
- 處理 TWSE 與 TAIFEX 不同資料格式
- 做基本欄位驗證與日期一致性檢查

設計上應把 TWSE 與 TAIFEX client 分開，避免某一來源格式異動時影響全部資料流程。

### Factor Engine

負責把原始資料轉成 v0.1 的 8 個核心因子：

1. TAIEX vs MA20 / MA60
2. 20 日動能
3. 外資 5 日買賣超
4. 外資台指期淨多空部位
5. 外資期貨淨部位 5 日變化
6. 期現貨 Basis
7. OI Put/Call Ratio
8. Taiwan VIX

### Scoring Engine

負責：

- 將各因子統一轉為 0–100 分
- 套用 v0.1 權重
- 計算 Market Score
- 將 Market Score 映射成操作方向

詳細規格見 `docs/factor-model-v0.1.md`。

### Backtest Engine

第一層回測引擎已建立；真實歷史資料驗證仍待執行，用來回答：

- 高分是否對未來 5 / 10 / 20 日報酬有辨識力
- 權重是否需要調整
- PCR / Basis 等因子是否應保留
- 操作門檻是否合理

### Web Dashboard

已公開部署的唯讀 Streamlit MVP 入口為 `streamlit_app.py`。
Python 伺服器透過 Supabase Data API 讀取最新持久化 Market Score 與各來源
最近擷取紀錄；secret key 只存在伺服器環境。不重算分數、不寫入資料。
公開網址、啟動與資料缺漏限制見 README。

網站第一版重點是「先顯示結論，再顯示原因」。

至少顯示：

- 今日 Market Score
- 操作方向
- 按分類排列的因子分數
- 可取得的 8 個核心因子原始值
- 資料截至日期

Dashboard 只讀取已計算的結果；資料庫寫入由 GitHub Actions 負責。
新的 `factor_scores_json` 紀錄包含因子原始值與計算證據，舊紀錄可能缺少；
網站不因缺漏而臨時計算因子。Streamlit 執行期本機檔案不是持久資料庫。

## Data and state

目前保存兩層資料：

1. **Raw data**：保留每日官方來源資料的必要欄位
2. **Derived data**：Factor Score、Market Score 與操作方向

歷史資料需可供回測重算，避免只保存最新一天結果。

欄位、時間戳、單位、修訂及缺值的共同語義見 [`data-contract-v0.1.md`](data-contract-v0.1.md)。Phase 1 本機開發儲存方案的比較與建議見 [`data-storage-options-v0.1.md`](data-storage-options-v0.1.md)，實作邊界見 [`storage-interface-v0.1.md`](storage-interface-v0.1.md)。正式持久來源與傳輸方式分別由 [ADR 0002](adr/0002-free-tier-mvp-stack.md) 與 [ADR 0003](adr/0003-supabase-data-api-transport.md) 決定；備份、權限與配額驗收仍待完成。

生成的 runtime cache、credentials 與 populated `.env` 不應提交到 Git。

## Runtime and deployment

目前配置：

- Python 作為資料抓取與量化計算核心
- GitHub Actions 每日台股收盤後自動執行，透過 Supabase Data API 將結果寫入 Supabase Free PostgreSQL
- Streamlit Community Cloud 提供公開的唯讀 Web Dashboard
- 本機 SQLite 保留為開發與遷移測試資料庫

第一版目標是不需要使用者每天手動更新資料，也不要求本機電腦持續開機。

免費 MVP 的限制與升級條件記錄在 [ADR 0002](adr/0002-free-tier-mvp-stack.md)；Data API 傳輸方式見 [ADR 0003](adr/0003-supabase-data-api-transport.md)，展示託管選擇見 [ADR 0004](adr/0004-streamlit-demo-hosting.md)。每日排程已配置；最新評分修正後的正式排程驗收，以及手動匯出、還原演練、權限分離與配額監控仍是待辦，不能以網站可用或手動工作成功取代。

## Quality attributes and constraints

### Cost

- 第一版優先使用免費官方資料
- 無必要不導入付費 API

### Explainability

- 每一個 Market Score 都應能回溯到因子與原始資料
- 避免第一版直接採用不可解釋的機器學習模型

### Reliability

- 每日資料必須有日期與完整性檢查
- 若某一必要資料源抓取失敗，系統不應默默產生錯誤分數
- 網站需顯示最新成功更新時間

### Maintainability

- TWSE / TAIFEX 資料存取層與 Factor 邏輯分離
- 評分權重與門檻應集中設定，方便回測後調整

## Important decisions

目前重要決策：

- v0.1 採 8 因子可解釋規則模型
- 第一版優先使用 TWSE + TAIFEX 官方免費來源
- 免費 MVP 堆疊採 GitHub Actions + Supabase Free PostgreSQL Data API + Streamlit Community Cloud
- 權重與門檻皆視為待回測的初始假設
- 第一版不以機器學習預測明日漲跌為主要方向
- Phase 1 本機開發採用被 Git 忽略的 SQLite；正式持久化 MVP 堆疊見 [ADR 0002](adr/0002-free-tier-mvp-stack.md)，傳輸層見 [ADR 0003](adr/0003-supabase-data-api-transport.md)，展示託管見 [ADR 0004](adr/0004-streamlit-demo-hosting.md)

## Updating this document

當資料流、部署方式、核心模型邊界或重要限制發生變更時，應同步更新本文件。

尚未實作的元件及其順序、驗收條件與 GitHub Issue 草案見 [`roadmap-v0.1.md`](roadmap-v0.1.md)。
原先在 ADR 0002 規劃的 Vercel Dashboard 已由 [ADR 0004](adr/0004-streamlit-demo-hosting.md)
改為 Streamlit Community Cloud；已完成的展示驗收與剩餘外部操作閘門見
[部署 runbook](demo-deployment.md)。
