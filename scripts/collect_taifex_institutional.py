"""Fetch the latest TAIFEX foreign TX open-interest snapshot."""

from __future__ import annotations

import argparse
import os
from collections.abc import Sequence
from datetime import date
from typing import Any

from src.data.storage import Observation, ObservationStore, WriteResult
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
    parser.add_argument(
        "--expected-date",
        metavar="YYYY-MM-DD",
        help=(
            "Require the official snapshot observation_date to match this date; "
            "a mismatch exits before persistence."
        ),
    )
    return parser


def _validate_expected_date(value: str | None) -> str | None:
    if value is None:
        return None
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("--expected-date must be YYYY-MM-DD") from exc
    if parsed.isoformat() != value:
        raise ValueError("--expected-date must be YYYY-MM-DD")
    return value


def _assert_expected_date(observation: Observation, expected_date: str) -> None:
    if observation.observation_date != expected_date:
        raise ValueError(
            "official institutional futures observation_date mismatch: "
            f"expected {expected_date}, got {observation.observation_date}"
        )


class _ExpectedDateStore:
    """Guard writes while preserving the collector's store implementation."""

    def __init__(self, store: ObservationStore, expected_date: str) -> None:
        self._store = store
        self._expected_date = expected_date

    def write_observation(self, observation: Observation) -> WriteResult:
        _assert_expected_date(observation, self._expected_date)
        return self._store.write_observation(observation)

    def __getattr__(self, name: str) -> Any:
        # The collector uses the store's private read helpers to link revisions;
        # forwarding keeps that behavior unchanged while the write guard runs.
        return getattr(self._store, name)


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        expected_date = _validate_expected_date(args.expected_date)
        if not args.write:
            observations = fetch_institutional_futures_latest()
            observation = observations[0]
            if expected_date is not None:
                _assert_expected_date(observation, expected_date)
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
            guarded_store = (
                _ExpectedDateStore(store, expected_date)
                if expected_date is not None
                else store
            )
            results = collect_institutional_futures_latest(guarded_store)
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
