"""Server-side Data API reads dedicated to the dashboard."""

import re
from typing import Any

from src.data.supabase_rest import SupabaseRestObservationStore


class DashboardDataStore(SupabaseRestObservationStore):
    """Reuse the server transport; dashboard call sites issue GET requests only."""

    _POSTGREST_PAGE_SIZE = 1000

    @staticmethod
    def _validate_limit(limit: int) -> int:
        if (
            isinstance(limit, bool)
            or not isinstance(limit, int)
            or not 1 <= limit <= 5000
        ):
            raise ValueError("limit must be between 1 and 5000")
        return limit

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

    def get_market_score_history(self, *, limit: int = 365) -> list[dict[str, Any]]:
        """Read persisted score history without recalculating or filling gaps."""

        self._validate_limit(limit)
        return self._read_history_pages(
            "/market_scores",
            {
                "select": (
                    "id,target_date,as_of,status,score,direction,reason,"
                    "factor_scores_json,created_at"
                ),
                "order": "target_date.asc,created_at.asc,id.asc",
            },
            limit,
        )

    def get_observation_history(
        self, dataset_id: str, *, limit: int = 1000
    ) -> list[dict[str, Any]]:
        """Read a source history for charts; this path is strictly GET-only."""

        self._validate_limit(limit)
        if re.fullmatch(r"[A-Za-z0-9_.-]+", dataset_id) is None:
            raise ValueError("dataset_id contains an invalid identifier")
        return self._read_history_pages(
            "/observations",
            {
                "select": (
                    "id,dataset_id,observation_date,source_record_key,"
                    "values_json,quality_status,source_payload_hash,created_at"
                ),
                "dataset_id": f"eq.{dataset_id}",
                "order": "observation_date.asc,created_at.asc,id.asc",
            },
            limit,
        )

    def _read_history_pages(
        self,
        path: str,
        params: dict[str, Any],
        limit: int,
    ) -> list[dict[str, Any]]:
        """Read history past Supabase's default 1,000-row response cap.

        History rows are ordered oldest first so the dashboard's existing
        same-date revision selection keeps the newest persisted revision. The
        explicit offset pages prevent duplicate score revisions from consuming
        the one-page limit and hiding the most recent dates.
        """

        rows: list[dict[str, Any]] = []
        offset = 0
        while len(rows) < limit:
            page_limit = min(self._POSTGREST_PAGE_SIZE, limit - len(rows))
            page = self._request(
                "GET",
                path,
                params={
                    **params,
                    "limit": str(page_limit),
                    "offset": str(offset),
                },
            )
            if not isinstance(page, list):
                raise TypeError("Supabase history response must be a list")
            rows.extend(row for row in page if isinstance(row, dict))
            if len(page) < page_limit:
                break
            offset += len(page)
        return rows[:limit]

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
