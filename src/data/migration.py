"""Validation helpers for controlled SQLite observation migrations."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from datetime import date, datetime
from typing import Any

from .storage import QUALITY_STATUSES

EXPORT_FORMAT_VERSION = "0.1"
_HASH_PATTERN = re.compile(r"^[0-9a-fA-F]{64}$")
_REQUIRED_RECORD_FIELDS = frozenset(
    {
        "id",
        "dataset_id",
        "schema_version",
        "observation_date",
        "source_date",
        "source_name",
        "source_url",
        "source_record_key",
        "retrieved_at",
        "ingested_at",
        "source_payload_hash",
        "parser_version",
        "values",
        "quality_status",
        "supersedes_id",
        "retrieval_count",
        "created_at",
    }
)


def validate_observation_export(
    payload: Mapping[str, Any], *, allow_external_parents: bool = False
) -> list[Mapping[str, Any]]:
    """Validate an observation export and return its records.

    A complete migration export must include every local parent referenced by
    ``supersedes_id``.  Filtered exports can explicitly allow a parent to live
    in an already migrated store by setting ``allow_external_parents=True``.
    """

    if payload.get("format_version") != EXPORT_FORMAT_VERSION:
        raise ValueError("unsupported observation export format_version")
    if payload.get("source_store") != "sqlite":
        raise ValueError("observation export source_store must be sqlite")
    records = payload.get("observations")
    if not isinstance(records, list):
        raise TypeError("observation export observations must be a list")
    if payload.get("observation_count") != len(records):
        raise ValueError("observation_count does not match observations")

    ids: set[int] = set()
    identity_keys: set[tuple[Any, ...]] = set()
    normalized: list[Mapping[str, Any]] = []
    for record in records:
        if not isinstance(record, Mapping):
            raise TypeError("each exported observation must be an object")
        missing = sorted(_REQUIRED_RECORD_FIELDS - set(record))
        if missing:
            raise ValueError(
                "exported observation missing fields: " + ", ".join(missing)
            )
        storage_id = _positive_int(record["id"], "id")
        if storage_id in ids:
            raise ValueError(f"duplicate exported observation id: {storage_id}")
        ids.add(storage_id)
        _validate_record(record)
        identity = (
            record["dataset_id"],
            record["observation_date"],
            record["source_record_key"],
            record.get("publication_label"),
            record.get("source_revision"),
            record["source_payload_hash"].lower(),
        )
        if identity in identity_keys:
            raise ValueError("duplicate exported observation payload identity")
        identity_keys.add(identity)
        normalized.append(record)

    ordered_ids = [int(record["id"]) for record in normalized]
    if ordered_ids != sorted(ordered_ids):
        raise ValueError("exported observations must be ordered by id")

    for record in normalized:
        parent_id = record["supersedes_id"]
        if parent_id is None:
            continue
        parent_id = _positive_int(parent_id, "supersedes_id")
        if parent_id == record["id"]:
            raise ValueError("observation cannot supersede itself")
        if parent_id not in ids:
            if allow_external_parents:
                continue
            raise ValueError(f"supersedes_id {parent_id} is not present in the export")
        parent = next(item for item in normalized if item["id"] == parent_id)
        if _base_identity(record) != _base_identity(parent):
            raise ValueError("supersedes_id must reference the same logical identity")

    _validate_lineage(normalized, allow_external_parents=allow_external_parents)
    return normalized


def _validate_record(record: Mapping[str, Any]) -> None:
    if not isinstance(record["dataset_id"], str) or not record["dataset_id"].strip():
        raise ValueError("exported dataset_id must not be empty")
    if record["source_name"] not in {"TWSE", "TAIFEX"}:
        raise ValueError("exported source_name must be TWSE or TAIFEX")
    if record["quality_status"] not in QUALITY_STATUSES:
        raise ValueError("exported quality_status is not supported")
    if not isinstance(record["values"], Mapping):
        raise TypeError("exported values must be an object")
    if _HASH_PATTERN.fullmatch(str(record["source_payload_hash"])) is None:
        raise ValueError("exported source_payload_hash must be SHA-256 hex")
    if _positive_int(record["retrieval_count"], "retrieval_count") < 1:
        raise ValueError("exported retrieval_count must be at least 1")
    _date(record["observation_date"], "observation_date")
    for field in ("retrieved_at", "ingested_at", "created_at"):
        _timestamp(record[field], field)
    for field in ("published_at", "effective_at"):
        if record[field] is not None:
            _timestamp(record[field], field)


def _validate_lineage(
    records: Sequence[Mapping[str, Any]], *, allow_external_parents: bool
) -> None:
    parents = {int(record["id"]): record["supersedes_id"] for record in records}
    ids = set(parents)
    for storage_id in ids:
        seen: set[int] = set()
        current: int | None = storage_id
        while current is not None and current in ids:
            if current in seen:
                raise ValueError("observation revision lineage contains a cycle")
            seen.add(current)
            parent = parents[current]
            if parent is None:
                break
            parent = _positive_int(parent, "supersedes_id")
            if parent not in ids:
                if allow_external_parents:
                    break
                raise ValueError(f"supersedes_id {parent} is not present in the export")
            current = parent


def _base_identity(record: Mapping[str, Any]) -> tuple[Any, ...]:
    return (
        record["dataset_id"],
        record["observation_date"],
        record["source_record_key"],
        record.get("publication_label"),
    )


def _positive_int(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"exported {field} must be a positive integer")
    return value


def _date(value: Any, field: str) -> None:
    if not isinstance(value, str):
        raise TypeError(f"exported {field} must be YYYY-MM-DD")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"exported {field} must be YYYY-MM-DD") from exc
    if parsed.isoformat() != value:
        raise ValueError(f"exported {field} must be YYYY-MM-DD")


def _timestamp(value: Any, field: str) -> None:
    if not isinstance(value, str):
        raise TypeError(f"exported {field} must be an RFC 3339 timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"exported {field} must be an RFC 3339 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"exported {field} must include a timezone")


__all__ = ["EXPORT_FORMAT_VERSION", "validate_observation_export"]
