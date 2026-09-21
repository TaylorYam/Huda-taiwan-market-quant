"""Validate a TOUCHANCE/MultiCharts text export without database writes."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from src.data.touchance_export import (
    TouchanceExportError,
    parse_touchance_oi_export,
    parse_touchance_vix_export,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate a TOUCHANCE export without writing to Supabase."
    )
    parser.add_argument("--kind", choices=("oi", "vix"), required=True)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        report = (
            parse_touchance_oi_export(args.input)
            if args.kind == "oi"
            else parse_touchance_vix_export(args.input)
        )
        payload = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(payload, encoding="utf-8")
        print(
            f"TOUCHANCE export: kind={report['kind']} rows={report['row_count']} "
            f"dates={report['earliest_date']}..{report['latest_date']} "
            f"duplicates={len(report['duplicate_dates'])}"
        )
        return 0
    except (OSError, TouchanceExportError) as exc:
        print(f"TOUCHANCE export validation failed: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
