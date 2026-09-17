"""Check the PostgreSQL connection without printing the connection string."""

from __future__ import annotations

import os


def main() -> None:
    dsn = os.environ.get("MARKET_DB_URL")
    if not dsn:
        raise SystemExit("MARKET_DB_URL is required")

    try:
        import psycopg

        with psycopg.connect(dsn, prepare_threshold=None) as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                if cursor.fetchone()[0] != 1:
                    raise RuntimeError("database health check returned an unexpected value")
    except Exception as exc:
        raise SystemExit(
            f"PostgreSQL connection failed before schema initialization: {type(exc).__name__}"
        ) from None

    print("PostgreSQL connection succeeded.")


if __name__ == "__main__":
    main()
