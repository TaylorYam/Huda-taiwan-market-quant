"""Supabase Data API adapter for the free-tier MVP.

This adapter keeps the MVP independent from a database password. It calls the
PostgREST endpoint with a server-only Supabase secret key. The schema must be
created once with the SQL migration in ``supabase/migrations/20260917000100_observations.sql``.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
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


@dataclass(frozen=True)
class MarketScoreWriteResult:
    """Outcome of writing a derived Market Score row."""

    score_id: int
    action: str


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
                "Authorization": f"Bearer {secret_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            }
        )
        self._timeout = timeout
        self.initialize()

    def initialize(self) -> None:
        """Verify that the observations table is exposed by the Data API."""
        self.verify_table("observations")

    def verify_table(self, table_name: str) -> None:
        """Verify that a public table is exposed without returning rows."""

        if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", table_name) is None:
            raise ValueError("table_name must be a simple public table name")
        self._request(
            "GET",
            f"/{table_name}",
            params={"select": "id", "limit": "0"},
        )

    def list_observations(
        self,
        *,
        dataset_ids: Sequence[str] | None = None,
        limit: int = 5000,
    ) -> list[Observation]:
        """Load source observations for a point-in-time factor calculation."""

        if limit < 1 or limit > 10_000:
            raise ValueError("limit must be between 1 and 10000")
        params: dict[str, Any] = {
            "select": "*",
            "order": "observation_date.asc,id.asc",
            "limit": str(limit),
        }
        if dataset_ids:
            names = [
                dataset_id
                for dataset_id in dataset_ids
                if re.fullmatch(r"[A-Za-z0-9_.-]+", dataset_id)
            ]
            if len(names) != len(dataset_ids):
                raise ValueError("dataset_ids contain an invalid identifier")
            params["dataset_id"] = f"in.({','.join(names)})"
        rows = self._request("GET", "/observations", params=params)
        return [_observation_from_row(row) for row in rows]

    def load_score_observations(
        self, *, dataset_ids: Sequence[str], target_date: str, as_of: str
    ) -> list[Observation]:
        """Read every eligible row, even when the API caps each response.

        Keyset pagination terminates only on an empty page, not a short page.
        The ingestion boundary prevents later backfills entering a replay.
        """
        from datetime import date

        date.fromisoformat(target_date)
        _parse_timestamp(as_of, "as_of")
        if not dataset_ids or any(
            re.fullmatch(r"[A-Za-z0-9_.-]+", name) is None for name in dataset_ids
        ):
            raise ValueError("dataset_ids must contain valid identifiers")
        result: list[Observation] = []
        cursor = 0
        while True:
            rows = self._request(
                "GET",
                "/observations",
                params={
                    "select": "*",
                    "dataset_id": f"in.({','.join(dataset_ids)})",
                    "observation_date": f"lte.{target_date}",
                    "ingested_at": f"lte.{as_of}",
                    "retrieved_at": f"lte.{as_of}",
                    "id": f"gt.{cursor}",
                    "order": "id.asc",
                    "limit": "1000",
                },
            )
            if not rows:
                return result
            ids = [int(row["id"]) for row in rows]
            if ids != sorted(set(ids)) or ids[0] <= cursor:
                raise RuntimeError("Observation pagination did not advance")
            result.extend(_observation_from_row(row) for row in rows)
            cursor = ids[-1]

    def load_backtest_observations(
        self, *, dataset_ids: Sequence[str], start_date: str, end_date: str
    ) -> list[Observation]:
        """Read every observation in a date range for an offline backtest replay.

        Unlike :meth:`load_score_observations`, this does not gate on
        ``ingested_at``, ``retrieved_at`` or ``published_at``: those record
        when a collector actually saw the data, which for bulk-backfilled
        history all reads as "whenever the backfill ran" and would hide
        every historical row from a knowledge-boundary check that only makes
        sense for a live run. A backtest replay's point-in-time guarantee
        comes from ``observation_date`` alone, enforced downstream by the
        factor adapters (see ``src/backtest/layer1.py``).
        """

        date.fromisoformat(start_date)
        date.fromisoformat(end_date)
        if start_date > end_date:
            raise ValueError("start_date must not be after end_date")
        if not dataset_ids or any(
            re.fullmatch(r"[A-Za-z0-9_.-]+", name) is None for name in dataset_ids
        ):
            raise ValueError("dataset_ids must contain valid identifiers")
        result: list[Observation] = []
        cursor = 0
        while True:
            rows = self._request(
                "GET",
                "/observations",
                params={
                    "select": "*",
                    "dataset_id": f"in.({','.join(dataset_ids)})",
                    "observation_date": [f"gte.{start_date}", f"lte.{end_date}"],
                    "id": f"gt.{cursor}",
                    "order": "id.asc",
                    "limit": "1000",
                },
            )
            if not rows:
                return result
            ids = [int(row["id"]) for row in rows]
            if ids != sorted(set(ids)) or ids[0] <= cursor:
                raise RuntimeError("Observation pagination did not advance")
            result.extend(_observation_from_row(row) for row in rows)
            cursor = ids[-1]

    def list_market_scores(
        self,
        *,
        model_version: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        limit: int = 5000,
    ) -> list[dict[str, Any]]:
        """List persisted score identities for an idempotent history replay.

        The backfill writer uses this metadata-only read to preserve any
        existing result for a target date.  In particular, a historical
        replay must never create a second row that hides a live score in the
        dashboard just because the replay has a different calculation hash.
        """

        if not 1 <= limit <= 10_000:
            raise ValueError("limit must be between 1 and 10000")
        if start_date is not None:
            date.fromisoformat(start_date)
        if end_date is not None:
            date.fromisoformat(end_date)
        if start_date is not None and end_date is not None and start_date > end_date:
            raise ValueError("start_date must not be after end_date")
        params: dict[str, Any] = {
            "select": "id,model_version,target_date,status,calculation_hash",
            "order": "target_date.asc,id.asc",
            "limit": str(limit),
        }
        if model_version is not None:
            if not model_version.strip():
                raise ValueError("model_version must not be empty")
            params["model_version"] = f"eq.{model_version}"
        if start_date is not None:
            params["target_date"] = [f"gte.{start_date}"]
        if end_date is not None:
            existing = params.get("target_date", [])
            params["target_date"] = [*existing, f"lte.{end_date}"]
        return self._request("GET", "/market_scores", params=params)

    def write_market_score(self, record: Mapping[str, Any]) -> MarketScoreWriteResult:
        """Insert one derived result or return duplicate for the same hash."""

        required = {
            "model_version",
            "target_date",
            "status",
            "calculation_hash",
            "factor_scores_json",
            "observation_identities_json",
        }
        missing = sorted(field for field in required if field not in record)
        if missing:
            raise ValueError(
                f"market score record missing fields: {', '.join(missing)}"
            )
        identity_params = {
            "model_version": f"eq.{record['model_version']}",
            "target_date": f"eq.{record['target_date']}",
            "calculation_hash": f"eq.{record['calculation_hash']}",
            "select": "id",
            "limit": "1",
        }
        existing = self._request("GET", "/market_scores", params=identity_params)
        if existing:
            return MarketScoreWriteResult(int(existing[0]["id"]), "duplicate")

        payload = {
            "model_version": record["model_version"],
            "target_date": record["target_date"],
            "as_of": record.get("as_of"),
            "status": record["status"],
            "score": record.get("score"),
            "direction": record.get("direction"),
            "reason": record.get("reason"),
            "calculation_hash": record["calculation_hash"],
            "factor_scores_json": record["factor_scores_json"],
            "observation_identities_json": record["observation_identities_json"],
        }
        inserted = self._request(
            "POST",
            "/market_scores",
            json_body=payload,
            prefer="return=representation",
        )
        if not inserted:
            raise RuntimeError("Supabase did not return the inserted market score")
        return MarketScoreWriteResult(int(inserted[0]["id"]), "inserted")

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

        base_identity = {key: identity[key] for key in base_identity_fields()}
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

        payload = self._observation_payload(observation, supersedes_id=supersedes_id)
        inserted = self._request(
            "POST",
            "/observations",
            json_body=payload,
            prefer="return=representation",
        )
        if not inserted:
            raise RuntimeError("Supabase did not return the inserted observation")
        return WriteResult(inserted[0]["id"], "inserted")

    def write_observations(
        self, observations: Sequence[Observation]
    ) -> list[WriteResult]:
        """Write a range with one read and one bulk insert instead of one request per row.

        Range backfills contain hundreds of independent daily rows.  The normal
        single-row contract remains the source of truth for live ingestion, but
        a bulk path keeps a one-time historical backfill within normal API and
        runner limits while preserving exact-payload deduplication.
        """

        if not observations:
            return []
        for observation in observations:
            _validate_observation(observation)

        datasets = sorted({observation.dataset_id for observation in observations})
        start = min(observation.observation_date for observation in observations)
        end = max(observation.observation_date for observation in observations)
        existing: list[dict[str, Any]] = []
        for dataset_id in datasets:
            existing.extend(
                self._request(
                    "GET",
                    "/observations",
                    params={
                        "select": (
                            "id,dataset_id,observation_date,source_record_key,"
                            "publication_label,source_revision,source_payload_hash,"
                            "retrieval_count,last_retrieved_at"
                        ),
                        "dataset_id": f"eq.{dataset_id}",
                        "observation_date": [f"gte.{start}", f"lte.{end}"],
                        "limit": "1000",
                    },
                )
            )

        exact: dict[tuple[str, str, str, str, str, str], dict[str, Any]] = {}
        latest_by_base: dict[tuple[str, str, str, str, str], dict[str, Any]] = {}
        for row in existing:
            exact[self._observation_identity_key(row)] = row
            base = self._observation_base_key(row)
            prior = latest_by_base.get(base)
            if prior is None or int(row["id"]) > int(prior["id"]):
                latest_by_base[base] = row

        results: list[WriteResult | None] = [None] * len(observations)
        pending: list[
            tuple[int, tuple[str, str, str, str, str, str], dict[str, Any]]
        ] = []
        for index, observation in enumerate(observations):
            key = self._observation_identity_key(observation)
            duplicate = exact.get(key)
            if duplicate is not None:
                latest_retrieved_at = (
                    observation.retrieved_at
                    if _parse_timestamp(observation.retrieved_at, "retrieved_at")
                    > _parse_timestamp(
                        duplicate["last_retrieved_at"], "last_retrieved_at"
                    )
                    else duplicate["last_retrieved_at"]
                )
                self._request(
                    "PATCH",
                    "/observations",
                    params={"id": f"eq.{duplicate['id']}"},
                    json_body={
                        "last_retrieved_at": latest_retrieved_at,
                        "retrieval_count": int(duplicate["retrieval_count"]) + 1,
                    },
                    prefer="return=minimal",
                )
                results[index] = WriteResult(int(duplicate["id"]), "duplicate")
                continue

            base = self._observation_base_key(observation)
            previous = latest_by_base.get(base)
            supersedes_id = observation.supersedes_id
            if previous is not None and supersedes_id is None:
                supersedes_id = int(previous["id"])
            payload = self._observation_payload(
                observation, supersedes_id=supersedes_id
            )
            pending.append((index, key, payload))

        for offset in range(0, len(pending), 500):
            chunk = pending[offset : offset + 500]
            inserted = self._request(
                "POST",
                "/observations",
                json_body=[payload for _, _, payload in chunk],
                prefer="return=representation",
            )
            if len(inserted) != len(chunk):
                raise RuntimeError(
                    "Supabase did not return every bulk-inserted observation"
                )
            inserted_by_key = {
                self._observation_identity_key(row): row for row in inserted
            }
            for index, key, _ in chunk:
                row = inserted_by_key.get(key)
                if row is None:
                    raise RuntimeError(
                        "Supabase bulk response omitted an inserted observation"
                    )
                results[index] = WriteResult(int(row["id"]), "inserted")

        return [result for result in results if result is not None]

    @staticmethod
    def _observation_identity_key(
        value: Mapping[str, Any] | Observation,
    ) -> tuple[str, str, str, str, str, str]:
        def field(name: str) -> str:
            raw = value[name] if isinstance(value, Mapping) else getattr(value, name)
            return "" if raw is None else str(raw)

        return (
            field("dataset_id"),
            field("observation_date"),
            field("source_record_key"),
            field("publication_label"),
            field("source_revision"),
            field("source_payload_hash"),
        )

    @staticmethod
    def _observation_base_key(
        value: Mapping[str, Any] | Observation,
    ) -> tuple[str, str, str, str, str]:
        key = SupabaseRestObservationStore._observation_identity_key(value)
        return key[:-1]

    @staticmethod
    def _observation_payload(
        observation: Observation, *, supersedes_id: int | None
    ) -> dict[str, Any]:
        return {
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
        json_body: Any = None,
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


__all__ = ["MarketScoreWriteResult", "SupabaseRestObservationStore"]
