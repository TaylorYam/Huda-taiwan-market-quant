"""Fetch the latest TAIFEX foreign TX open-interest snapshot."""

from __future__ import annotations

import argparse
import os
from collections.abc import Sequence

from src.data.supabase_rest import SupabaseRestObservationStore
from src.data.taifex_institutional import (
    collect_institutional_futures_latest,
    fetch_institutional_futures_latest,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Fetch the latest TAIFEX foreign TX open-interest snapshot."
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="Persist the validated snapshot to Supabase; default is read-only.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if not args.write:
            observations = fetch_institutional_futures_latest()
            observation = observations[0]
            print(
                "TAIFEX institutional futures latest: "
                f"source_date={observation.source_date} "
                f"open_interest_net={observation.values['open_interest_net']} "
                "quality_status=available (read-only)"
            )
            return 0

        project_url = os.environ.get("SUPABASE_URL", "")
        secret_key = os.environ.get("SUPABASE_SECRET_KEY", "")
        if not project_url or not secret_key:
            raise RuntimeError(
                "SUPABASE_URL and SUPABASE_SECRET_KEY are required with --write"
            )
        with SupabaseRestObservationStore(project_url, secret_key) as store:
            results = collect_institutional_futures_latest(store)
        result = results[0]
        print(
            "TAIFEX institutional futures latest: "
            f"{result.action} observation_id={result.observation_id}"
        )
        return 0
    except Exception as exc:  # noqa: BLE001 - CLI reports one actionable failure
        print(f"TAIFEX institutional futures ingestion failed: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
