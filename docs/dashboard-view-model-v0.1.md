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

## Streamlit trend views

The deployed Streamlit renderer also reads persisted history through the
read-only `DashboardDataStore` adapter:

- Market Score history is plotted only for rows with `status=available` and a
  finite score in the 0–100 range. Unavailable dates remain visible as status
  metadata and are never converted to zero.
- `twse_taiex_daily_v1` observations provide the TAIEX OHLC data for the
  candlestick view. Rows with non-available quality or incomplete OHLC are
  excluded from the plot and reported as unavailable.
- Factor trend lines come from the persisted `factor_scores_json` envelope.
  Each factor cell is missing unless its own status is `available` and its
  score is valid; the dashboard does not recalculate factors in the renderer.
- New score records retain the factor's raw input value, named raw values, and
  calculation window in that same JSON envelope. The dashboard labels the
  normalized result as `分數（0–100）` and shows the raw evidence with its unit;
  legacy records without those fields say `原始值尚未儲存` instead of guessing.
