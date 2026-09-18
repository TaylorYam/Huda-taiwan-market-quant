# 0004: Streamlit Community Cloud 公開展示路線

- Status: Accepted（外部部署仍由維護者執行）
- Date: 2026-09-17
- Supersedes: ADR 0002 的 Dashboard hosting 選擇；資料持久化與排程維持不變

## Context

盤點基準為 origin/main `ab3abe2`：requirements.txt 已包含 Streamlit，
且 `streamlit_app.py`、`src/dashboard/app.py`、唯讀 Data API adapter 與 demo smoke 已合併。
外部 Community Cloud 部署與公開 URL 驗收仍未完成；不能把本機 smoke 當成已上線網站。

## Decision

最快免費展示路線採 Streamlit Community Cloud，入口約定 `streamlit_app.py`，
Python 3.12，從 repository 根目錄讀取 requirements.txt 與 .streamlit/config.toml。
Dashboard 入口已由獨立工作合併；無憑證 smoke 已通過，瀏覽器驗收與外部部署仍是 demo ready 的必要條件。
初次展示可採不需資料庫憑證的空資料狀態；若展示真實資料，憑證只留在 server-side，且須另行完成權限分離驗收。

Vercel 的 Python Functions 文件要求 ASGI／WSGI handler；Streamlit 是以
`streamlit run` 啟動的有 session 狀態伺服器，現有 repo 沒有該 adapter。
不能靠 Vercel build command 啟動 Streamlit 就視為可部署。
2026-09-17 官方文件已有 WebSockets beta，因此本決策不依賴「Vercel 永遠不支援
WebSocket」的舊假設；是否能可靠承載 Streamlit 仍需要額外適配與驗證，不是最快路線。

## Alternatives considered

- Vercel + 新前端／唯讀 API：可作未來重構，現在超出部署設定範圍。
- 容器或 VM：需另管程序、資源與平台免費限制，不如原生 Streamlit hosting 直接。

## Consequences

不建立帳號、付費資源或生產部署；本 PR 提供可審閱的部署設定及驗收程序。
Community Cloud 免費方案沒有本專案要求的可用性保證，休眠後需喚醒再重跑檢查。
HTTP health 成功只證明伺服器存活；AppTest 與人工 UI／資料日期驗收仍必要。
Supabase integration、RLS、migration 與正式排程仍有独立閘門，詳見
[部署 runbook](../demo-deployment.md)。

## References

- [Streamlit 免費部署平台](https://docs.streamlit.io/deploy)
- [Community Cloud 部署欄位](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/deploy)
- [Vercel Python handler](https://vercel.com/docs/functions/runtimes/python)
- [Vercel WebSockets 現況](https://vercel.com/kb/guide/do-vercel-serverless-functions-support-websocket-connections)
