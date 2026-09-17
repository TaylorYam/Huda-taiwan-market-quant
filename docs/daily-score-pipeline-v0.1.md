# Daily Score Pipeline v0.1

`src/scoring/pipeline.py` is the first executable join between the factor
adapters and the Market Score contract. It accepts the saved daily
observations, applies the explicit target date and `as_of` boundary, scores
each factor, and returns a report that retains source identities.

```python
from src.scoring import calculate_daily_score

result = calculate_daily_score(
    taiex_observations=taiex_rows,
    pcr_observations=pcr_rows,
    tx_observations=tx_rows,
    vix_observations=vix_rows,
    target_date="2026-09-17",
    historical_values={
        "taiex_20d_momentum": previous_momentum_values,
        "tx_basis": previous_basis_values,
        "txo_oi_pcr": previous_pcr_values,
        "taiwan_vix": previous_vix_values,
    },
)
```

The history mapping must contain only values known by the selected `as_of`
boundary. If a percentile history is absent, or if a required source factor is
unavailable, the result remains explicitly `unavailable`; the pipeline does
not fill the gap with a neutral score or renormalize weights.

`DailyScoreResult.as_dict()` is intended as the stable handoff to a future
dashboard or persistence writer. It includes the model version, score state,
factor values, factor score states, windows, reasons, and source observation
identities.

The foreign cash factor remains blocked by the source contract. Foreign TX
open-interest inputs can now be calculated from institutional observations,
but missing snapshots, insufficient lookback, or a percentile history with
zero eligible historical points still leave their scores unavailable. The
aggregate remains unavailable while any required factor score is unavailable.


## Manual daily runner

Run from the repository root after installing `requirements-dev.txt`:

```sh
python -m src.scoring.daily_runner --target-date 2026-09-17 --as-of 2026-09-17T20:00:00+08:00
```

Set `SUPABASE_URL` and `SUPABASE_SECRET_KEY` in the server environment. Both
`observations` and `market_scores` must already exist and be exposed through
the Data API. This runner never applies schema changes. The manual **Manual
daily Market Score** Actions workflow accepts the same two required inputs and
uses repository secrets. It has no automatic schedule; backup/restore and
operational gates in ADR 0002 remain outstanding.

`target-date` is the explicit Taiwan market date, never inferred from the
latest available row or replaced by a prior trading date. `as-of` requires a
timezone and is normalized to UTC+08:00 before calculation and hashing.
Equivalent timestamp offsets therefore reproduce the same identity. Dates
after the Taiwan as-of date are rejected.

The reader loads all five supported datasets (TAIEX, PCR, TX, VIX and
institutional futures OI) through keyset pagination. A short Data API response
is not treated as end-of-history; it continues until an empty page. Retrieval
and ingestion timestamps must be at or before as-of, and future publication
timestamps are excluded. For sources without a publication timestamp, the
first retrieval and ingestion provide the conservative knowledge boundary.
Historical backfills obtained later cannot be used to reconstruct an earlier
knowledge state. Keep immutable observation revisions to reproduce a run;
this is not an atomic database snapshot across concurrent ingestion.

The runner invokes `calculate_daily_score` and `persist_market_score` without
changing the model, weights or existing calculation hash contract. Repeating
the same calculation returns `duplicate`; changed eligible source evidence
creates another record. Missing data is a successfully persisted
`unavailable` result with null score/direction and per-factor reasons. Read or
write failures exit nonzero instead of being converted into source absence.
The CLI emits a bounded summary without source URLs or raw API errors, and
redacts exceptions because upstream transport errors may contain credentials.

### Current result limitations

- Foreign cash (15%): `adapt_foreign_cash_input` combines free BFI82U (foreign
  net buy/sell) and FMTQIK (market turnover) into the 5-day ratio, but only
  for dates on or after `FOREIGN_CASH_VERIFIED_START` (2010-01-01); it is
  never filled with T86 shares. Dates before that stay unavailable, and the
  runner needs both `src/data/twse_foreign_cash.py` and
  `src/data/twse_market_turnover.py` to have collected data for all 5 window
  dates or the factor stays unavailable rather than using a partial window.
- Foreign TX OI (15% position + 10% five-day change): the existing adapter is
  connected, but usable snapshots and six observations for the five-day change
  are needed. No rows, stale rows, or insufficient lookback remain unavailable.
- Percentile scoring: the runner now builds each percentile factor's history
  via `src/scoring/history.py`'s `build_historical_values`, which replays that
  factor's own point-in-time adapter over every eligible date strictly before
  the target within a trailing window (3 years by default, 1 year for VIX,
  per `docs/factor-model-v0.1.md`'s initial assumption). This makes momentum,
  PCR, basis, VIX, foreign cash and the foreign TX position/change factors
  scoreable once enough raw history exists; it does not change the raw-input
  gates above, and the window length itself is still an unconfirmed v0.1
  hypothesis pending
  the Phase 3 backtest in `docs/backtest-spec-v0.1.md`. PCR also retains its
  existing model-policy gate on direction/threshold. Foreign cash stays
  unavailable regardless, since it has no raw input to build a history from.

The full factor result stays in the calculation; `market_scores` stores the
existing envelope of factor score states/reasons and source identities. No new
columns or migrations are introduced. Run only one writer: Actions serializes
this workflow, while operators must avoid concurrent CLI writes because the
existing REST writer checks then inserts without a transaction.

`tests/test_daily_runner.py` supplies synthetic observation fixtures and an
in-memory, page-capped Data API transport. It exercises actual REST adapter
reads/writes, replay deduplication, changed revisions, future evidence,
institutional routing, empty inputs, pagination failure and secret-safe errors
without a live database or credentials.
