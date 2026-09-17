"""Build a TAIFEX daily data-quality report from probe/collector evidence."""

from __future__ import annotations

import argparse
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from src.data.taifex_quality import build_taifex_quality_report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Write a daily TAIFEX coverage/reconciliation report. "
            "Input dates must come from a probe or collector."
        )
    )
    parser.add_argument(
        "--input",
        type=Path,
        required=True,
        help="JSON evidence with a datasets mapping and daily records.",
    )
    parser.add_argument(
        "--output", type=Path, default=Path("taifex-quality-report.json")
    )
    parser.add_argument("--start", help="Requested boundary, YYYY-MM-DD")
    parser.add_argument("--end", help="Requested boundary, YYYY-MM-DD")
    parser.add_argument(
        "--calendar",
        type=Path,
        help="Optional JSON list/object of official trading dates.",
    )
    parser.add_argument(
        "--calendar-source",
        help="Official calendar URL or evidence identifier when supplied.",
    )
    return parser


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _calendar_dates(path: Path | None) -> list[str] | None:
    if path is None:
        return None
    payload = _read_json(path)
    if isinstance(payload, list):
        return payload
    if isinstance(payload, Mapping):
        dates = payload.get("dates", payload.get("expected_dates"))
        if not isinstance(dates, list):
            raise TypeError("calendar JSON must contain a dates list")
        return dates
    raise TypeError("calendar JSON must be a list or an object containing dates")


def _datasets(payload: Any) -> Mapping[str, Any]:
    if isinstance(payload, Mapping) and isinstance(payload.get("datasets"), Mapping):
        return payload["datasets"]
    if isinstance(payload, Mapping):
        return payload
    raise ValueError("input JSON must contain a datasets mapping")


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if (args.start is None) != (args.end is None):
            raise ValueError("--start and --end must be provided together")
        expected_dates = _calendar_dates(args.calendar)
        report = build_taifex_quality_report(
            _datasets(_read_json(args.input)),
            requested_start=args.start,
            requested_end=args.end,
            expected_dates=expected_dates,
            calendar_status="available" if expected_dates is not None else "unknown",
            calendar_source=args.calendar_source,
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(
            f"TAIFEX quality gate: status={report['gate_status']} "
            f"datasets={len(report['datasets'])} "
            f"calendar={report['calendar_boundary']['status']}"
        )
        return 0 if report["gate_status"] == "pass" else 1
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        print(f"TAIFEX quality report failed: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
