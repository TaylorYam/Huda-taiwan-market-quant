# Daily Market Score automation acceptance v0.1

This checklist records the executable contract for the daily Market Score
boundary. It covers the runner, score persistence semantics, and the dashboard
read path. It does not approve a production schedule or modify the collector.

## Acceptance matrix

| Contract | Evidence | Result |
| --- | --- | --- |
| `target_date` is explicit Taiwan market date | `run_daily_score` validates canonical `YYYY-MM-DD`, passes it to the reader and pipeline, and rejects a date after the Taipei date of `as_of`. | **Pass** |
| `as_of` is explicit and point-in-time | Runner requires a timezone, normalizes equivalent offsets to `Asia/Taipei`, and filters retrieval, ingestion, and publication timestamps at or before that boundary. | **Pass** |
| Score-only replay can persist unavailable | Empty or non-available source rows are excluded from factor inputs; the point-in-time runner keeps per-factor unavailable states and, by default, persists the envelope with null score/direction. | **Pass** |
| Integrated update requires an available score | The integrated workflow invokes the runner with `--require-available`; missing factors produce a nonzero result before the Market Score write. A blank manual cutoff is refreshed after collection; an explicit cutoff remains unchanged. | **Pass** |
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

The workflow has weekday 16:30 and 22:00 Asia/Taipei scheduled passes, plus
00:30 and 10:30 Asia/Taipei Tuesday-Saturday confirmation passes. Each overnight
weekday has its own cron so the originating local weekday remains identifiable
if execution is delayed into the next scheduled day. Both passes resolve the
previous TWSE trading date from the official holiday calendar and stop before
collection if that calendar cannot be validated. Transient calendar timeouts,
connection errors, retryable server responses, and invalid JSON are retried up to
three times. All passes retain the same one-writer concurrency policy and strict
source-date guards.
The application contract and a live secret/table
smoke check are proven, while backup/restore, access separation, secret rotation,
quota, and source-term evidence remain release gates in Issue #18.

## Minimal follow-up if scheduling is enabled

Keep `target_date` explicit. The integrated workflow may use an automatic
post-collection `as_of` or preserve an intentionally supplied point-in-time
cutoff; it never infers the market date from the latest observation. Serialize
invocations for one target/model and retain a failed run as an error. A green
integrated run must have persisted an available score. The separate score-only
replay may still persist `status=unavailable` for data-quality diagnosis, and
that state remains visible in the dashboard.
