# Daily automation v0.1

## Status

The workflow [`daily-market-automation.yml`](../.github/workflows/daily-market-automation.yml)
supports both explicit manual runs and two weekday scheduled passes at 16:30 and
22:00 Asia/Taipei (`30 8` and `0 14` in GitHub Actions UTC). The schedule derives
the target date from the planned local schedule time, so a delayed run that
crosses midnight remains on the intended market date. It acknowledges the write
internally and refreshes the score cutoff after all source collectors finish, so
rows ingested by the same run are eligible for scoring. The later pass is a
confirmation run for delayed or revised official data. Issue #18
still has outstanding backup/restore, access-separation, secret-rotation, quota,
and source-attribution work, so enabling this trigger is not approval for a final
production release.

## Run contract

For a manual run, an operator starts **Actions → Daily market automation
(supervised) → Run workflow** with:

- `target_date`: the explicit Taiwan market date in canonical `YYYY-MM-DD` form;
- `as_of`: an ISO-8601 timestamp with a timezone, normally entered in
  `Asia/Taipei` (for example, `2026-09-17T20:00:00+08:00`); and
- `confirm_write=true`, an explicit acknowledgement that the run may write source
  observations and the derived Market Score.

The scheduled path resolves `target_date` from the cron schedule and runner time,
then sets an initial timezone-aware `as_of` for input validation. After source
collection it refreshes the scheduled score cutoff to the current Taipei time;
manual runs retain their explicit `as_of`. Both paths normalize `as_of` to
`Asia/Taipei`, reject a target date after the Taiwan as-of date, and pass the same
target date to the date-specific collectors. Repeating a run with the same inputs is supported:
the existing observation and Market Score writers preserve duplicate detection and
revision lineage.

The only credentials used are the existing `SUPABASE_URL` and
`SUPABASE_SECRET_KEY` Actions secrets. The workflow checks that both names are
available without printing their values. The concurrency group allows only one
daily automation run at a time and does not cancel an in-flight run.

## Ordered execution

All source steps are separate steps in one job. GitHub Actions stops the job on the
first non-zero collector result, so Market Score cannot run after partial source
collection:

1. TAIEX month (`target_date` year and month)
2. TWSE BFI82U foreign cash day (`target_date`)
3. TWSE FMTQIK market turnover month (`target_date` year and month)
4. TAIFEX TX day (`target_date`)
5. TAIFEX PCR day (`target_date`)
6. TAIFEX VIX month (`target_date` year and month)
7. TAIFEX foreign TX open-interest latest snapshot
8. `src.scoring.daily_runner` with the normalized target/as-of window

The score runner reads all seven supported datasets, applies its point-in-time
filters using the refreshed scheduled cutoff, and persists an available or
explicitly unavailable result. It does not create or alter the Supabase schema.

## Known v0.1 limits

The existing collector interfaces do not all have a single-day contract. TAIEX,
FMTQIK, and VIX collect a whole month, while the TX daily endpoint now collects
the exact requested date. The institutional futures command still exposes only the
latest official snapshot; the workflow passes `--expected-date` so a snapshot for
another date fails before persistence instead of being silently associated with
the requested target. A historical manual rerun can therefore collect rows outside
the requested date for the month-based sources, or stop when the latest snapshot
does not match. This is why the workflow requires explicit inputs and remains
supervised.
The workflow does not infer a prior trading day when an exchange is closed. A
weekday schedule on a Taiwan holiday therefore stops at the source/date guards
without publishing a misleading score; a manual rerun can use the last confirmed
trading date.

The workflow is not a transactional boundary across the source writes and score
write. If a later source or scoring step fails, earlier successful writes remain
idempotent durable observations. Rerun after fixing the reported issue and inspect
the resulting score's target date, as-of, status, and factor coverage.

## Failure handling

Each successful collector appends a job-summary section with its source name,
requested `target_date`, collection window, and completion result. The score step
adds its normalized `as_of` boundary. A small runner-local stage marker is written
before every source and score command, so the final failure summary identifies the
last stage that started as well as the requested input window. A failed collector
does not append its completion section, and the score step is skipped.

The failure summary does not include credentials, source payloads, or raw transport
errors. The failed step's log is the place to inspect the bounded error from that
collector or the score CLI; source scripts and the score CLI retain their existing
secret-safe error boundaries. Earlier successful source writes may remain durable,
so reruns should use the same explicit inputs after the cause is addressed.

## Schedule operation

The weekday schedule intentionally skips the prior three-trading-day observation
gate. The 16:30 pass is the first collection; the 22:00 pass repeats the same
target-date collection as a confirmation for late or revised source data. The
one-writer concurrency group, strict source/date guards, bounded source retries,
and failure summary remain active. Source observations are idempotent; a later
cutoff can create a new auditable Market Score revision when the evidence changes.
Backup/restore, access separation, secret rotation, quota, and source-term evidence
remain release gates tracked in Issue #18 and are handled separately.
