"""Fetch one TAIFEX VIX month and persist it through Supabase."""

from __future__ import annotations

import argparse
import os
from collections.abc import Sequence

from src.data import (
    SupabaseRestObservationStore,
    collect_vix_month,
    current_taiwan_month,
    fetch_vix_month,
    summarize_write_results,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Fetch a TAIFEX VIX month and write daily observations."
    )
    parser.add_argument(
        "--year", type=int, help="Calendar year; defaults to Taiwan time."
    )
    parser.add_argument(
        "--month", type=int, help="Calendar month 1-12; defaults to Taiwan time."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Fetch and validate the month without writing to Supabase.",
    )
    return parser


def _target_month(year: int | None, month: int | None) -> tuple[int, int]:
    if (year is None) != (month is None):
        raise ValueError("--year and --month must be provided together")
    return (
        (year, month)
        if year is not None and month is not None
        else current_taiwan_month()
    )


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        year, month = _target_month(args.year, args.month)
        if not 1 <= month <= 12:
            raise ValueError("--month must be between 1 and 12")
        if args.dry_run:
            observations = fetch_vix_month(year, month)
            print(
                f"TAIFEX VIX {year:04d}-{month:02d}: "
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
            results = collect_vix_month(store, year, month)
        summary = summarize_write_results(results)
        counts = ", ".join(f"{action}={count}" for action, count in summary.items())
        print(
            f"TAIFEX VIX {year:04d}-{month:02d}: "
            f"{len(results)} daily rows written ({counts})"
        )
        return 0
    except Exception as exc:
        print(f"TAIFEX VIX ingestion failed: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
