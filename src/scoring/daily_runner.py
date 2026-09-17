"""Manual, point-in-time daily calculation and persistence entry point."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date, datetime, timedelta, timezone
from typing import Protocol

from src.data.storage import Observation
from src.data.supabase_rest import SupabaseRestObservationStore
from src.factors.contracts import (
    INSTITUTIONAL_FUTURES_DATASET_ID,
    PCR_DATASET_ID,
    TAIEX_DATASET_ID,
    TX_DATASET_ID,
    VIX_DATASET_ID,
)
from src.scoring.pipeline import calculate_daily_score
from src.scoring.writer import MarketScoreWriter, persist_market_score

DATASETS = (
    TAIEX_DATASET_ID,
    PCR_DATASET_ID,
    TX_DATASET_ID,
    VIX_DATASET_ID,
    INSTITUTIONAL_FUTURES_DATASET_ID,
)
TAIPEI = timezone(timedelta(hours=8))


class ScoreObservationReader(Protocol):
    def load_score_observations(
        self, *, dataset_ids: tuple[str, ...], target_date: str, as_of: str
    ) -> list[Observation]: ...


def _timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("as-of and observation timestamps must include a timezone")
    return parsed


def run_daily_score(
    reader: ScoreObservationReader,
    writer: MarketScoreWriter,
    *,
    target_date: str,
    as_of: str,
) -> dict[str, object]:
    """Persist unavailable results too; transport failures must propagate.

    No percentile history is invented: its window/coverage policy has not yet
    been implemented. Raw factors still retain their evidence in the pipeline.
    """
    target = date.fromisoformat(target_date)
    boundary = _timestamp(as_of)
    if target > boundary.astimezone(TAIPEI).date():
        raise ValueError("target date is after as-of in Asia/Taipei")
    # Canonical Taipei time avoids equivalent offsets producing different hashes
    # and keeps the factor adapter's date boundary on the Taiwan market date.
    canonical_as_of = boundary.astimezone(TAIPEI).isoformat()
    rows = reader.load_score_observations(
        dataset_ids=DATASETS, target_date=target.isoformat(), as_of=canonical_as_of
    )
    eligible = [
        row
        for row in rows
        if row.observation_date <= target.isoformat()
        and _timestamp(row.retrieved_at) <= boundary
        and _timestamp(row.ingested_at) <= boundary
        and (row.published_at is None or _timestamp(row.published_at) <= boundary)
    ]
    grouped = {
        dataset: [row for row in eligible if row.dataset_id == dataset]
        for dataset in DATASETS
    }
    result = calculate_daily_score(
        taiex_observations=grouped[TAIEX_DATASET_ID],
        pcr_observations=grouped[PCR_DATASET_ID],
        tx_observations=grouped[TX_DATASET_ID],
        vix_observations=grouped[VIX_DATASET_ID],
        institutional_observations=grouped[INSTITUTIONAL_FUTURES_DATASET_ID],
        target_date=target,
        as_of=canonical_as_of,
    )
    record, outcome = persist_market_score(writer, result)
    return {
        "target_date": record.target_date,
        "as_of": record.as_of,
        "status": record.status,
        "score": record.score,
        "calculation_hash": record.calculation_hash,
        "action": outcome.action,
        "score_id": outcome.score_id,
        "missing_factor_ids": list(result.market_score.missing_factor_ids),
        "factor_scores": record.factor_scores,
        "observation_count": len(eligible),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target-date", required=True, help="Taiwan date YYYY-MM-DD")
    parser.add_argument("--as-of", required=True, help="ISO timestamp with timezone")
    args = parser.parse_args(argv)
    # Validate before connecting; never print remote errors, URLs or credentials.
    try:
        date.fromisoformat(args.target_date)
        _timestamp(args.as_of)
        url = os.environ["SUPABASE_URL"]
        key = os.environ["SUPABASE_SECRET_KEY"]
        with SupabaseRestObservationStore(url, key) as store:
            store.verify_table("market_scores")
            summary = run_daily_score(
                store, store, target_date=args.target_date, as_of=args.as_of
            )
    except Exception:  # noqa: BLE001 - CLI boundary must redact transport errors
        print(
            "Daily score failed. Check dates, server configuration, table access "
            "and observation timestamp validity; no result is confirmed.",
            file=sys.stderr,
        )
        return 1
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
