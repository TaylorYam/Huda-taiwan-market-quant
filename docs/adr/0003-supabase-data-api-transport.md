# ADR 0003: 以 Supabase Data API 作為免費 MVP 傳輸層

- Status: Accepted
- Date: 2026-09-17
- Supersedes: MVP 的連線傳輸選擇；資料庫供應商仍為 ADR 0002 的 Supabase Free PostgreSQL

## Context

Supabase Free PostgreSQL 已選為免費 MVP 的持久化來源，但 GitHub Actions 以資料庫連線字串驗證時，密碼認證連線仍失敗。MVP 需要先有一條不依賴資料庫密碼、可由每日工作流程使用的寫入路徑。

## Decision

1. Supabase Free PostgreSQL 仍是資料的持久化來源。
2. GitHub Actions 改用 Supabase Data API／PostgREST，透過 `SUPABASE_URL` 與伺服器端 `SUPABASE_SECRET_KEY` 存取 `observations`。
3. `SUPABASE_SECRET_KEY` 只放在 GitHub Actions secrets 或伺服器端環境變數，不放進瀏覽器、repository 或對話內容。未來 Dashboard 若只需讀取，另用 publishable key 與 RLS 設計。
4. Schema 仍由 [`src/data/sql/001_observations.sql`](../../src/data/sql/001_observations.sql) 在 Supabase SQL Editor 建立一次；API smoke test 只確認資料表已可由 Data API 存取。
5. `PostgresObservationStore` 保留作為未來需要直接交易式 PostgreSQL 連線時的選項；免費 MVP 不再要求 `MARKET_DB_URL`。

## Consequences

- 不需要把 Supabase 資料庫密碼放進 GitHub Secret，也避開目前遇到的 direct PostgreSQL 認證問題。
- Data API 的 `observations` table 必須已建立且可被 API 暴露；若 Supabase 專案關閉該表的 Data API 存取，smoke test 會明確失敗。
- 目前 adapter 的 duplicate／revision 操作是多個 REST 請求，MVP 假設每日只有一個 writer；若日後有併發寫入，應改成 PostgreSQL RPC 或單一交易函式。
- secret key 可繞過 RLS，因此只能在受控的 server-side workflow 使用。

## Follow-up

1. 在 GitHub repository secrets 建立 `SUPABASE_URL` 與 `SUPABASE_SECRET_KEY`。
2. 在 Supabase SQL Editor 執行 observations schema。
3. 手動執行 [`supabase-api-smoke.yml`](../../.github/workflows/supabase-api-smoke.yml)。
4. 後續再加入每日收集器、備份／還原演練與 quota 監控。

## References

- [Supabase API keys](https://supabase.com/docs/guides/getting-started/api-keys)
- [Supabase Data API](https://supabase.com/docs/guides/api)
