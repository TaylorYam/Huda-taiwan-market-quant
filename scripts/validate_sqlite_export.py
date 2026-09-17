"""Validate a SQLite observation export before a controlled migration."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from src.data.migration import validate_observation_export


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate SQLite observation export structure and lineage."
    )
    parser.add_argument("input", type=Path, help="JSON export to validate.")
    parser.add_argument(
        "--allow-external-parents",
        action="store_true",
        help="Allow supersedes_id parents outside a filtered export.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        payload = json.loads(args.input.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise TypeError("export root must be an object")
        records = validate_observation_export(
            payload, allow_external_parents=args.allow_external_parents
        )
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        print(f"SQLite observation export validation failed: {exc}")
        return 1
    print(f"Validated {len(records)} observations from {args.input}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
