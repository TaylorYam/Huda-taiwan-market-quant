"""Backfill the free TWSE/TAIFEX factor sources over a date range.

The script keeps the source-specific parsers and writes only validated
observations.  It is intended for a manually triggered GitHub Actions run;
production schedules remain separate and are not enabled by this command.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from collections import Counter
from collections.abc import Sequence
from datetime import date, timedelta

import requests

from src.data import (
    SupabaseRestObservationStore,
    fetch_foreign_cash_day,
    fetch_market_turnover_month,
    fetch_pcr_day,
    fetch_taiex_month,
    fetch_tx_day,
    fetch_tx_year,
)
from src.data.storage import Observation, WriteResult
from src.data.taifex_pcr import PCRFetchError, PCRParseError
from src.data.twse_foreign_cash import ForeignCashFetchError, ForeignCashParseError


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", required=True, type=date.fromisoformat)
    parser.add_argument("--end", required=True, type=date.fromisoformat)
    parser.add_argument(
        "--dry-run", action="store_true", help="Fetch and parse without writing"
    )
    parser.add_argument(
        "--request-delay", type=float, default=0.2, help="Delay between daily requests"
    )
    return parser


def _months(start: date, end: date) -> list[tuple[int, int]]:
    current = date(start.year, start.month, 1)
    last = date(end.year, end.month, 1)
    values: list[tuple[int, int]] = []
    while current <= last:
        values.append((current.year, current.month))
        current = (
            date(current.year + 1, 1, 1)
            if current.month == 12
            else date(current.year, current.month + 1, 1)
        )
    return values


def _dates(start: date, end: date) -> list[date]:
    return [start + timedelta(days=offset) for offset in range((end - start).days + 1)]


def _filter_range(
    observations: Sequence[Observation], start: date, end: date
) -> list[Observation]:
    return [
        observation
        for observation in observations
        if start <= date.fromisoformat(observation.observation_date) <= end
    ]


def _write_in_chunks(
    store: SupabaseRestObservationStore,
    observations: Sequence[Observation],
    *,
    dry_run: bool,
) -> list[WriteResult]:
    if dry_run:
        return []
    results: list[WriteResult] = []
    for offset in range(0, len(observations), 500):
        results.extend(store.write_observations(observations[offset : offset + 500]))
    return results


def _count_actions(results: Sequence[WriteResult]) -> str:
    counts = Counter(result.action for result in results)
    return ", ".join(f"{action}={count}" for action, count in sorted(counts.items()))


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.start > args.end:
            raise ValueError("--start must not be after --end")
        if args.request_delay < 0:
            raise ValueError("--request-delay must not be negative")

        project_url = os.environ.get("SUPABASE_URL", "")
        secret_key = os.environ.get("SUPABASE_SECRET_KEY", "")
        if not args.dry_run and (not project_url or not secret_key):
            raise RuntimeError(
                "SUPABASE_URL and SUPABASE_SECRET_KEY are required unless --dry-run is used"
            )

        session = requests.Session()
        session.headers.update(
            {
                "User-Agent": "HudaTaiwanQuant/0.1",
                "Referer": "https://www.twse.com.tw/",
            }
        )

        def get(url: str) -> bytes:
            response = session.get(url, timeout=60)
            response.raise_for_status()
            return response.content

        def post(url: str, data: object) -> bytes:
            response = session.post(url, data=data, timeout=60)
            response.raise_for_status()
            return response.content

        collected: dict[str, list[Observation]] = {}

        taiex: list[Observation] = []
        turnover: list[Observation] = []
        for year, month in _months(args.start, args.end):
            taiex.extend(
                _filter_range(
                    fetch_taiex_month(year, month, http_get=get), args.start, args.end
                )
            )
            turnover.extend(
                _filter_range(
                    fetch_market_turnover_month(year, month, http_get=get),
                    args.start,
                    args.end,
                )
            )
        collected["taiex"] = taiex
        collected["turnover"] = turnover

        pcr: list[Observation] = []
        cash: list[Observation] = []
        skipped_cash = 0
        for target in _dates(args.start, args.end):
            try:
                pcr.extend(fetch_pcr_day(target, http_post=post))
            except (PCRFetchError, PCRParseError) as exc:
                raise RuntimeError(f"PCR {target.isoformat()} failed: {exc}") from exc
            try:
                cash.extend(fetch_foreign_cash_day(target, http_get=get))
            except (ForeignCashFetchError, ForeignCashParseError):
                # Weekends and exchange holidays have no BFI82U daily row.
                skipped_cash += 1
            if args.request_delay:
                time.sleep(args.request_delay)
        collected["pcr"] = _filter_range(pcr, args.start, args.end)
        collected["cash"] = _filter_range(cash, args.start, args.end)

        tx: list[Observation] = []
        for year in range(args.start.year, min(args.end.year, 2025) + 1):
            tx.extend(
                _filter_range(fetch_tx_year(year, http_post=post), args.start, args.end)
            )
        # TAIFEX publishes the current year through the date-based daily page;
        # the annual ZIP appears only after the calendar year closes.  Keep the
        # day session because the basis adapter intentionally selects session
        # ``一般`` and does not need the after-hours duplicate.
        current_year_start = max(args.start, date(2026, 1, 1))
        if current_year_start <= args.end:
            for target in _dates(current_year_start, args.end):
                tx.extend(fetch_tx_day(target, market_code=0, http_post=post))
                if args.request_delay:
                    time.sleep(args.request_delay)
        collected["tx"] = tx

        if args.dry_run:
            for name, observations in collected.items():
                print(f"{name}: {len(observations)} validated rows")
        else:
            with SupabaseRestObservationStore(project_url, secret_key) as store:
                for name, observations in collected.items():
                    results = _write_in_chunks(store, observations, dry_run=False)
                    print(
                        f"{name}: {len(observations)} rows written"
                        f" ({_count_actions(results) or 'none'})"
                    )
        print(f"cash skipped non-trading/unavailable days: {skipped_cash}")
        print(
            "TX source: annual ZIP through 2025 plus the official date-based "
            "day-session report for 2026 and later."
        )
        return 0
    except Exception as exc:  # noqa: BLE001 - CLI boundary keeps logs actionable
        print(f"Free factor range backfill failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
