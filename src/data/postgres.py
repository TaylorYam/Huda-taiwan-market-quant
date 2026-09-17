"""Optional PostgreSQL adapter for the free-tier MVP persistence boundary.

The adapter is deliberately separate from the SQLite implementation so local
development does not require a database account or a running PostgreSQL server.
It uses the same :class:`Observation` contract and revision rules as SQLite.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any, Self

from .storage import (
    Observation,
    WriteResult,
    _observation_from_row,
    _parse_timestamp,
    _utc_now,
    _validate_observation,
    base_identity_fields,
)

POSTGRES_SCHEMA_PATH = (
    Path(__file__).parents[2]
    / "supabase"
    / "migrations"
    / "20260917000100_observations.sql"
)


def _postgres_schema_sql() -> str:
    return POSTGRES_SCHEMA_PATH.read_text(encoding="utf-8")


def _connect(dsn: str) -> Any:
    try:
        import psycopg
        from psycopg.rows import dict_row
    except ImportError as exc:  # pragma: no cover - depends on optional runtime setup
        raise RuntimeError(
            "PostgreSQL support requires the psycopg[binary] dependency"
        ) from exc
    return psycopg.connect(dsn, row_factory=dict_row)


class PostgresObservationStore:
    """Transactional PostgreSQL adapter for Supabase or another PostgreSQL host."""

    def __init__(
        self,
        dsn: str,
        *,
        connection_factory: Callable[[str], Any] | None = None,
    ) -> None:
        self._connection = (connection_factory or _connect)(dsn)
        self.initialize()

    def initialize(self) -> None:
        """Create the observation schema; safe to call repeatedly."""
        try:
            with self._connection.cursor() as cursor:
                cursor.execute(_postgres_schema_sql())
            self._connection.commit()
        except Exception:
            self._connection.rollback()
            raise

    def close(self) -> None:
        self._connection.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> None:
        self.close()

    def write_observation(self, observation: Observation) -> WriteResult:
        _validate_observation(observation)
        values_json = json.dumps(
            observation.values,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        now = _utc_now()
        identity = (
            observation.dataset_id,
            observation.observation_date,
            observation.source_record_key,
            observation.publication_label,
            observation.source_revision,
            observation.source_payload_hash,
        )
        base_identity = identity[:4]

        try:
            with self._connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT id, retrieval_count, last_retrieved_at
                    FROM observations
                    WHERE dataset_id = %s
                      AND observation_date = %s
                      AND source_record_key = %s
                      AND COALESCE(publication_label, '') = COALESCE(%s, '')
                      AND COALESCE(source_revision, '') = COALESCE(%s, '')
                      AND source_payload_hash = %s
                    """,
                    identity,
                )
                existing = cursor.fetchone()
                if existing is not None:
                    previous_retrieved_at = existing["last_retrieved_at"]
                    latest_retrieved_at = (
                        observation.retrieved_at
                        if _parse_timestamp(observation.retrieved_at, "retrieved_at")
                        > _parse_timestamp(previous_retrieved_at, "last_retrieved_at")
                        else previous_retrieved_at
                    )
                    cursor.execute(
                        """
                        UPDATE observations
                        SET last_retrieved_at = %s, retrieval_count = %s
                        WHERE id = %s
                        """,
                        (
                            latest_retrieved_at,
                            existing["retrieval_count"] + 1,
                            existing["id"],
                        ),
                    )
                    self._connection.commit()
                    return WriteResult(existing["id"], "duplicate")

                cursor.execute(
                    """
                    SELECT id
                    FROM observations
                    WHERE dataset_id = %s
                      AND observation_date = %s
                      AND source_record_key = %s
                      AND COALESCE(publication_label, '') = COALESCE(%s, '')
                    ORDER BY id DESC
                    LIMIT 1
                    """,
                    base_identity,
                )
                prior = cursor.fetchone()
                if prior is not None and observation.supersedes_id is None:
                    raise ValueError(
                        "a new payload for an existing observation identity requires supersedes_id"
                    )

                supersedes_id = observation.supersedes_id
                if supersedes_id is not None:
                    cursor.execute(
                        """
                        SELECT dataset_id, observation_date, source_record_key,
                               publication_label, source_revision
                        FROM observations
                        WHERE id = %s
                        """,
                        (supersedes_id,),
                    )
                    prior = cursor.fetchone()
                    if prior is None:
                        raise ValueError(
                            "supersedes_id does not reference an observation"
                        )
                    if (
                        tuple(prior[field] for field in base_identity_fields())
                        != base_identity
                    ):
                        raise ValueError(
                            "supersedes_id must reference the same observation identity"
                        )

                cursor.execute(
                    """
                    INSERT INTO observations (
                        dataset_id, schema_version, observation_date, source_date,
                        source_name, source_url, source_record_key, published_at,
                        publication_label, effective_at, retrieved_at, last_retrieved_at,
                        ingested_at, source_revision, supersedes_id, source_payload_hash,
                        parser_version, values_json, quality_status, quality_notes,
                        created_at
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                    )
                    RETURNING id
                    """,
                    (
                        observation.dataset_id,
                        observation.schema_version,
                        observation.observation_date,
                        observation.source_date,
                        observation.source_name,
                        observation.source_url,
                        observation.source_record_key,
                        observation.published_at,
                        observation.publication_label,
                        observation.effective_at,
                        observation.retrieved_at,
                        observation.retrieved_at,
                        observation.ingested_at,
                        observation.source_revision,
                        supersedes_id,
                        observation.source_payload_hash,
                        observation.parser_version,
                        values_json,
                        observation.quality_status,
                        observation.quality_notes,
                        now,
                    ),
                )
                result = cursor.fetchone()
            self._connection.commit()
        except Exception:
            self._connection.rollback()
            raise
        return WriteResult(result["id"], "inserted")

    def get_observation(self, observation_id: int) -> Observation | None:
        with self._connection.cursor() as cursor:
            cursor.execute(
                "SELECT * FROM observations WHERE id = %s", (observation_id,)
            )
            row = cursor.fetchone()
        return None if row is None else _observation_from_row(row)

    def list_revisions(self, observation: Observation) -> list[Observation]:
        """Return all source revisions sharing an observation's base identity."""
        _validate_observation(observation)
        with self._connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT * FROM observations
                WHERE dataset_id = %s
                  AND observation_date = %s
                  AND source_record_key = %s
                  AND COALESCE(publication_label, '') = COALESCE(%s, '')
                ORDER BY id
                """,
                (
                    observation.dataset_id,
                    observation.observation_date,
                    observation.source_record_key,
                    observation.publication_label,
                ),
            )
            rows = cursor.fetchall()
        return [_observation_from_row(row) for row in rows]


__all__ = ["POSTGRES_SCHEMA_PATH", "PostgresObservationStore"]
