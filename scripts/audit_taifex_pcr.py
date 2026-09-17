"""Audit the full daily TAIFEX PCR history without writing market data."""

from __future__ import annotations

import argparse
import json
import time
from collections.abc import Sequence
from datetime import date, datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

from src.data import PCR_ENDPOINT, audit_pcr_range
from src.data.taifex_pcr_probe import PCRWindow

TAIWAN_TIMEZONE = ZoneInfo("Asia/Taipei")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Audit TAIFEX PCR windows and write a JSON evidence report."
    )
    parser.add_argument("--start", default="2001-12-24", help="First date, YYYY-MM-DD")
    parser.add_argument(
        "--end",
        default=None,
        help="Last date, YYYY-MM-DD; defaults to today's Taiwan date",
    )
    parser.add_argument("--output", type=Path, default=Path("pcr-window-audit.json"))
    parser.add_argument("--sleep-seconds", type=float, default=0.2)
    return parser


def _parse_date(value: str, field_name: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{field_name} must use YYYY-MM-DD") from exc


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        start = _parse_date(args.start, "--start")
        end = _parse_date(
            args.end or datetime.now(TAIWAN_TIMEZONE).date().isoformat(), "--end"
        )
        if args.sleep_seconds < 0:
            raise ValueError("--sleep-seconds must not be negative")

        with requests.Session() as session:
            session.headers.update({"User-Agent": "HudaTaiwanQuant/0.1"})

            def fetch(window: PCRWindow) -> bytes:
                response = session.post(
                    PCR_ENDPOINT,
                    data=window.form_values(),
                    timeout=30,
                )
                response.raise_for_status()
                if args.sleep_seconds:
                    time.sleep(args.sleep_seconds)
                return response.content

            report = audit_pcr_range(start, end, fetch)
        report["audit_finished_at"] = datetime.now(timezone.utc).isoformat(
            timespec="seconds"
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(
            "PCR audit: "
            f"windows={report['planned_window_count']} "
            f"rows={report['total_rows']} "
            f"unique_dates={report['unique_dates']} "
            f"errors={report['error_window_count']} "
            f"duplicates={len(report['duplicate_dates'])}"
        )
        return 0 if not report["errors"] and not report["duplicate_dates"] else 1
    except (OSError, ValueError, requests.RequestException) as exc:
        print(f"PCR audit failed: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
