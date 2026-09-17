# Phase 1 儲存方案評估 v0.1

- 日期：2026-09-17
- 狀態：Phase 1 邊界由 [ADR 0001](adr/0001-phase-1-storage-boundary.md) 接受；免費 MVP 堆疊由 [ADR 0002](adr/0002-free-tier-mvp-stack.md) 選定，Data API 傳輸由 [ADR 0003](adr/0003-supabase-data-api-transport.md) 選定
- 範圍：Phase 1 官方市場資料收集、品質檢查、本機開發與免費 MVP 遷移準備；不選購或開通任何付費服務

## 評估依據

本專案以 Python 每日收集 TWSE／TAIFEX 官方資料，需保留原始與正規化觀察、發布版本、擷取時間、雜湊、品質狀態，以及可供重算的歷史因子結果。資料契約要求修訂採追加版本，明確指出原始下載檔、資料庫與執行期狀態不提交 Git；實體格式與保留期要另走 ADR。架構預期由 GitHub Actions 在收盤後執行，儀表板讀取最新結果，而每日資料不應依賴維護者的個人電腦持續開機。

以下容量判斷只是推估：目前每天是少量官方日資料系列，未經完整歷史回補後的實測資料量；Phase 0 仍有來源版次、歷史下界及覆蓋範圍待驗證事項。因而不以未測量的容量推估作為付費服務採購依據。

## 方案比較

| 方案 | Phase 1 適合度 | 優點 | 主要限制及風險 |
|---|---|---|---|
| 本機 SQLite | 高，建議作為可逆的開發預設 | 單一檔案、免服務管理，可交易式寫入與 SQL 查詢；適合低併發的單一收集器。可直接實作契約中的唯一鍵、追加修訂、來源雜湊與品質欄位。 | 本機檔案不會自動出現在 GitHub-hosted runner 或網站環境；必須排除 Git，並另做備份。SQLite 同時只有一個寫入者，適用目前預期的單一每日收集流程，不適合作為多個遠端服務共同寫入的中央資料庫。[SQLite 使用情境](https://www.sqlite.org/whentouse.html)、[SQLite 特性](https://www.sqlite.org/features.html) |
| 分區 CSV／Parquet | 中，適合作交換、稽核匯出及後續回測輸入 | 可將資料按 dataset／年份（或月份）分檔，便於抽查、複製與重算；CSV 易閱讀且工具普及，Parquet 是為有效儲存與取回而設計的欄式格式。[Apache Parquet 官方概述](https://parquet.apache.org/docs/overview/) | CSV 需額外約定型別、空值、欄位順序及 schema 版本；多檔追加修訂與跨檔查詢需應用層管理。Parquet 型別明確、適合掃描歷史資料，但不便人工逐列審查，通常也需額外 Python 套件。單靠檔案不會提供資料契約要求的鍵、版本和交易處理。 |
| 將資料提交到 Git repository | 低，不建議作市場資料儲存層 | 天然有 commit 歷史、審查與分支差異，符合表面上的 GitHub-first 流程。 | 與現行資料契約直接衝突：原始下載檔、資料庫、執行期狀態不提交 Git。每日追加資料會持續擴大 repository 歷史；公開 repo 的可見性和資料來源再散布條款也可能造成問題。Git 保留變更不等於資料授權，也不是適合執行中資料的備份策略。可將程式碼、schema、合成測試 fixture 納入 Git，但不要把正式市場資料集或 SQLite 檔當成來源資料庫。 |
| GitHub Actions workflow artifacts | 低，限短期流程驗證／交接 | 可將一次 workflow 的輸出留給後續工作或維護者下載；不用先建立另一套服務。 | GitHub-hosted runner 每個 job 都在新的 runner instance 執行，runner 上的 SQLite／檔案不會因此成為下一次排程的持久儲存。[Runner 選擇說明](https://docs.github.com/en/actions/how-tos/write-workflows/choose-where-workflows-run/choose-the-runner-for-a-job) Artifacts 預設保留 90 天，公開 repo 可設定 1–90 天、私有 repo 1–400 天，且組織／企業政策可再縮短；過期後自動刪除，並非永久資料庫。[Artifact 保留期限](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/enabling-features-for-your-repository/managing-github-actions-settings-for-a-repository) |
| 外部持久服務 | 高；MVP 選定 Supabase Free PostgreSQL + Data API | 托管 PostgreSQL 可集中保存觀察與版本並供收集器／網站讀取；runner 透過 Data API 連回同一個持久端點，不需要資料庫密碼。 | 免費層有 500 MB 資料庫配額，沒有託管自動備份／PITR，低活動專案可能暫停；需以 Actions secrets 管理 project URL 與 server-side secret key，並自行執行匯出與還原演練。 |

## 建議：Phase 1 開發與免費 MVP

先用**被 Git 忽略的本機 SQLite 檔**作為 Phase 1 單機開發資料庫，透過穩定的資料存取介面和契約欄位寫入；資料來源每次修訂追加新版本，不靜默覆蓋舊值。保留資料來源 URL、交易日、版次／盤別、`retrieved_at`、payload 雜湊、parser/schema 版本及品質狀態。這符合目前低併發、小規模每日資料收集的需求，且 SQLite 可整檔複製，容易在後續 ADR 決策後搬移。[SQLite 官方文件](https://www.sqlite.org/whentouse.html)

本機資料庫所在位置應明確列入 `.gitignore`，不要將資料庫或含正式觀察值的匯出檔提交。另提供可重現的 CSV 匯出作人工檢查與跨工具交換；CSV／Parquet 先視為匯出格式，不另立為 Phase 1 的第二套寫入真相。若歷史回測的掃描效能或檔案交換量成為實測瓶頸，再評估按 dataset／年份輸出 Parquet。程式以單一 repository／介面隔離資料存取，可把本機 SQLite 實作替換成外部資料庫，而不讓 TWSE／TAIFEX parser 或因子計算直接依賴 SQLite 細節。

這項建議先以**本機 SQLite + Supabase Free PostgreSQL Data API**支援開發與免費 MVP，並由 GitHub Actions 執行每日收集，Vercel Hobby 提供 Dashboard。它不代表已取得生產 SLA，也不代表免費服務具備災難復原能力。Artifacts 可在測試或短期故障排查時存放一次執行的報表／產物，但官方文件所列有限保留期和計畫儲存配額不適合作本專案多年回測資料的唯一來源。GitHub Actions artifact 配額依帳戶方案而異；實際適用額度、可計費使用量及費用須以 repo 所屬帳戶與當時方案為準，本文不作費用預測。[GitHub Actions billing](https://docs.github.com/en/billing/concepts/product-billing/github-actions)

## 排程正式上線前必須決定

在啟用每日無人值守排程之前，需依 [ADR 0002](adr/0002-free-tier-mvp-stack.md) 與 [ADR 0003](adr/0003-supabase-data-api-transport.md) 完成下列證據，並由 [Issue #18](https://github.com/TaylorYam/Huda-taiwan-market-quant/issues/18) 追蹤：

1. Actions 執行完成後，歷史觀察與版本透過 Supabase Data API 寫入 Supabase Free PostgreSQL，Dashboard 使用唯讀查詢路徑；必要時另用允許的匯出位置保存原始回應或資料庫 dump。
2. 保留期、備份頻率、還原方式、資料校正後重建流程，以及資料來源允許保存和再散布的範圍。
3. 免費方案配額／升級觸發器、區域、認證方式、GitHub Actions secrets 管理與最小權限存取。
4. 正式部署採用何種匯出／交換格式、schema migration 與回填規則，並以已驗證的 Phase 0 數據量測結果驗證容量。

就 GitHub-hosted runner 會在不同 job 使用新 instance 及 artifacts 會依政策到期這兩項條件而言，僅有 runner 本機 SQLite 或僅靠 workflow artifact 留存，均不足以滿足「不依賴個人電腦、每日自動更新、保留可重算歷史」的需求。Supabase Free PostgreSQL 是目前免費 MVP 的共享持久來源，Data API 是 Actions 的傳輸方式；在備份還原與配額監控完成前，不得把它描述成具備正式 SLA 的永久資料庫。

## 來源

- [SQLite：Appropriate Uses For SQLite](https://www.sqlite.org/whentouse.html)（SQLite 官方，查閱日期 2026-09-16）
- [SQLite Features](https://sqlite.org/features.html)（SQLite 官方，查閱日期 2026-09-16）
- [Apache Parquet Overview](https://parquet.apache.org/docs/overview/)（Apache 官方，查閱日期 2026-09-16）
- [GitHub-hosted runners：Choosing the runner for a job](https://docs.github.com/en/actions/how-tos/write-workflows/choose-where-workflows-run/choose-the-runner-for-a-job)（GitHub 官方，查閱日期 2026-09-16）
- [Managing GitHub Actions settings for a repository](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/enabling-features-for-your-repository/managing-github-actions-settings-for-a-repository)（GitHub 官方，查閱日期 2026-09-16）
- [GitHub Actions billing](https://docs.github.com/en/billing/concepts/product-billing/github-actions)（GitHub 官方，查閱日期 2026-09-16）
