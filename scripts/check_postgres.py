"""Initialize and smoke-test the configured PostgreSQL observation store."""

from __future__ import annotations

import os
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from src.data import PostgresObservationStore  # noqa: E402


def main() -> None:
    dsn = os.environ.get("MARKET_DB_URL")
    if not dsn:
        raise SystemExit("MARKET_DB_URL is required")

    with PostgresObservationStore(dsn):
        print("PostgreSQL connection succeeded and observation schema is ready.")


if __name__ == "__main__":
    main()
