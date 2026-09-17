"""Initialize and smoke-test the Supabase Data API observation endpoint."""

from __future__ import annotations

import os
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from src.data import SupabaseRestObservationStore  # noqa: E402


def main() -> None:
    project_url = os.environ.get("SUPABASE_URL")
    secret_key = os.environ.get("SUPABASE_SECRET_KEY")
    if not project_url or not secret_key:
        raise SystemExit("SUPABASE_URL and SUPABASE_SECRET_KEY are required")

    with SupabaseRestObservationStore(project_url, secret_key):
        print("Supabase Data API connection succeeded and observations is exposed.")


if __name__ == "__main__":
    main()
