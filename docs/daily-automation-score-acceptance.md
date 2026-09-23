# Daily Market Score automation acceptance v0.1

This checklist records the executable contract for the daily Market Score
boundary. It covers the runner, score persistence semantics, and the dashboard
read path. It does not approve a production schedule or modify the collector.

## Acceptance matrix

| Contract | Evidence | Result |
| --- | --- | --- |
| `target_date` is explicit Taiwan market date | `run_daily_score` validates canonical `YYYY-MM-DD`, passes it to the reader and pipeline, and rejects a date after the Taipei date of `as_of`. | **Pass** |
| `as_of` is explicit and point-in-time | Runner requires a timezone, normalizes equivalent offsets to `Asia/Taipei`, and filters retrieval, ingestion, and publication timestamps at or before that boundary. | **Pass** |
| Missing data is persisted as unavailable | Empty or non-available source rows are excluded from factor inputs; the pipeline keeps per-factor unavailable states and the runner persists the envelope with null score/direction. | **Pass** |
| Same calculation rerun is idempotent | Persistence identity includes `model_version`, `target_date`, and `calculation_hash`; the REST writer returns `duplicate` for an existing identity. Equivalent `as_of` offsets therefore deduplicate. | **Pass** |
| Known later source revision is retained | A revision with changed source evidence and a retrieval timestamp inside the boundary changes the calculation hash and is inserted as a new score row. A future revision is excluded. | **Pass** |
| Dashboard can show the newest persisted result | `DashboardDataStore.get_latest_market_score()` reads `/market_scores` ordered by `target_date.desc,created_at.desc,id.desc` and includes unavailable rows instead of falling back to an older available score. | **Pass** |
| Read/write failures are distinguishable from source absence | Reader and writer exceptions propagate from `run_daily_score`; the CLI exits nonzero and emits a bounded error without transport details. | **Pass** |

The independent contract test in
`tests/test_daily_automation_contract.py` also verifies that an empty-source
run preserves the explicit target/as-of window and writes an unavailable
result. The broader runner and dashboard suites cover pagination, future
evidence, revisions, duplicate replay, and GET-only dashboard reads.

## Operational gate outside this code boundary

The workflow now has weekday 16:30 and 22:00 Asia/Taipei scheduled passes, plus
a 00:30 Asia/Taipei Tuesday-Saturday confirmation pass, with the same one-writer
concurrency policy as manual runs. The latter passes confirm late or revised
source data and retain strict target-date guards across the local date boundary.
The application contract and a live secret/table
smoke check are proven, while backup/restore, access separation, secret rotation,
quota, and source-term evidence remain release gates in Issue #18.

## Minimal follow-up if scheduling is enabled

Keep the workflow inputs explicit: every invocation must provide both
`target_date` and `as_of`; do not infer either from the latest observation.
Serialize invocations for one target/model, retain a failed run as an error,
and alert when no `market_scores` row is produced. A successful run may still
have `status=unavailable`; that state is a persisted data-quality result and
must remain visible in the dashboard.
