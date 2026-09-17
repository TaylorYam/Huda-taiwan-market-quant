# Huda Taiwan Market Quant

台指大盤量化方向判斷系統。

## 專案目標

本專案的核心不是堆疊大量指標，而是每天自動回答一個問題：

> **目前台指大盤的操作方向是什麼？**

系統預計每日自動更新資料、計算量化分數，最後輸出：

- 強多
- 偏多
- 中性／觀望
- 偏空
- 強空

第一版網站應讓主管快速看到：

- 今日台指方向
- Market Score（0–100）
- 各類因子分數
- 簡短的判斷理由

範例：

```text
台指大盤：偏多
Market Score：72 / 100

技術趨勢：偏多
現貨籌碼：偏多
期貨籌碼：偏多
選擇權：中性
市場風險：正常

操作方向：維持偏多操作。
```

## 設計原則

1. **自動化優先**：每日自動抓資料，不依賴人工下載 Excel 或手動輸入。
2. **免費資料優先**：第一版盡量只使用官方免費資料，不購買付費 API。
3. **官方來源優先**：主要來源以 TWSE（臺灣證券交易所）與 TAIFEX（臺灣期貨交易所）為主。
4. **模型可解釋**：主管能看懂為什麼今天是偏多或偏空。
5. **先做規則模型，再回測**：v0.1 的權重與門檻是初始假設，之後必須用歷史資料驗證並調整。
6. **不追求預測明日漲跌**：模型主要判斷目前市場 Regime／操作方向，而不是預測明天精確漲跌幅。

## 自動化流程

```text
官方免費資料
    ↓
Python 每日抓取
    ↓
資料清理與儲存
    ↓
計算 Factor
    ↓
計算 0–100 分
    ↓
產生台指操作方向
    ↓
網站自動更新
```

預計之後使用 GitHub Actions 在台股收盤後自動執行。

## 免費 MVP 部署堆疊

第一版先採用零固定費用的部署方式：

```text
TWSE / TAIFEX 官方日資料
        ↓
GitHub Actions：每日收集與寫入
        ↓
Supabase Free PostgreSQL + Data API：持久化觀察與分數
        ↓
Vercel Hobby：Dashboard 與唯讀 API
```

本機開發仍使用被 Git 忽略的 SQLite。GitHub Actions 透過 Supabase Data API 寫入，不需要資料庫密碼；`SUPABASE_URL` 與 `SUPABASE_SECRET_KEY` 只放在 GitHub Secrets。Supabase Free 沒有託管自動備份或 PITR，Vercel Hobby 的每日 Cron 也不是精準排程器；完整限制、備份要求與升級條件見 [`docs/adr/0002-free-tier-mvp-stack.md`](docs/adr/0002-free-tier-mvp-stack.md) 與 [`docs/adr/0003-supabase-data-api-transport.md`](docs/adr/0003-supabase-data-api-transport.md)。

若啟用 Supabase GitHub integration，標準 migration 位置為 [`supabase/migrations/`](supabase/migrations/)，專案設定在 [`supabase/config.toml`](supabase/config.toml)，working directory 使用 repository root（`.`）。推送或合併到 production branch 後，integration 可依 migration 檔部署 schema；目前的 Data API writer 仍由 GitHub Actions 負責。

## v0.1 核心模型

第一版先使用 8 個核心因子：

| 類別 | 指標 | 權重 |
|---|---|---:|
| 技術 | TAIEX vs MA20 / MA60 | 20% |
| 技術 | 20 日動能 | 10% |
| 現貨籌碼 | 外資 5 日買賣超 | 15% |
| 期貨 | 外資台指期淨多空部位 | 15% |
| 期貨 | 外資期貨淨部位 5 日變化 | 10% |
| 期貨 | 期現貨價差 Basis | 5% |
| 選擇權 | OI Put/Call Ratio | 10% |
| 風險 | Taiwan VIX | 15% |
|  | **合計** | **100%** |

詳細定義與初始評分規則請見 [`docs/factor-spec.md`](docs/factor-spec.md) 及其連結的版本化模型文件。

各文件中尚未實作的資料、評分、回測與 Dashboard 方向，已整併為 [`docs/roadmap-v0.1.md`](docs/roadmap-v0.1.md)，包含依賴順序、驗收條件與 GitHub Issue 草案。

## 目前階段

- [x] 定義主管需求與系統目標
- [x] 確認第一版以免費官方資料為主
- [x] 定義 Market Direction Model v0.1
- [x] 定義 8 個核心因子與初始權重
- [x] 定義 Factor Score 0–100 的基本方式
- [x] 完成第一輪資料可用性探測（缺值率與部分歷史下界仍待完整下載驗證）
- [x] 補查免費 BFI82U 現貨金額及 FMTQIK 成交金額資料來源；建立資料契約草案
- [ ] 核對現貨金額分子／分母的版次、交易範圍與歷史缺口（Roadmap Phase 0）
- [x] 確認 Phase 1 使用 Git 忽略的 SQLite observation store；免費 MVP 持久來源已由 ADR 0002 選定
- [x] 選定免費 MVP 堆疊：GitHub Actions + Supabase Free PostgreSQL Data API + Vercel Hobby
- [ ] 建立官方資料收集與品質檢查（Phase 1）
- [ ] 實作 8 個因子與 Market Score（Phase 2）
- [ ] 驗證分數辨識力；通過後才做策略層回測（Phase 3）
- [ ] 建立 Dashboard、CI 與每日資料流程（Phase 4）

## 專案結構

```text
.
├── README.md
├── AGENTS.md
├── .gitignore
├── requirements.txt
├── docs/
│   ├── factor-spec.md
│   ├── factor-model-v0.1.md
│   ├── data-window-policy-v0.1.md
│   ├── data-availability-probe-v0.1.md
│   ├── phase0-source-research-v0.1.md
│   ├── phase0-cash-market-scope-v0.1.md
│   ├── phase0-cash-factor-source-verification-v0.1.md
│   ├── phase0-taifex-history-v0.1.md
│   ├── data-contract-v0.1.md
│   ├── data-storage-options-v0.1.md
│   ├── storage-interface-v0.1.md
│   ├── taiex-collector-v0.1.md
│   ├── backtest-spec-v0.1.md
│   ├── roadmap-v0.1.md
│   └── adr/
├── src/
│   ├── data/
│   ├── factors/
│   ├── scoring/
│   └── dashboard/
├── tests/
└── .github/
    ├── ISSUE_TEMPLATE/
    └── pull_request_template.md
```

## Streamlit 唯讀 Dashboard MVP

此展示入口供主管快速查看最新已儲存結果及維護者檢查來源品質；
使用 Streamlit Python 伺服器呼叫 Supabase Data API，不在頁面重算分數。
這是可本機啟動的展示方案，正式網站部署方向仍見 ADR 0002。

在 repository 根目錄執行（Python 3.12+）：

```powershell
python -m pip install -r requirements.txt
# 在執行 Streamlit 的伺服器環境安全注入以下兩個變數：
$env:SUPABASE_URL = "https://your-project-ref.supabase.co"
$env:SUPABASE_SECRET_KEY = "<server-only-secret>"
python -m streamlit run streamlit_app.py
```

瀏覽器開啟 `http://localhost:8501`。程式僅讀取環境變數，不自動載入 `.env`。
請用部署平台的伺服器 secrets 設定實際值；不要把密鑰放入程式、URL、
畫面輸入欄或前端環境變數。`SUPABASE_SECRET_KEY` 可繞過 RLS，必須留在
受控的 Python 伺服器；本頁只發出 GET，但此密鑰本身不是唯讀權限。
畫面不顯示原始 API 回應錯誤、憑證或 session。

- 最新結果依 `target_date DESC, created_at DESC, id DESC` 選一筆，跨模型版本。
  最新結果若 unavailable，不退回較舊的 available 分數。
- 顯示分類／因子列、target、as-of、模型、分數寫入時間與 unavailable 原因。
  現有持久化格式沒有因子原始值／分類總分，因此不自行推算。
- 來源區列出五個已實作來源各自最近擷取的一筆紀錄、品質狀態與擷取時間。
  這是來源更新概況，並非分數的 as-of 證據或全部資料品質摘要；
  未持久化的失敗擷取無法由此得知。外資現貨來源契約仍未完成。
- 頁面載入或按「重新整理」時讀取最新資料，無跨使用者的憑證快取。
  `available` 不是新鮮度保證，請核對 target、as-of 與各來源日期。

無憑證時會顯示設定錯誤；資料表存在但沒有分數時顯示 empty，來源區仍可讀取。
若 API、憑證、網路或資料表不可用，顯示不含敏感資訊的錯誤。
遠端須已由維護者完成既有 observations 與 market_scores schema 設定，
且有 Data API 存取權。本頁不建立表、不執行 migration、不觸發每日評分。
缺少生產資料／憑證時不會生成示範分數。

最小驗證（測試資料均為本機假資料，不寫入 Supabase）：

```powershell
python -m pip install -r requirements-dev.txt
python -m pytest -q
python -m ruff check src tests streamlit_app.py
python -m ruff format --check src tests streamlit_app.py
```

## Contribution flow

本專案沿用 GitHub-first 流程：

`Issue → branch → plan → implementation → validation → commit → pull request → review/CI → merge`
