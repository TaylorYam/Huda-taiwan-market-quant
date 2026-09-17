# Dashboard View Model v0.1

`src/dashboard/view_model.py` is a presentation-only boundary. It converts a
`DailyScoreResult` into a `DashboardSnapshot` containing the score headline,
factor rows, categories, raw values, score states, reasons and evidence
counts. It never calls a data source and never calculates a factor.

The renderer should show `Market Score 尚不可用` whenever the aggregate result
is unavailable, then display each factor's `reason` so missing source data is
visible. A future Streamlit or Vercel handler can serialize
`DashboardSnapshot.as_dict()` without coupling the UI to SQLite, Supabase, or
the factor implementation.
