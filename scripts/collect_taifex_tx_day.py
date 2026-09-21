"""Fetch one TAIFEX date-based TX report and persist its daily observations."""

from __future__ import annotations

import argparse
import os
from collections import Counter
from collections.abc import Sequence
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

from src.data.supabase_rest import SupabaseRestObservationStore
from src.data.taifex_tx_daily import collect_tx_day, fetch_tx_day

TAIWAN_TIMEZONE = ZoneInfo("Asia/Taipei")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Fetch one TAIFEX date-based TX report and write observations."
    )
    parser.add_argument(
        "--date",
        dest="observation_date",
        help="Trading date, YYYY-MM-DD; defaults to today's Taiwan date.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Fetch and validate without writing to Supabase.",
    )
    return parser


def _target_date(value: str | None) -> date:
    if value:
        try:
            return date.fromisoformat(value)
        except ValueError as exc:
            raise ValueError("--date must use YYYY-MM-DD") from exc
    return datetime.now(timezone.utc).astimezone(TAIWAN_TIMEZONE).date()


def _summarize(results: Sequence[object]) -> str:
    counts = Counter(getattr(result, "action", "unknown") for result in results)
    return ", ".join(f"{action}={count}" for action, count in sorted(counts.items()))


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        target = _target_date(args.observation_date)
        if args.dry_run:
            observations = fetch_tx_day(target)
            print(
                f"TAIFEX TX {target.isoformat()}: "
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
            results = collect_tx_day(store, target)
        print(
            f"TAIFEX TX {target.isoformat()}: "
            f"{len(results)} daily contract rows written ({_summarize(results)})"
        )
        return 0
    except Exception as exc:  # noqa: BLE001 - CLI reports one actionable failure
        print(f"TAIFEX TX daily ingestion failed: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
