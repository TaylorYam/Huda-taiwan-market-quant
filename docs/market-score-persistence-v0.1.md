# Market Score Persistence v0.1

`src/scoring/persistence.py` turns a `DailyScoreResult` into a
`MarketScoreRecord`. The record keeps the model version, target date, as-of
boundary, aggregate status, score or unavailable reason, factor score states,
and the de-duplicated source observation identities used by the calculation.

`calculation_hash` is a SHA-256 digest of the canonical JSON report. It is the
idempotency key for the same model, target date and input evidence. A changed
source revision or model output creates a new hash and leaves the prior result
available for audit and backtest comparison.

The checked-in migration [`002_market_scores.sql`](../src/data/sql/002_market_scores.sql)
creates the PostgreSQL table with value-state checks, a latest-date index and
RLS enabled. Applying the migration to Supabase is a separate remote operation;
this commit does not contain credentials or claim that the remote table has
already been created.
