"""Server-side Data API reads dedicated to the dashboard."""

import re
from typing import Any

from src.data.supabase_rest import SupabaseRestObservationStore


class DashboardDataStore(SupabaseRestObservationStore):
    """Reuse the server transport; dashboard call sites issue GET requests only."""

    def get_latest_market_score(self) -> dict[str, Any] | None:
        """Read the newest target and persisted revision, including unavailable.

        Never fall back to an older available score: that would hide a newer
        failed calculation. Creation time breaks ties within a target date.
        """
        rows = self._request(
            "GET",
            "/market_scores",
            params={
                "select": "*",
                "order": "target_date.desc,created_at.desc,id.desc",
                "limit": "1",
            },
        )
        return rows[0] if rows else None

    def get_latest_source_quality(self, dataset_id: str) -> dict[str, Any] | None:
        """Read the most recently retrieved record for one source dataset.

        This is a source heartbeat, not a claim about all records or the exact
        evidence of a persisted score. Failed attempts may have no stored row.
        """
        if re.fullmatch(r"[A-Za-z0-9_.-]+", dataset_id) is None:
            raise ValueError("dataset_id contains an invalid identifier")
        rows = self._request(
            "GET",
            "/observations",
            params={
                "select": (
                    "dataset_id,source_name,observation_date,source_record_key,"
                    "quality_status,quality_notes,last_retrieved_at"
                ),
                "dataset_id": f"eq.{dataset_id}",
                "order": "last_retrieved_at.desc,id.desc",
                "limit": "1",
            },
        )
        return rows[0] if rows else None
