"""One-time backfill of TAIFEX foreign TX open interest for a date range.

The daily production collector (``collect_taifex_institutional.py``) only
ever captures the latest snapshot. This script uses the website's date-range
download form instead, which serves a rolling window of roughly the most
recent three years. Because that window rolls forward with the current date,
running this promptly matters: delaying it permanently loses the older end
of the currently-available range. See docs/data-window-policy-v0.1.md.
"""

from __future__ import annotations

import argparse
import os
from collections.abc import Sequence
from datetime import date

from src.data import (
    SupabaseRestObservationStore,
    collect_institutional_futures_range,
    fetch_institutional_futures_range,
    summarize_write_results,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Backfill TAIFEX foreign TX open interest over a date range "
            "using the date-range download form (not the latest-snapshot API)."
        )
    )
    parser.add_argument(
        "--start", required=True, type=date.fromisoformat, help="First date, YYYY-MM-DD"
    )
    parser.add_argument(
        "--end", required=True, type=date.fromisoformat, help="Last date, YYYY-MM-DD"
    )
    parser.add_argument(
        "--contract-code",
        default="TXF",
        help="TAIFEX commodityId to query; defaults to 臺股期貨 (TXF).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Fetch and validate the range without writing to Supabase.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.start > args.end:
            raise ValueError("--start must not be after --end")

        if args.dry_run:
            observations = fetch_institutional_futures_range(
                args.start, args.end, contract_code=args.contract_code
            )
            print(
                f"TAIFEX institutional futures range {args.start}..{args.end}: "
                f"{len(observations)} daily rows validated"
            )
            return 0

        project_url = os.environ.get("SUPABASE_URL", "")
        secret_key = os.environ.get("SUPABASE_SECRET_KEY", "")
        if not project_url or not secret_key:
            raise RuntimeError(
                "SUPABASE_URL and SUPABASE_SECRET_KEY are required unless "
                "--dry-run is used"
            )
        with SupabaseRestObservationStore(project_url, secret_key) as store:
            results = collect_institutional_futures_range(
                store, args.start, args.end, contract_code=args.contract_code
            )
        summary = summarize_write_results(results)
        counts = ", ".join(f"{action}={count}" for action, count in summary.items())
        print(
            f"TAIFEX institutional futures range {args.start}..{args.end}: "
            f"{len(results)} daily rows written ({counts})"
        )
        return 0
    except Exception as exc:  # noqa: BLE001 - CLI reports one actionable failure
        print(f"TAIFEX institutional futures range backfill failed: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
