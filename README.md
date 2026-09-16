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
- [x] 確認 Phase 1 使用 Git 忽略的 SQLite observation store；正式排程持久來源仍待 Accepted ADR
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

## Contribution flow

本專案沿用 GitHub-first 流程：

`Issue → branch → plan → implementation → validation → commit → pull request → review/CI → merge`
