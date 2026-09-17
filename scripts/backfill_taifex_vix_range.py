"""One-time backfill of TAIFEX Taiwan VIX daily closes for a date range.

The daily production collector (``collect_taifex_vix_month.py``) only reads
the log2data monthly files, which cover a rolling ~3-4 month window. This
script instead calls the index-chart JSON API behind the 指數專區 page's
"3年" range picker, which serves a genuine rolling ~3-year window. Because
that window rolls forward with the current date, running this promptly
matters: delaying it permanently loses the older end of the
currently-available range. See docs/data-window-policy-v0.1.md.
"""

from __future__ import annotations

import argparse
import os
from collections.abc import Sequence
from datetime import date

from src.data import (
    SupabaseRestObservationStore,
    collect_vix_range,
    fetch_vix_range,
    summarize_write_results,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Backfill Taiwan VIX daily closes over a date range using the "
            "index-chart range API (not the log2data monthly files)."
        )
    )
    parser.add_argument(
        "--start", required=True, type=date.fromisoformat, help="First date, YYYY-MM-DD"
    )
    parser.add_argument(
        "--end", required=True, type=date.fromisoformat, help="Last date, YYYY-MM-DD"
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
            observations = fetch_vix_range(args.start, args.end)
            print(
                f"TAIFEX VIX range {args.start}..{args.end}: "
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
            results = collect_vix_range(store, args.start, args.end)
        summary = summarize_write_results(results)
        counts = ", ".join(f"{action}={count}" for action, count in summary.items())
        print(
            f"TAIFEX VIX range {args.start}..{args.end}: "
            f"{len(results)} daily rows written ({counts})"
        )
        return 0
    except Exception as exc:  # noqa: BLE001 - CLI reports one actionable failure
        print(f"TAIFEX VIX range backfill failed: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
