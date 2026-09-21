# Issue #18 營運 Gate Runbook v0.1

- Status: operational checklist; unattended production writes remain gated
- Scope: Supabase Free PostgreSQL/Data API、GitHub Actions、資料備份與還原、存取權限、配額及來源條款
- Tracking: [Issue #18](https://github.com/TaylorYam/Huda-taiwan-market-quant/issues/18)
- Last reviewed: 2026-09-17（Asia/Taipei）

本文件把已完成的 repository-level 驗證和仍需由授權操作者在 Supabase、GitHub 及核准的備份位置完成的工作分開。完成全部手動 gate 前，不得啟用無人值守的每日正式寫入。任何匯出檔、連線值、API key、token 或 populated `.env` 都不得放進 repository、issue、artifact 或本文件。

## Gate 狀態

### 已由既有 run 驗證

Issue #18 可引用的既有證據為 [run 35191715728](https://github.com/TaylorYam/Huda-taiwan-market-quant/actions/runs/35191715728) 與 [run 35192169763](https://github.com/TaylorYam/Huda-taiwan-market-quant/actions/runs/35192169763)。兩次 run 的證據範圍是 repository 內、無外部憑證的 persistence gate：

- checked-in PostgreSQL migration [`20260917000100_observations.sql`](../supabase/migrations/20260917000100_observations.sql) 具備 observation identity index、`source_payload_hash`、`retrieval_count`、`values_json` 及 `supersedes_id` 等持久化契約欄位；derived score migration 為 [`20260917000200_market_scores.sql`](../supabase/migrations/20260917000200_market_scores.sql)。
- 臨時 SQLite store 能插入原始 observation；同一 payload 重跑會判定為 duplicate、保留同一 row 並增加 `retrieval_count`。
- 修訂 payload 會新增 row、保存兩個 payload hash，並用 `supersedes_id` 連回前一版本；原始 observation 的值不會被改寫。
- 這些 run 沒有證明遠端 SQL migration、Supabase Data API 權限、資料庫 backup／restore、secret rotation、配額餘裕或來源條款。run 成功不能取代下列手動 gate。

### 本次 Supabase 操作（2026-09-17，Asia/Taipei）

- 目標 project：`TaylorYam's Project`（ref `vfjljdhpjhaebcgdzsvz`）。已在 SQL Editor 執行 [`001_observations.sql`](../src/data/sql/001_observations.sql) 與 [`002_market_scores.sql`](../src/data/sql/002_market_scores.sql)；兩份 migration 均回傳成功。
- 唯讀驗證確認 `public.observations` 有 39 筆、`public.market_scores` 有 0 筆；兩表的 checked-in 欄位、索引與 RLS 狀態均存在。
- [Supabase API smoke run 35211970093](https://github.com/TaylorYam/Huda-taiwan-market-quant/actions/runs/35211970093) 成功，`SUPABASE_URL` 與 `SUPABASE_SECRET_KEY` 均由 GitHub Secrets 提供且未出現在 log。Supabase project 目前沒有 `supabase_migrations.schema_migrations` metadata table；後續若要由 CLI 管理 migration history，需另行建立受控的 migration 流程。

### Quota snapshot（2026-09-17，Asia/Taipei）

- Supabase 使用量頁顯示 Free Plan、目前 billing cycle 為 2026-09-17 至 2026-10-17；database size 為 24.96 MB／500 MB（5%），egress 為 0／5 GB，cached egress 為 0／5 GB，storage 為 0／1 GB，MAU 為 0／50,000。Spend cap 已啟用。
- SQL 盤點顯示 `public.observations` 為 104 kB（39 筆）、`public.market_scores` 為 32 kB（0 筆）；兩表合計約 136 kB。專案資料庫總量仍以 Supabase usage 頁的 24.96 MB 為準。
- GitHub Actions billing API 需要目前 token 未提供的 `user` scope，因此本次只記錄 workflow run history，未宣稱 Actions quota gate 已完成；取得核准 billing scope 後再補記官方 usage snapshot。

### Access check snapshot（2026-09-17，Asia/Taipei）

- GitHub repository secret names 目前為 `SUPABASE_URL`、`SUPABASE_SECRET_KEY` 與 `MARKET_DB_URL`；所有 `.github/workflows/` 的正式 writer 都只引用前兩者，`MARKET_DB_URL` 沒有 workflow 引用，但 repository 仍保留手動 PostgreSQL 檢查腳本的支援，是否撤銷交由 owner 決定。
- Supabase SQL 檢查確認 `public.observations` 與 `public.market_scores` 都已啟用 RLS，且目前沒有 public policy。server-side `SUPABASE_SECRET_KEY` 的 API smoke 已通過；Dashboard 的獨立 publishable／read-only credential 尚未建立，因此 access separation gate 不宣稱完成。

### Source terms snapshot（2026-09-17，Asia/Taipei）

- [TWSE 網路資訊商店使用條款](https://eshop.twse.com.tw/zh/home/terms) 禁止未經同意以自動化裝置、指令碼、爬蟲或擷取程式下載資料；內容的使用、重製、散布及轉載另要求事前書面同意，引用時須標示來源並保持完整性。
- [TAIFEX 網站使用條款](https://www.taifex.com.tw/cht/edu/userTerms) 將網站內容與資料列為受智慧財產權保護，重製、改作、散布或公開發表原則上需事前書面同意；政府資料開放平台授權的資料另有例外。直接使用交易資訊仍須對照[交易資訊使用管理辦法及契約](https://www.taifex.com.tw/cht/6/iTRule)的適用範圍與授權條件。
- **書面確認（2026-09-17）**：owner 已親自去信 TWSE 與 TAIFEX，敘明本專案的使用方式與目的；雙方回覆確認可正常使用，條件為 (1) 僅限非商業用途、(2) 須標示資料來源。回覆內容由 owner 自行留存，不進 repository。
- 結論：來源矩陣狀態更新為 `allowed with restrictions`（僅限非商業用途＋須標示來源）。TWSE、TAIFEX 的自動下載、內部 Dashboard 與再散布邊界視為已取得授權，**前提是專案維持非商業性質，且對外呈現（README、Dashboard、任何公開頁面）確實標示 TWSE／TAIFEX 資料來源**。目前 repository 尚未加入符合此條件的來源標示，列為待辦（見下表）。若未來用途擴大至商業性質，須重新向兩所確認。

### 仍需手動完成

| Gate | 完成條件 | 證據應保存在哪裡 |
|---|---|---|
| Remote schema and API | 在目標 Supabase project 執行 migration，確認 `observations` 可由 Data API 讀取，並成功執行 smoke workflow | 已於 2026-09-17 完成；project ref `vfjljdhpjhaebcgdzsvz`、migration `001`／`002`、[smoke run 35211970093](https://github.com/TaylorYam/Huda-taiwan-market-quant/actions/runs/35211970093) |
| Backup | 產生完整 `pg_dump`，放到核准且受限的備份位置，記錄備份日期、範圍、保存期限及 owner | Issue #18 的 metadata；dump 本身不進 GitHub |
| Restore drill | 還原到隔離 project／database，通過 row count、logical identity、payload hash、`supersedes_id` chain 比對，記錄 RTO 與最新可還原 observation date | Issue #18 的 drill record；隔離環境完成後刪除臨時資料 |
| Access separation and rotation | Actions writer、Dashboard reader、操作者權限各自符合最小權限；新 key 已驗證後才撤銷舊 key | 只記錄 key 類型、輪替日期、驗證 run URL；不記錄 key 值 |
| Quota and upgrade trigger | 記錄 Supabase database usage、Actions usage、資料增長估計及升級門檻 | Issue #18 的日期化 quota snapshot |
| Source terms | 已於 2026-09-17 取得 TWSE、TAIFEX 書面確認（`allowed with restrictions`：僅限非商業用途、須標示來源）；剩餘工作為在 README／Dashboard 補上符合條件的來源標示 | Issue #18 的來源、查核日期、結論及限制；email 回覆內容由 owner 自行留存，不進 repository |

## A. 首次建立或驗證遠端環境

1. 由具備 Supabase project 管理權限的操作者登入 Supabase Dashboard，選定正式 project。確認 project 名稱、region 與 owner，將 metadata 記在 Issue #18；不要把任何 key 或連線字串貼入 issue。
2. 開啟 **SQL Editor**，貼上 repository 的 [`supabase/migrations/20260917000100_observations.sql`](../supabase/migrations/20260917000100_observations.sql) 與 [`supabase/migrations/20260917000200_market_scores.sql`](../supabase/migrations/20260917000200_market_scores.sql) 內容並執行。查詢結果只需確認 migration 成功；不要把含資料或 credentials 的畫面截圖上傳。
3. 在 project 的 **Data API／API Settings** 檢查 `observations` 已暴露給 API。若 project 使用 table exposure 或 schema allowlist，加入必要設定後保存。
4. 在 GitHub repository 開啟 **Settings → Secrets and variables → Actions**。建立或更新 `SUPABASE_URL` 與 `SUPABASE_SECRET_KEY` 這兩個 secret name；只在 secret 欄位輸入值，不將值寫入 workflow、issue 或 log。
5. 開啟 **Actions → Supabase API smoke test → Run workflow**，使用預設 branch 手動執行。確認 `Verify API secrets are available` 與 `Verify observations endpoint` 都成功；只記錄 run URL、日期與結果。
6. 若 smoke test 失敗，先停止正式排程，檢查 schema、table exposure、secret name 及 key 的 active 狀態。不要用把 key 印到 log 的方式除錯。

這個 smoke workflow 只確認 Data API endpoint 可存取，不會完成 backup／restore，也不會證明 Dashboard 已使用唯讀憑證。後兩項仍由下列 gate 處理。

## B. 手動 backup 與 restore drill

Supabase Free 不提供可依賴的 managed automatic backup 或 PITR，因此至少在啟用正式每日寫入前完成一次 drill，之後依 owner 設定的週期重做。建議每週至少一次，或在 schema、來源契約及 writer 權限變更後立即重做。

### Export

1. 在核准的受限工作環境安裝與目標 PostgreSQL 相容的 `pg_dump`。確認 dump 會寫入 GitHub 以外的受限備份位置；不要把 dump 放在 repository、workflow artifact 或公開 cloud bucket。
2. 從 Supabase Dashboard 的 **Connect**／資料庫連線資訊取得本次操作所需的連線參數，僅暫時放入本機受保護的 credential prompt 或已核准的 secret store。不要將連線 URL、密碼或 token 寫入 shell history、文件或截圖。
3. 以 custom-format dump 匯出正式 schema 與資料，至少包含 `observations` 及正式使用的 derived-result tables。排除不屬於本專案的 project data，並保留 dump 的 SHA-256、建立時間、資料庫 project metadata 與最新 observation date。
4. 將 dump 移到受限備份位置，設定 owner、保存期限及刪除方式。Issue #18 只記錄檔案識別資訊、大小、hash、保存期限及位置類型，不記錄可存取備份的 credentials。

### Isolated restore

1. 建立與正式環境隔離的 temporary project／database，使用不同的 project identifier。不得把 restore 直接指向 production。
2. 以受限操作者身份執行 `pg_restore`（或 provider 指定的等效 restore），先載入 schema，再載入資料。restore 使用的權限只需支援該次 drill，完成後撤銷或刪除。
3. 在隔離環境以 SQL 或受控檢查比對：總 row count、每個 dataset 的日期範圍、`dataset_id`／`observation_date`／`source_record_key`／`publication_label` logical identity、`source_payload_hash`、`retrieval_count`，以及每條 `supersedes_id` revision chain。
4. 執行現有的 smoke workflow，確認隔離 endpoint 可讀取 `observations`。不要在 smoke workflow 中寫入真實市場資料，除非 drill record 明確標示測試資料與清除方式。
5. 記錄 export 開始／結束時間、restore 開始／結束時間、RTO、最新可還原 observation date、比對結果與任何遺失欄位。刪除 temporary project 及本機暫存憑證後，再把結果貼到 Issue #18。

若任一 hash、row count 或 revision chain 不一致，restore gate 為失敗；停止正式排程，保留隔離環境供調查，並建立修正後的 dump 與第二次 drill。不要以「資料大致存在」視為通過。

## C. Access separation 與 secret rotation

目前 Data API writer 透過 server-side `SUPABASE_SECRET_KEY`，此 key 只能供 GitHub Actions 或受控 server-side process 使用。不得放進瀏覽器、前端 bundle、Dashboard client、repository 或聊天內容。

### 初始 access check

1. 在 Supabase Dashboard 檢查 Data API 的 table exposure 及任何 RLS／policy 設定。確認 GitHub Actions 的 writer 路徑可完成既定寫入，而 Dashboard 查詢路徑只持有讀取所需的 publishable／read-only credential。
2. 在 GitHub **Settings → Secrets and variables → Actions** 確認只存在必要 secret names，且 production workflow 沒有把 secret 值以 `echo`、debug log、artifact 或 output 傳出。
3. 手動執行 smoke workflow 驗證 writer-side API credential 的 endpoint access。Dashboard 的 read-only path 需用獨立 credential 做讀取驗證；若尚未建立該 path，access gate 保持未完成，不得宣稱已完成權限分離。

### Rotation procedure

1. 在 Supabase 對應的 API key／credential 管理頁建立新 credential，或依 provider 支援的流程產生新 server-side key。先把新值存入核准的 secret store；不要刪除舊 key。
2. 在 GitHub **Settings → Secrets and variables → Actions** 更新既有 secret name 的值。不要改 workflow 來印出或回傳新值。
3. 從 **Actions → Supabase API smoke test → Run workflow** 執行 smoke test，確認新 credential 成功。若正式 writer 有專用 dry-run 或隔離 workflow，先完成該驗證再繼續。
4. 確認沒有其他受控 server-side consumer 仍依賴舊 credential 後，在 Supabase 撤銷舊 key。輪替順序是「建立新值 → 更新 consumer → 驗證 → 撤銷舊值」。
5. 記錄 key 類型、建立／撤銷日期、驗證 run URL、操作者與失敗回復步驟。絕不記錄 key 值。

若 key 遺失或疑似外洩，立即撤銷該 key、產生新 key、更新 Actions secret、重跑 smoke test，並在 Issue #18 記錄事件時間與處置結果，不要在 issue 中重述外洩內容。

## D. Quota、成本與升級門檻

### 每次 release gate 的 UI 檢查

1. 在 Supabase Dashboard 開啟 project 的 **Settings → Usage／Billing**（實際標籤依 Dashboard 版本為準），記錄 database size、當月使用量、project pause 狀態及查核日期。
2. 在 GitHub repository 開啟 **Settings → Billing and plans → Actions**，記錄可用的 Actions minutes／storage quota 與近期 workflow 使用情況。免費方案的實際數值以帳號頁面顯示為準，不從文件中的假設推算。
3. 以最近至少 14 天的 observation row count、payload size 與每日增量估計耗用。分開估算 normalized observations、derived results 及任何 raw payload backup；不要把壓縮後 dump 大小當成 database quota。
4. 在 Issue #18 寫入 snapshot date、目前值、估算方法、owner 與下次檢查日期。不要上傳 raw payload、dump 或含 credentials 的 billing export。

### 必須暫停並評估升級

- Supabase database usage 接近 500 MB，或按目前增長率會在下一個規劃週期超過免費額度。
- 需要 provider-managed automatic backup、PITR、較長的 retention 或可靠的 failover。
- project 反覆因低活動被 pause，或 Actions quota／執行時間已影響每日資料收集。
- 需要更可靠的排程、重試、併發寫入或更細的 service role／RLS boundary。
- 來源條款要求更嚴格的儲存位置、存取控管、刪除期限或禁止目前的備份複本。

達到任一條件時，先停用無人值守正式 workflow，於新的 ADR 或 Issue #18 記錄 provider、成本上限、migration、backup／restore 方案及 owner，再恢復排程。

## E. Source terms 與資料邊界

1. 針對 [TWSE 網路資訊商店使用條款](https://eshop.twse.com.tw/zh/home/terms)、[TAIFEX 網站使用條款](https://www.taifex.com.tw/cht/edu/userTerms)，逐一記錄查核日期、適用的公開 endpoint／產品、允許的保存期限、內部 Dashboard 使用、備份複本、再散布限制及需要的 attribution。
2. 將免費公開資料與未購買的付費 E-Shop／E-Data 商品分開。不要因文件列出付費商品就假設已取得授權；未申購、未下載的商品不列入可用來源。
3. 只保存完成契約核對所需的欄位與 metadata：source URL、source date、retrieved time、units、contract／session identity、payload hash、parser version、quality state。raw payload 若需保存，先確認條款允許，再指定受限位置與刪除期限。
4. 在 Issue #18 的來源矩陣寫下結論：`allowed`、`allowed with restrictions` 或 `unresolved`。任何 `unresolved` 都會使 source-term gate 保持未完成，且不得把資料公開到 Dashboard 或備份到未核准位置。

現有來源研究已指出，TWSE E-Shop 資料有自動化與使用條款限制，TAIFEX 歷史資料商品也有各自的申購與使用邊界；這些文件中的公開資料探測結果不等於取得付費資料授權。參考 [`data-availability-probe-v0.1.md`](data-availability-probe-v0.1.md) 與 [`phase0-taifex-history-v0.1.md`](phase0-taifex-history-v0.1.md)。

目前新增的 [`taifex-institutional-daily-ingestion.yml`](../.github/workflows/taifex-institutional-daily-ingestion.yml) 只有 `workflow_dispatch`，預設為唯讀探測；只有操作者明確勾選寫入並通過 secret 檢查時才會寫入 Supabase。完整的 [`daily-market-automation.yml`](../.github/workflows/daily-market-automation.yml) 已加入平日 16:30 與 22:00 Asia/Taipei 排程，會在 Runner 上產生當日日期與 cutoff；22:00 是延遲／修訂資料的確認重跑，institutional collector 仍由完整流程的日期閘門保護。這不代表 Issue #18 的備份、還原、權限、輪替、配額與來源條款 gates 已完成。

## Release decision record

在 Issue #18 逐項填寫下表。只有所有列為「必須完成」的 gate 都有日期化證據，才可把每日 workflow 改為無人值守。

| 項目 | 狀態 | 操作者／日期 | 證據 |
|---|---|---|---|
| Local migration、idempotency、revision lineage | 已驗證 | run 35191715728、35192169763 | workflow run URL |
| Remote SQL migration and Data API exposure | 已驗證 | 2026-09-17（Asia/Taipei） | [Supabase API smoke run 35211970093](https://github.com/TaylorYam/Huda-taiwan-market-quant/actions/runs/35211970093)；project ref `vfjljdhpjhaebcgdzsvz` |
| Backup export and retention | 待手動 |  | dump metadata（不含 dump／secret） |
| Isolated restore and reconciliation | 待手動 |  | RTO、latest recoverable date、比對結果 |
| Actions writer / Dashboard reader separation | 部分驗證 | 2026-09-17（Asia/Taipei） | Secrets 名稱與 RLS 已盤點；server-side smoke 通過，Dashboard 獨立唯讀 credential 尚待建立 |
| Secret rotation | 待手動 |  | rotation date、old key revoked、smoke run |
| Supabase / Actions quota snapshot | 部分驗證 | 2026-09-17（Asia/Taipei） | Supabase usage：24.96 MB／500 MB（5%）；Actions billing 尚待核准 scope 後補記 |
| TWSE / TAIFEX source terms | 已驗證（有條件） | 2026-09-17（Asia/Taipei） | [TWSE 條款](https://eshop.twse.com.tw/zh/home/terms)、[TAIFEX 條款](https://www.taifex.com.tw/cht/edu/userTerms)；owner 已取得雙方書面確認（僅限非商業用途＋須標示來源）；來源標示尚未加入 README／Dashboard，列入待辦 |

### 不通過時的處置

任何 gate 失敗或證據缺失時，維持正式每日 workflow 停用，保留已完成的 local checks，並在 Issue #18 記錄失敗步驟、影響範圍、owner 與下一次重試條件。不要以 runner-local SQLite、短期 Actions artifact 或單次 API 讀取代替持久化、備份、還原或條款證據。
