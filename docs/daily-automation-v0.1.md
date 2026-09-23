# Daily automation v0.1

## Status

The workflow [`daily-market-automation.yml`](../.github/workflows/daily-market-automation.yml)
supports explicit manual runs and three scheduled passes: 16:30 and 22:00
Asia/Taipei on weekdays, plus 00:30 Asia/Taipei Tuesday-Saturday. The first two
use `30 8` and `0 14` UTC weekdays; the midnight pass uses five weekday-specific
cron entries from `30 16 * * 1` through `30 16 * * 5` UTC. Its cron identifies
the scheduled Taipei weekday if GitHub starts that run after the next day's
00:30 occurrence. The midnight pass resolves the preceding TWSE trading date
from the official TWSE holiday calendar, skipping weekends and listed market
closures. If the calendar cannot be fetched or validated, the run stops before
collection or scoring instead of guessing. Existing source-date guards stop a run
that has no data for its requested date, before scoring. The workflow acknowledges
the write internally and refreshes the score cutoff after all source collectors
finish, so rows ingested by the same run are eligible for scoring. The 22:00 and
00:30 passes confirm delayed or revised official data. Issue #18
still has outstanding backup/restore, access-separation, secret-rotation, quota,
and source-attribution work, so enabling this trigger is not approval for a final
production release.

The midnight resolver reads the year-specific JSON response from the [official
TWSE market open/closure calendar](https://www.twse.com.tw/holidaySchedule/holidaySchedule?response=html).
It recognizes explicit closed-day and special-open-day labels; an unknown
weekday label is treated as an invalid calendar and fails before collection.

## Run contract

For a manual run, an operator starts **Actions → Daily market automation
(supervised) → Run workflow** with:

- `target_date`: the explicit Taiwan market date in canonical `YYYY-MM-DD` form;
- `as_of`: an ISO-8601 timestamp with a timezone, normally entered in
  `Asia/Taipei` (for example, `2026-09-17T20:00:00+08:00`); and
- `confirm_write=true`, an explicit acknowledgement that the run may write source
  observations and the derived Market Score.

The scheduled path resolves `target_date` from the cron schedule and runner time,
then sets an initial timezone-aware `as_of` for input validation. For midnight
confirmation, the day-specific cron preserves the originating local weekday
across an overnight delay, while the TWSE calendar resolves the previous trading
date. After source
collection it refreshes the scheduled score cutoff to the current Taipei time;
manual runs retain their explicit `as_of`. Both paths normalize `as_of` to
`Asia/Taipei`, reject a target date after the Taiwan as-of date, and pass the same
target date to the date-specific collectors. The 00:30 Asia/Taipei schedule
targets the preceding TWSE trading date, including Friday when the Saturday
morning pass follows a weekend. A Taiwan market holiday is skipped using the
official calendar; a delayed/unavailable source still fails its expected-date
guard. Repeating a run with the same inputs is supported:
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
The midnight pass uses the TWSE holiday calendar to resolve the prior trading
date. The earlier weekday passes retain their calendar-date behavior and stop at
the source/date guards on exchange holidays without publishing a misleading
score; a manual rerun can use the last confirmed trading date.

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

The scheduled automation intentionally skips the prior three-trading-day
observation gate. The 16:30 pass is the first collection; the 22:00 pass repeats the same
target-date collection, and the 00:30 pass on the following Taipei date retries
the preceding TWSE trading date once more for late or revised source data. The
midnight target uses the official TWSE calendar; a missing or invalid calendar
stops the run before any data writes. The
one-writer concurrency group, strict source/date guards, bounded source retries,
and failure summary remain active. The failure summary identifies when scoring
was skipped and explains the TAIFEX expected-date gate. Source observations are
idempotent; a later cutoff can create a new auditable Market Score revision when
the evidence changes.
Backup/restore, access separation, secret rotation, quota, and source-term evidence
remain release gates tracked in Issue #18 and are handled separately.
