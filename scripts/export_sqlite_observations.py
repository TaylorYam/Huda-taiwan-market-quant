"""Export the local SQLite observation store for a controlled migration."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from datetime import datetime, timezone
from pathlib import Path

from src.data.storage import SQLiteObservationStore


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Export SQLite observations as JSON. Keep the output outside the "
            "repository and any public artifact location."
        )
    )
    parser.add_argument("--database", type=Path, default=Path("data/market.sqlite3"))
    parser.add_argument(
        "--output", type=Path, required=True, help="Destination JSON file."
    )
    parser.add_argument(
        "--dataset-id", action="append", dest="dataset_ids", default=None
    )
    parser.add_argument("--start", dest="start_date")
    parser.add_argument("--end", dest="end_date")
    parser.add_argument("--limit", type=int, default=100_000)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        with SQLiteObservationStore(args.database) as store:
            observations = store.export_observations(
                dataset_ids=args.dataset_ids,
                start_date=args.start_date,
                end_date=args.end_date,
                limit=args.limit,
            )
        payload = {
            "format_version": "0.1",
            "source_store": "sqlite",
            "exported_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "observation_count": len(observations),
            "observations": observations,
        }
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    except (OSError, TypeError, ValueError) as exc:
        print(f"SQLite observation export failed: {exc}")
        return 1
    print(f"Exported {len(observations)} observations to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
