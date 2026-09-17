"""Fetch one TAIFEX TX annual archive and persist daily observations."""

from __future__ import annotations

import argparse
import os
from collections import Counter
from collections.abc import Sequence
from datetime import datetime
from zoneinfo import ZoneInfo

from src.data.supabase_rest import SupabaseRestObservationStore
from src.data.taifex_tx import collect_tx_year, fetch_tx_year

TAIWAN_TIMEZONE = ZoneInfo("Asia/Taipei")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Fetch a TAIFEX TX annual archive and write daily observations."
    )
    parser.add_argument(
        "--year", type=int, help="Calendar year; defaults to Taiwan time."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Fetch and validate the annual archive without writing to Supabase.",
    )
    return parser


def _target_year(year: int | None) -> int:
    return year if year is not None else datetime.now(TAIWAN_TIMEZONE).year


def _summarize(results: Sequence[object]) -> str:
    counts = Counter(getattr(result, "action", "unknown") for result in results)
    return ", ".join(f"{action}={count}" for action, count in sorted(counts.items()))


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        year = _target_year(args.year)
        if args.dry_run:
            observations = fetch_tx_year(year)
            print(
                f"TAIFEX TX {year:04d}: "
                f"{len(observations)} daily contract rows validated"
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
            results = collect_tx_year(store, year)
        print(
            f"TAIFEX TX {year:04d}: "
            f"{len(results)} daily contract rows written ({_summarize(results)})"
        )
        return 0
    except Exception as exc:  # noqa: BLE001 - CLI reports one actionable error
        print(f"TAIFEX TX ingestion failed: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
