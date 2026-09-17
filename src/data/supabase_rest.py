"""Supabase Data API adapter for the free-tier MVP.

This adapter keeps the MVP independent from a database password. It calls the
PostgREST endpoint with a server-only Supabase secret key. The schema must be
created once with the SQL migration in ``src/data/sql/001_observations.sql``.
"""

from __future__ import annotations

from typing import Any, Self

import requests

from .storage import (
    Observation,
    WriteResult,
    _observation_from_row,
    _parse_timestamp,
    _utc_now,
    _validate_observation,
    base_identity_fields,
)


class SupabaseRestObservationStore:
    """Observation store backed by Supabase's REST Data API."""

    def __init__(
        self,
        project_url: str,
        secret_key: str,
        *,
        session: requests.Session | None = None,
        timeout: float = 30.0,
    ) -> None:
        if not project_url.strip():
            raise ValueError("project_url must not be empty")
        if not secret_key.strip():
            raise ValueError("secret_key must not be empty")
        self._base_url = project_url.rstrip("/") + "/rest/v1"
        self._session = session or requests.Session()
        self._session.headers.update(
            {
                "apikey": secret_key,
                "Content-Type": "application/json",
                "Accept": "application/json",
            }
        )
        self._timeout = timeout
        self.initialize()

    def initialize(self) -> None:
        """Verify that the observations table is exposed by the Data API."""
        self._request(
            "GET",
            "/observations",
            params={"select": "id", "limit": "0"},
        )

    def close(self) -> None:
        self._session.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> None:
        self.close()

    def write_observation(self, observation: Observation) -> WriteResult:
        _validate_observation(observation)
        identity = {
            "dataset_id": observation.dataset_id,
            "observation_date": observation.observation_date,
            "source_record_key": observation.source_record_key,
            "publication_label": observation.publication_label,
            "source_revision": observation.source_revision,
            "source_payload_hash": observation.source_payload_hash,
        }
        rows = self._select(identity, "id,retrieval_count,last_retrieved_at")
        if rows:
            existing = rows[0]
            previous_retrieved_at = existing["last_retrieved_at"]
            latest_retrieved_at = (
                observation.retrieved_at
                if _parse_timestamp(observation.retrieved_at, "retrieved_at")
                > _parse_timestamp(previous_retrieved_at, "last_retrieved_at")
                else previous_retrieved_at
            )
            self._request(
                "PATCH",
                "/observations",
                params={"id": f"eq.{existing['id']}"},
                json_body={
                    "last_retrieved_at": latest_retrieved_at,
                    "retrieval_count": existing["retrieval_count"] + 1,
                },
                prefer="return=minimal",
            )
            return WriteResult(existing["id"], "duplicate")

        base_identity = {
            key: identity[key]
            for key in base_identity_fields()
        }
        prior_rows = self._select(base_identity, "id")
        if prior_rows and observation.supersedes_id is None:
            raise ValueError(
                "a new payload for an existing observation identity requires "
                "supersedes_id"
            )

        supersedes_id = observation.supersedes_id
        if supersedes_id is not None:
            prior = self._select(
                {"id": supersedes_id}, ",".join(base_identity_fields())
            )
            if not prior:
                raise ValueError("supersedes_id does not reference an observation")
            if any(
                prior[0][field] != base_identity[field]
                for field in base_identity_fields()
            ):
                raise ValueError(
                    "supersedes_id must reference the same observation identity"
                )

        payload = {
            "dataset_id": observation.dataset_id,
            "schema_version": observation.schema_version,
            "observation_date": observation.observation_date,
            "source_date": observation.source_date,
            "source_name": observation.source_name,
            "source_url": observation.source_url,
            "source_record_key": observation.source_record_key,
            "published_at": observation.published_at,
            "publication_label": observation.publication_label,
            "effective_at": observation.effective_at,
            "retrieved_at": observation.retrieved_at,
            "last_retrieved_at": observation.retrieved_at,
            "ingested_at": observation.ingested_at,
            "source_revision": observation.source_revision,
            "supersedes_id": supersedes_id,
            "source_payload_hash": observation.source_payload_hash,
            "parser_version": observation.parser_version,
            "values_json": dict(observation.values),
            "quality_status": observation.quality_status,
            "quality_notes": observation.quality_notes,
            "retrieval_count": 1,
            "created_at": _utc_now(),
        }
        inserted = self._request(
            "POST",
            "/observations",
            json_body=payload,
            prefer="return=representation",
        )
        if not inserted:
            raise RuntimeError("Supabase did not return the inserted observation")
        return WriteResult(inserted[0]["id"], "inserted")

    def get_observation(self, observation_id: int) -> Observation | None:
        rows = self._select({"id": observation_id}, "*")
        return None if not rows else _observation_from_row(rows[0])

    def list_revisions(self, observation: Observation) -> list[Observation]:
        """Return all source revisions sharing an observation's base identity."""
        _validate_observation(observation)
        rows = self._select(
            {
                "dataset_id": observation.dataset_id,
                "observation_date": observation.observation_date,
                "source_record_key": observation.source_record_key,
                "publication_label": observation.publication_label,
            },
            "*",
        )
        return [_observation_from_row(row) for row in rows]

    def _select(self, filters: dict[str, Any], select: str) -> list[dict[str, Any]]:
        params = {"select": select}
        for key, value in filters.items():
            params[key] = "is.null" if value is None else f"eq.{value}"
        return self._request("GET", "/observations", params=params)

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
        prefer: str | None = None,
    ) -> Any:
        headers = {"Prefer": prefer} if prefer else None
        response = self._session.request(
            method,
            self._base_url + path,
            params=params,
            json=json_body,
            headers=headers,
            timeout=self._timeout,
        )
        if not response.ok:
            detail = response.text[:300].replace("\n", " ")
            raise RuntimeError(
                f"Supabase Data API request failed ({response.status_code}): {detail}"
            )
        if response.status_code == 204 or not response.content:
            return []
        return response.json()


__all__ = ["SupabaseRestObservationStore"]
