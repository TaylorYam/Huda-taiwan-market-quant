# 公開展示部署與驗收

## 目前狀態與依賴

採用 [ADR 0004](adr/0004-streamlit-demo-hosting.md) 的 Streamlit Community Cloud 免費展示路線。
目前 `main` 已包含 `streamlit_app.py`、唯讀 Dashboard 與 Demo readiness smoke；
公開網站已完成初次展示驗收。本文件保留部署設定與後續驗收程序，
初次展示成功不代表最新正式排程、資料完整性或權限／備份驗收完成。

## 實際展示驗收（2026-09-18）

- 公開網址：[Huda｜台指大盤](https://huda-taiwan-market-quant-5f2taszopumzppuwyult9c.streamlit.app/)
- 部署來源：`TaylorYam/Huda-taiwan-market-quant` 的 `main`，驗收 commit `a31420a`
- 未登入瀏覽器可載入頁面標題、唯讀展示標示與來源資料品質表；Supabase 連線設定已由 Streamlit Secrets 提供，頁面未出現連線錯誤。
- 上述驗收僅代表 2026-09-18 當時的頁面狀態；當時 `market_scores` 尚無資料。
  後續已加入評分寫入、因子原始值與每日流程，不能沿用這筆舊紀錄判斷今天的資料狀態。

## 部署設定

| 欄位 | 設定 |
| --- | --- |
| Repository | TaylorYam/Huda-taiwan-market-quant |
| Branch | main |
| Main file path | streamlit_app.py |
| Python | 3.12（Community Cloud Advanced settings） |
| Dependencies | 根目錄 requirements.txt |
| Streamlit config | .streamlit/config.toml |
| Secrets | 實際展示需設定 `SUPABASE_URL` 與 `SUPABASE_SECRET_KEY`；無 secrets 僅可跑 readiness smoke |

由有權限的維護者登入 Community Cloud、授權此 GitHub repo、選 Create app，填上述欄位。
先核對頁面只呈現允許公開的資料，再選公開可見性與部署。記錄實際 URL、部署 commit SHA、
Python 及安裝套件版本；本 repo 的 requirements.txt 目前未鎖定全部版本，重建需重新驗收。
不要把 SQLite 放在 hosting 本機磁碟當持久資料庫。不要在啟動指令執行 migrations 或資料寫入。

## 環境變數／secret names

| 名稱 | 使用位置 | 公開展示要求 |
| --- | --- | --- |
| SUPABASE_URL | Dashboard 與既有 Actions Data API smoke／writer | 由伺服器端 secret 設定；不可放在 URL 或前端 |
| SUPABASE_SECRET_KEY | Dashboard 與既有 Actions server-side writer／smoke | 僅由伺服器端 secret 設定；可繞過 RLS，絕不公開 |
| MARKET_DB_URL | 舊 direct PostgreSQL 檢查／adapter | demo 不需要 |
| APP_ENV / APP_PORT | 舊 .env.example placeholder | 目前無讀取程式；不控制 Streamlit |

Dashboard 已有 server-side 唯讀讀取路徑，啟動時要求 `SUPABASE_URL` 與 `SUPABASE_SECRET_KEY`；
它也會拒絕非 HTTPS、含帳密、查詢參數或 fragment 的 URL。這把 key 可繞過 RLS，不應直接視為真正的 read-only credential。不要為了讓展示有資料就把 key 放到瀏覽器或前端環境變數；
Streamlit secrets 由管理介面配置，
root-level secrets 可映射環境變數；`.streamlit/secrets.toml` 受現有 `secrets.*` ignore 規則保護。
`.env` 不會由本專案自動載入。檢查紀錄只留 secret 名稱與通過狀態。

## 本機與 CI smoke

從 repo 根目錄、Python 3.12 環境執行：

```sh
python -m pip install -r requirements.txt
python scripts/check_demo.py
python -m streamlit run streamlit_app.py --server.port=8501
# 另一個終端執行：
python scripts/check_demo.py --url http://127.0.0.1:8501
```

第一項檢查使用 Streamlit AppTest 執行初始頁，入口缺失或拋例外即失敗。
AppTest 不驗證 WebSocket、所有互動或資料品質。第二項要求 `/_stcore/health` 回傳 200 與 `ok`，
拒絕登入頁／休眠頁等 HTML 假陽性，但不證明 Dashboard 正確。
GitHub Actions 的 **Demo readiness smoke** 可手動執行，無 secrets、無部署、無資料庫寫入。
目前入口缺失時這個工作應失敗，不能以跳過來宣告 ready。

公開 URL 部署後以同一 checker 的 `--url` 參數檢查。若休眠，先在瀏覽器喚醒再重跑。
用未登入／無痕視窗確認可公開訪問、頁面無 traceback、互動後仍正常；確認交易日期、
更新時間、來源／demo 標示、缺資料狀態與 8 因子顯示。不可把 demo 分數當成今日真實訊號。
記錄 URL、commit SHA、時間、health 結果、UI 截圖及資料日期才完成展示驗收。

## Supabase GitHub integration（PR #46 已合併）驗收

1. 確認 #46 已合併 main，root directory 為 repo 根目錄，GitHub integration 指向正確 repo、
   production branch 為 main。檢查 Supabase GitHub App 的 repo 授權、integration deployment 設定。
   不因本文件而開啟 Automatic branching 或建立 preview DB；先核對方案及費用。
2. 在 main 確認 `supabase/config.toml` 以及
   `supabase/migrations/20260917000100_observations.sql`、
   `supabase/migrations/20260917000200_market_scores.sql` 已存在，執行
   `python scripts/check_persistence_gate.py`。這只是 repo 結構／政策檢查，不是遠端成功證據。
3. 核對現有 DB 是否已透過 SQL Editor 建表；先比對 schema 與 migration history，
   留存備份。若歷史不一致，停止自動套用，由維護者審核 baseline／repair 計畫；
   不刪 production 表、不盲目重跑或直接把 migration 標為 applied。
4. 在 Supabase deployment logs／GitHub check 檢查 main 合併 SHA 是否被觸發、migration
   是否成功且無待套用／failed 狀態；如果 integration 未部署，先檢查授權、branch、root
   與自動部署設定，不假設 PR merge 即成功。保存不含 secrets 的 run URL／狀態證據。
5. 使用已授權的管理工具檢查 `public.observations`、`public.market_scores`、索引／constraints
   與 migration history 對應版本。確認 Data API 表可見性、RLS enabled、anon／authenticated
   無非預期寫入權限；writer secret 成功不能證明匿名讀取權限安全。
6. 在 GitHub main 手動執行既有 **Supabase API smoke test**，它使用
   `SUPABASE_URL`、`SUPABASE_SECRET_KEY`，確認兩表 Data API 可讀取。
   檢查程式不新增觀察值；綠燈不等於 migration history、RLS 或資料完整性已驗收。
7. 確認 migration 不應搬移 SQLite 既有資料；受控 export／import 是 #45 與 operations runbook
   的獨立步驟。資料筆數、修訂 lineage、最新日期、備份還原與 #18 維運閘門
   必須各自驗收；既有 daily writes 與網站可用不能替代這些證據。

## 回復與外部待辦

若部署失敗，維護者先停止分享 URL，查看已脫敏的 build／runtime logs，
回復 main 的部署變更需走新 PR；回復已知良好版本後重跑 AppTest、health 及 UI 驗收。
不得透過刪表回復 demo。必要時由維護者停止 Community Cloud app。

初次 Community Cloud 公開 URL 與頁面載入已於 2026-09-18 驗收；
雲端版本重建與互動、Supabase integration 的 migration history、RLS／權限、
備份還原、配額及最新 daily workflow 的正式排程結果仍須個別驗收。
不能由本機測試或早期展示紀錄替代。

參考：[Community Cloud secrets](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/secrets-management)、
[Supabase GitHub integration](https://supabase.com/docs/guides/deployment/branching/github-integration)、
[Migration history 與同步](https://supabase.com/docs/guides/deployment/database-migrations)。
