"""Replay and optionally persist historical Market Score rows.

This command is for dashboard history, not formal model validation.  It uses
the Layer 1 point-in-time replay so each target date only sees observations
from that date (and earlier publication dates).  Existing rows for a target
date are preserved; a bulk replay must not hide a live score with a second
revision that happens to have a different calculation hash.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from datetime import date, timedelta
from typing import Any

from src.backtest.layer1 import build_score_series
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
from src.scoring.contracts import MODEL_VERSION, REQUIRED_FACTOR_IDS
from src.scoring.history import DEFAULT_WINDOW_YEARS
from src.scoring.pipeline import DailyScoreResult
from src.scoring.writer import persist_market_score

DATASETS: tuple[str, ...] = (
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
        "--start-date", required=True, help="First target date, YYYY-MM-DD"
    )
    parser.add_argument(
        "--end-date", required=True, help="Last target date, YYYY-MM-DD"
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="Persist results; without this flag the command is a dry run",
    )
    parser.add_argument(
        "--refresh-unavailable",
        action="store_true",
        help="Recalculate dates whose existing score status is unavailable",
    )
    parser.add_argument(
        "--refresh-missing-raw",
        action="store_true",
        help="Update existing dates whose available factors lack raw evidence",
    )
    return parser


def group_observations(rows: Iterable[Any]) -> dict[str, list[Any]]:
    """Group source rows by the dataset contract used by the replay."""

    grouped = {dataset: [] for dataset in DATASETS}
    for row in rows:
        dataset_id = getattr(row, "dataset_id", None)
        if dataset_id in grouped:
            grouped[dataset_id].append(row)
    return grouped


def existing_target_dates(rows: Iterable[Mapping[str, Any]]) -> set[str]:
    """Return dates with a persisted result, regardless of its status."""

    return {
        target_date
        for row in rows
        if isinstance(target_date := row.get("target_date"), str) and target_date
    }


def existing_available_target_dates(rows: Iterable[Mapping[str, Any]]) -> set[str]:
    """Return dates with an existing usable score, ignoring unavailable rows."""

    return {
        target_date
        for row in rows
        if row.get("status") == "available"
        and isinstance(target_date := row.get("target_date"), str)
        and target_date
    }


def _factor_has_raw_evidence(factor: object) -> bool:
    if not isinstance(factor, Mapping) or factor.get("status") != "available":
        return False
    raw_values = factor.get("raw_values")
    if isinstance(raw_values, Mapping) and raw_values:
        return True
    return factor.get("raw_value") is not None


def has_complete_raw_evidence(row: Mapping[str, Any]) -> bool:
    """Return whether every available v0.1 factor retains its raw input."""

    factors = row.get("factor_scores_json")
    if not isinstance(factors, Mapping):
        return False
    return all(
        _factor_has_raw_evidence(factors.get(factor_id))
        for factor_id in REQUIRED_FACTOR_IDS
    )


def existing_target_dates_for_refresh(
    rows: Iterable[Mapping[str, Any]],
    *,
    refresh_unavailable: bool,
    refresh_missing_raw: bool,
) -> set[str]:
    """Select dates that should remain untouched for a requested refresh."""

    latest_by_target: dict[str, Mapping[str, Any]] = {}
    for row in rows:
        target_date = row.get("target_date")
        if isinstance(target_date, str) and target_date:
            latest_by_target[target_date] = row

    existing: set[str] = set()
    for target_date, row in latest_by_target.items():
        status = row.get("status")
        if status == "unavailable" and refresh_unavailable:
            continue
        if (
            status == "available"
            and refresh_missing_raw
            and not has_complete_raw_evidence(row)
        ):
            continue
        existing.add(target_date)
    return existing


def summarize_results(
    results: Sequence[DailyScoreResult],
    *,
    start_date: str,
    end_date: str,
    skipped_existing_dates: int,
    write: bool,
    refresh_unavailable: bool = False,
    refresh_missing_raw: bool = False,
    inserted: int = 0,
    duplicates: int = 0,
    updated: int = 0,
) -> dict[str, Any]:
    """Create a bounded, safe summary suitable for Actions logs."""

    status_counts = Counter(result.status for result in results)
    reason_counts = Counter(
        result.market_score.reason for result in results if result.market_score.reason
    )
    missing_factor_counts = Counter(
        factor_id
        for result in results
        for factor_id in result.market_score.missing_factor_ids
    )
    unavailable_samples = [
        {
            "target_date": result.target_date,
            "missing_factor_ids": list(result.market_score.missing_factor_ids),
            "factor_reasons": {
                factor_id: result.factor_scores[factor_id].reason
                for factor_id in result.market_score.missing_factor_ids
                if factor_id in result.factor_scores
                and result.factor_scores[factor_id].reason
            },
        }
        for result in results
        if result.status == "unavailable"
    ][:10]
    return {
        "model_version": MODEL_VERSION,
        "start_date": start_date,
        "end_date": end_date,
        "candidate_days": len(results),
        "available_days": status_counts.get("available", 0),
        "unavailable_days": status_counts.get("unavailable", 0),
        "status_counts": dict(sorted(status_counts.items())),
        "reason_counts": dict(sorted(reason_counts.items())),
        "missing_factor_counts": dict(sorted(missing_factor_counts.items())),
        "unavailable_samples": unavailable_samples,
        "skipped_existing_dates": skipped_existing_dates,
        "write_mode": write,
        "refresh_unavailable": refresh_unavailable,
        "refresh_missing_raw": refresh_missing_raw,
        "inserted": inserted,
        "duplicates": duplicates,
        "updated": updated,
    }


def _date_range(args: argparse.Namespace) -> tuple[date, date]:
    start = date.fromisoformat(args.start_date)
    end = date.fromisoformat(args.end_date)
    if start > end:
        raise ValueError("--start-date must not be after --end-date")
    return start, end


def _build_results(
    rows: Sequence[Any], *, start: date, end: date
) -> list[DailyScoreResult]:
    grouped = group_observations(rows)
    return build_score_series(
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


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        start, end = _date_range(args)
        url = os.environ["SUPABASE_URL"]
        key = os.environ["SUPABASE_SECRET_KEY"]
        # The longest percentile window plus a raw-indicator cushion is needed
        # before the first requested day.  This does not widen the output
        # range, only the source rows loaded for point-in-time replay.
        fetch_from = start - timedelta(days=365 * _MAX_WINDOW_YEARS + 90)
        with SupabaseRestObservationStore(url, key) as store:
            rows = store.load_backtest_observations(
                dataset_ids=DATASETS,
                start_date=fetch_from.isoformat(),
                end_date=end.isoformat(),
            )
            results = _build_results(rows, start=start, end=end)
            score_rows = store.list_market_scores(
                model_version=MODEL_VERSION,
                start_date=start.isoformat(),
                end_date=end.isoformat(),
                include_factor_scores=args.refresh_missing_raw,
            )
            existing = existing_target_dates(score_rows)
            if args.refresh_unavailable or args.refresh_missing_raw:
                existing = existing_target_dates_for_refresh(
                    score_rows,
                    refresh_unavailable=args.refresh_unavailable,
                    refresh_missing_raw=args.refresh_missing_raw,
                )
            pending = [
                result for result in results if result.target_date not in existing
            ]
            if args.write:
                inserted = 0
                duplicates = 0
                updated = 0
                for result in pending:
                    _, outcome = persist_market_score(store, result)
                    action = getattr(outcome, "action", None)
                    if action == "inserted":
                        inserted += 1
                    elif action == "duplicate":
                        duplicates += 1
                    elif action == "updated":
                        updated += 1
                summary = summarize_results(
                    results,
                    start_date=start.isoformat(),
                    end_date=end.isoformat(),
                    skipped_existing_dates=len(results) - len(pending),
                    write=True,
                    refresh_unavailable=args.refresh_unavailable,
                    refresh_missing_raw=args.refresh_missing_raw,
                    inserted=inserted,
                    duplicates=duplicates,
                    updated=updated,
                )
            else:
                summary = summarize_results(
                    results,
                    start_date=start.isoformat(),
                    end_date=end.isoformat(),
                    skipped_existing_dates=len(results) - len(pending),
                    write=False,
                    refresh_unavailable=args.refresh_unavailable,
                    refresh_missing_raw=args.refresh_missing_raw,
                )
    except Exception:  # noqa: BLE001 - CLI boundary must not print secrets
        print(
            "Market Score history backfill failed. Check dates and server "
            "configuration; no result is confirmed.",
            file=sys.stderr,
        )
        return 1

    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
