"""Run the Layer 1 Market Score backtest against persisted observations.

Layer 1 (docs/backtest-spec-v0.1.md#2) asks whether the score ranks future
TAIEX returns; it does not simulate a position or costs. This CLI replays
the same scoring pipeline the daily runner uses, across every trading day in
the requested range, and prints the section-9 style bucket report.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date, timedelta

from src.backtest import format_report, run_layer1_backtest
from src.data.supabase_rest import SupabaseRestObservationStore
from src.factors.contracts import (
    FOREIGN_CASH_DATASET_ID,
    INSTITUTIONAL_FUTURES_DATASET_ID,
    MARKET_TURNOVER_DATASET_ID,
    PCR_DATASET_ID,
    TAIEX_DATASET_ID,
    TX_DATASET_ID,
    VIX_DATASET_ID,
)
from src.scoring.history import DEFAULT_WINDOW_YEARS

DATASETS = (
    TAIEX_DATASET_ID,
    PCR_DATASET_ID,
    TX_DATASET_ID,
    VIX_DATASET_ID,
    INSTITUTIONAL_FUTURES_DATASET_ID,
    FOREIGN_CASH_DATASET_ID,
    MARKET_TURNOVER_DATASET_ID,
)
_MAX_WINDOW_YEARS = max(DEFAULT_WINDOW_YEARS.values())


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--start-date", required=True, help="Backtest start, Taiwan date YYYY-MM-DD"
    )
    parser.add_argument(
        "--end-date",
        required=True,
        help="Backtest end (inclusive), Taiwan date YYYY-MM-DD",
    )
    parser.add_argument(
        "--warmup-years",
        type=int,
        default=_MAX_WINDOW_YEARS,
        help=(
            "Extra years of history fetched before --start-date so the "
            "earliest backtest days already have a full percentile window "
            f"(default matches the model's own longest window, {_MAX_WINDOW_YEARS}y). "
            "Does not widen the reported backtest period."
        ),
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print the machine-readable summary instead of the text report",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        start = date.fromisoformat(args.start_date)
        end = date.fromisoformat(args.end_date)
        if start > end:
            raise ValueError("--start-date must not be after --end-date")
        if args.warmup_years < 0:
            raise ValueError("--warmup-years must not be negative")
        # +90 calendar days pads the raw MA60/momentum warm-up on top of the
        # percentile window itself, so the first requested day is not starved.
        fetch_from = start - timedelta(days=365 * args.warmup_years + 90)

        url = os.environ["SUPABASE_URL"]
        key = os.environ["SUPABASE_SECRET_KEY"]
        with SupabaseRestObservationStore(url, key) as store:
            rows = store.load_backtest_observations(
                dataset_ids=DATASETS,
                start_date=fetch_from.isoformat(),
                end_date=end.isoformat(),
            )
        grouped = {
            dataset: [row for row in rows if row.dataset_id == dataset]
            for dataset in DATASETS
        }
        report = run_layer1_backtest(
            taiex_observations=grouped[TAIEX_DATASET_ID],
            pcr_observations=grouped[PCR_DATASET_ID],
            tx_observations=grouped[TX_DATASET_ID],
            vix_observations=grouped[VIX_DATASET_ID],
            institutional_observations=grouped[INSTITUTIONAL_FUTURES_DATASET_ID],
            cash_observations=grouped[FOREIGN_CASH_DATASET_ID],
            turnover_observations=grouped[MARKET_TURNOVER_DATASET_ID],
            start_date=start,
            end_date=end,
        )
    except Exception:  # noqa: BLE001 - CLI boundary must redact transport errors
        print(
            "Layer 1 backtest failed. Check dates and server configuration; "
            "no result is confirmed.",
            file=sys.stderr,
        )
        return 1
    if args.json:
        print(json.dumps(report.as_dict(), ensure_ascii=False, sort_keys=True))
    else:
        print(format_report(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
