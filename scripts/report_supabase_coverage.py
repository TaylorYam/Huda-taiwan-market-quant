"""Report persisted daily coverage and the v0.1 model's raw common start."""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from datetime import date

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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", required=True, help="First date, YYYY-MM-DD")
    parser.add_argument("--end", required=True, help="Last date, YYYY-MM-DD")
    parser.add_argument(
        "--json", action="store_true", help="Print machine-readable JSON"
    )
    return parser


def _summary(rows: list[object]) -> dict[str, object]:
    dates: list[str] = []
    available: list[str] = []
    statuses: Counter[str] = Counter()
    for row in rows:
        observation_date = str(row.observation_date)
        dates.append(observation_date)
        status = str(row.quality_status)
        statuses[status] += 1
        if status == "available":
            available.append(observation_date)
    distinct_available = sorted(set(available))
    return {
        "row_count": len(rows),
        "observed_date_count": len(set(dates)),
        "available_date_count": len(distinct_available),
        "earliest_date": min(dates) if dates else None,
        "latest_date": max(dates) if dates else None,
        "available_earliest_date": distinct_available[0]
        if distinct_available
        else None,
        "available_latest_date": distinct_available[-1] if distinct_available else None,
        "quality_status_counts": dict(sorted(statuses.items())),
    }


def _add_years(value: date, years: int) -> date:
    try:
        return value.replace(year=value.year + years)
    except ValueError:
        return value.replace(month=2, day=28, year=value.year + years)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        start = date.fromisoformat(args.start)
        end = date.fromisoformat(args.end)
        if start > end:
            raise ValueError("--start must not be after --end")
        url = os.environ["SUPABASE_URL"]
        key = os.environ["SUPABASE_SECRET_KEY"]
        with SupabaseRestObservationStore(url, key) as store:
            rows = store.load_backtest_observations(
                dataset_ids=DATASETS,
                start_date=start.isoformat(),
                end_date=end.isoformat(),
            )
        grouped = {
            dataset_id: [row for row in rows if row.dataset_id == dataset_id]
            for dataset_id in DATASETS
        }
        summaries = {dataset_id: _summary(rows) for dataset_id, rows in grouped.items()}
        starts = [
            str(summary["available_earliest_date"])
            for summary in summaries.values()
            if summary["available_earliest_date"] is not None
        ]
        raw_common_start = max(starts) if len(starts) == len(DATASETS) else None
        earliest_percentile_ready = (
            _add_years(
                date.fromisoformat(raw_common_start),
                max(DEFAULT_WINDOW_YEARS.values()),
            ).isoformat()
            if raw_common_start is not None
            else None
        )
        report = {
            "requested_start": start.isoformat(),
            "requested_end": end.isoformat(),
            "datasets": summaries,
            "raw_common_start": raw_common_start,
            "max_percentile_window_years": max(DEFAULT_WINDOW_YEARS.values()),
            "earliest_percentile_ready_date": earliest_percentile_ready,
            "backtest_ready": earliest_percentile_ready is not None
            and earliest_percentile_ready <= end.isoformat(),
        }
        if args.json:
            print(json.dumps(report, ensure_ascii=False, sort_keys=True))
        else:
            print("Supabase persisted coverage")
            for dataset_id, summary in summaries.items():
                print(
                    f"- {dataset_id}: {summary['available_date_count']} dates; "
                    f"{summary['available_earliest_date']}.."
                    f"{summary['available_latest_date']}"
                )
            print(f"raw_common_start={report['raw_common_start']}")
            print(
                "earliest_percentile_ready_date="
                f"{report['earliest_percentile_ready_date']}"
            )
            print(
                "backtest_ready="
                f"{report['backtest_ready']} "
                f"(max percentile window {report['max_percentile_window_years']} years)"
            )
        return 0
    except Exception as exc:  # noqa: BLE001 - CLI boundary must redact transport errors
        print(f"Supabase coverage report failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
