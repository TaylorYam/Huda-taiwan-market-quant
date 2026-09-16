"""Storage interface and Phase 1 SQLite implementation.

The SQLite adapter stores the observation envelope from ``docs/data-contract-v0.1.md``.
Parsers and factor code should depend on :class:`ObservationStore`, rather than on
SQLite-specific SQL or connection details.
"""

from __future__ import annotations

import json
import re
import sqlite3
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Protocol, Self

QUALITY_STATUSES = frozenset(
    {
        "available",
        "not_published",
        "source_empty",
        "fetch_failed",
        "parse_failed",
        "invalid",
        "not_applicable",
    }
)
SOURCE_NAMES = frozenset({"TWSE", "TAIFEX"})


@dataclass(frozen=True)
class Observation:
    """A source or normalized observation matching the shared data contract."""

    dataset_id: str
    schema_version: str
    observation_date: str
    source_date: str
    source_name: str
    source_url: str
    source_record_key: str
    retrieved_at: str
    ingested_at: str
    source_payload_hash: str
    parser_version: str
    values: Mapping[str, Any]
    quality_status: str
    published_at: str | None = None
    publication_label: str | None = None
    effective_at: str | None = None
    source_revision: str | None = None
    supersedes_id: int | None = None
    quality_notes: str | None = None


@dataclass(frozen=True)
class WriteResult:
    """Outcome of writing an observation."""

    observation_id: int
    action: str


class ObservationStore(Protocol):
    """Storage boundary used by data collectors and factor pipelines."""

    def initialize(self) -> None:
        """Create or migrate the storage schema."""

    def write_observation(self, observation: Observation) -> WriteResult:
        """Insert, deduplicate, or append a revised observation."""

    def get_observation(self, observation_id: int) -> Observation | None:
        """Return one observation by its database id."""


SCHEMA = """
CREATE TABLE IF NOT EXISTS observations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    dataset_id TEXT NOT NULL,
    schema_version TEXT NOT NULL,
    observation_date TEXT NOT NULL,
    source_date TEXT NOT NULL,
    source_name TEXT NOT NULL,
    source_url TEXT NOT NULL,
    source_record_key TEXT NOT NULL,
    published_at TEXT,
    publication_label TEXT,
    effective_at TEXT,
    retrieved_at TEXT NOT NULL,
    last_retrieved_at TEXT NOT NULL,
    ingested_at TEXT NOT NULL,
    source_revision TEXT,
    supersedes_id INTEGER REFERENCES observations(id),
    source_payload_hash TEXT NOT NULL,
    parser_version TEXT NOT NULL,
    values_json TEXT NOT NULL,
    quality_status TEXT NOT NULL,
    quality_notes TEXT,
    retrieval_count INTEGER NOT NULL DEFAULT 1 CHECK (retrieval_count >= 1),
    created_at TEXT NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS observations_payload_identity
ON observations (
    dataset_id,
    observation_date,
    source_record_key,
    IFNULL(publication_label, ''),
    IFNULL(source_revision, ''),
    source_payload_hash
);

CREATE INDEX IF NOT EXISTS observations_logical_identity
ON observations (
    dataset_id,
    observation_date,
    source_record_key,
    IFNULL(publication_label, ''),
    IFNULL(source_revision, ''),
    id
);
"""


def _validate_date(value: str, field_name: str) -> None:
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{field_name} must be YYYY-MM-DD") from exc
    if parsed.isoformat() != value:
        raise ValueError(f"{field_name} must be YYYY-MM-DD")


def _parse_timestamp(value: str, field_name: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(
            f"{field_name} must be an RFC 3339 timestamp with timezone"
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{field_name} must include a timezone")
    return parsed


def _validate_timestamp(
    value: str, field_name: str, *, require_utc: bool = False
) -> None:
    parsed = _parse_timestamp(value, field_name)
    if require_utc and parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise ValueError(f"{field_name} must use UTC")


def _validate_observation(observation: Observation) -> None:
    required_text = {
        "dataset_id": observation.dataset_id,
        "schema_version": observation.schema_version,
        "source_name": observation.source_name,
        "source_url": observation.source_url,
        "source_record_key": observation.source_record_key,
        "source_payload_hash": observation.source_payload_hash,
        "parser_version": observation.parser_version,
    }
    for field_name, value in required_text.items():
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{field_name} must not be empty")

    _validate_date(observation.observation_date, "observation_date")
    if (
        not isinstance(observation.source_date, str)
        or not observation.source_date.strip()
    ):
        raise ValueError("source_date must preserve a non-empty official source value")
    _validate_timestamp(observation.retrieved_at, "retrieved_at", require_utc=True)
    _validate_timestamp(observation.ingested_at, "ingested_at", require_utc=True)
    if observation.published_at is not None:
        _validate_timestamp(observation.published_at, "published_at")
    if observation.effective_at is not None:
        _validate_timestamp(observation.effective_at, "effective_at")
    if observation.quality_status not in QUALITY_STATUSES:
        allowed = ", ".join(sorted(QUALITY_STATUSES))
        raise ValueError(f"quality_status must be one of: {allowed}")
    if observation.source_name not in SOURCE_NAMES:
        raise ValueError("source_name must be TWSE or TAIFEX")
    if re.fullmatch(r"[0-9a-fA-F]{64}", observation.source_payload_hash) is None:
        raise ValueError(
            "source_payload_hash must be a 64-character SHA-256 hex digest"
        )
    if not isinstance(observation.values, Mapping):
        raise TypeError("values must be a mapping")
    try:
        json.dumps(
            observation.values,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise ValueError("values must be JSON serializable") from exc


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class SQLiteObservationStore:
    """Transactional SQLite adapter for Phase 1 local development."""

    def __init__(self, path: str | Path = "data/market.sqlite3") -> None:
        self.path = Path(path)
        if str(self.path) != ":memory:":
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(self.path)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA foreign_keys = ON")
        self.initialize()

    def initialize(self) -> None:
        """Create the schema; safe to call repeatedly."""
        self._connection.executescript(SCHEMA)
        self._connection.commit()

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
        revision_identity = identity[:-1]
        base_identity = identity[:4]

        with self._connection:
            existing = self._connection.execute(
                """
                SELECT id, retrieval_count, last_retrieved_at
                FROM observations
                WHERE dataset_id = ?
                  AND observation_date = ?
                  AND source_record_key = ?
                  AND IFNULL(publication_label, '') = IFNULL(?, '')
                  AND IFNULL(source_revision, '') = IFNULL(?, '')
                  AND source_payload_hash = ?
                """,
                identity,
            ).fetchone()
            if existing is not None:
                previous_retrieved_at = existing["last_retrieved_at"]
                latest_retrieved_at = (
                    observation.retrieved_at
                    if _parse_timestamp(observation.retrieved_at, "retrieved_at")
                    > _parse_timestamp(previous_retrieved_at, "last_retrieved_at")
                    else previous_retrieved_at
                )
                self._connection.execute(
                    """
                    UPDATE observations
                    SET last_retrieved_at = ?, retrieval_count = ?
                    WHERE id = ?
                    """,
                    (
                        latest_retrieved_at,
                        existing["retrieval_count"] + 1,
                        existing["id"],
                    ),
                )
                return WriteResult(existing["id"], "duplicate")

            supersedes_id = observation.supersedes_id
            prior = self._connection.execute(
                """
                SELECT id
                FROM observations
                WHERE dataset_id = ?
                  AND observation_date = ?
                  AND source_record_key = ?
                  AND IFNULL(publication_label, '') = IFNULL(?, '')
                  AND IFNULL(source_revision, '') = IFNULL(?, '')
                ORDER BY id DESC LIMIT 1
                """,
                revision_identity,
            ).fetchone()
            if prior is not None and supersedes_id is None:
                raise ValueError(
                    "a changed payload for an existing logical identity requires supersedes_id"
                )
            if supersedes_id is not None:
                prior = self._connection.execute(
                    """
                    SELECT dataset_id, observation_date, source_record_key,
                           publication_label, source_revision
                    FROM observations WHERE id = ?
                    """,
                    (supersedes_id,),
                ).fetchone()
                if prior is None:
                    raise ValueError("supersedes_id does not reference an observation")
                if (
                    tuple(prior[field] for field in base_identity_fields())
                    != base_identity
                ):
                    raise ValueError(
                        "supersedes_id must reference the same observation identity"
                    )

            cursor = self._connection.execute(
                """
                INSERT INTO observations (
                    dataset_id, schema_version, observation_date, source_date,
                    source_name, source_url, source_record_key, published_at,
                    publication_label, effective_at, retrieved_at, last_retrieved_at,
                    ingested_at, source_revision, supersedes_id, source_payload_hash,
                    parser_version, values_json, quality_status, quality_notes,
                    created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            return WriteResult(int(cursor.lastrowid), "inserted")

    def get_observation(self, observation_id: int) -> Observation | None:
        row = self._connection.execute(
            "SELECT * FROM observations WHERE id = ?", (observation_id,)
        ).fetchone()
        if row is None:
            return None
        return _observation_from_row(row)

    def list_revisions(self, observation: Observation) -> list[Observation]:
        """Return all source revisions sharing an observation's base identity."""
        _validate_observation(observation)
        rows = self._connection.execute(
            """
            SELECT * FROM observations
            WHERE dataset_id = ?
              AND observation_date = ?
              AND source_record_key = ?
              AND IFNULL(publication_label, '') = IFNULL(?, '')
            ORDER BY id
            """,
            (
                observation.dataset_id,
                observation.observation_date,
                observation.source_record_key,
                observation.publication_label,
            ),
        ).fetchall()
        return [_observation_from_row(row) for row in rows]


def base_identity_fields() -> tuple[str, ...]:
    return (
        "dataset_id",
        "observation_date",
        "source_record_key",
        "publication_label",
    )


def _observation_from_row(row: sqlite3.Row) -> Observation:
    return Observation(
        dataset_id=row["dataset_id"],
        schema_version=row["schema_version"],
        observation_date=row["observation_date"],
        source_date=row["source_date"],
        source_name=row["source_name"],
        source_url=row["source_url"],
        source_record_key=row["source_record_key"],
        published_at=row["published_at"],
        publication_label=row["publication_label"],
        effective_at=row["effective_at"],
        retrieved_at=row["retrieved_at"],
        ingested_at=row["ingested_at"],
        source_revision=row["source_revision"],
        supersedes_id=row["supersedes_id"],
        source_payload_hash=row["source_payload_hash"],
        parser_version=row["parser_version"],
        values=json.loads(row["values_json"]),
        quality_status=row["quality_status"],
        quality_notes=row["quality_notes"],
    )
