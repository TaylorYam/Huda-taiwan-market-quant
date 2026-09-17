"""Audit TAIFEX annual TX ZIP archives without writing market data."""

from __future__ import annotations

import argparse
import json
import time
from collections.abc import Sequence
from datetime import datetime, timezone
from pathlib import Path

import requests

from src.data import TX_ARCHIVE_ENDPOINT, audit_tx_archives, build_archive_form


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Audit TAIFEX annual TX ZIP archives and write JSON evidence."
    )
    parser.add_argument("--start-year", type=int, default=1998)
    parser.add_argument("--end-year", type=int, default=2025)
    parser.add_argument("--output", type=Path, default=Path("tx-archive-audit.json"))
    parser.add_argument("--sleep-seconds", type=float, default=0.2)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.sleep_seconds < 0:
            raise ValueError("--sleep-seconds must not be negative")
        with requests.Session() as session:
            session.headers.update({"User-Agent": "HudaTaiwanQuant/0.1"})

            def fetch(year: int) -> bytes:
                response = session.post(
                    TX_ARCHIVE_ENDPOINT,
                    data=build_archive_form(year),
                    timeout=60,
                )
                response.raise_for_status()
                if args.sleep_seconds:
                    time.sleep(args.sleep_seconds)
                return response.content

            report = audit_tx_archives(args.start_year, args.end_year, fetch)
        report["audit_finished_at"] = datetime.now(timezone.utc).isoformat(
            timespec="seconds"
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(
            "TX archive audit: "
            f"years={report['planned_year_count']} "
            f"completed={report['completed_year_count']} "
            f"errors={report['error_year_count']}"
        )
        return 0 if not report["errors"] else 1
    except (OSError, ValueError, requests.RequestException) as exc:
        print(f"TX archive audit failed: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
