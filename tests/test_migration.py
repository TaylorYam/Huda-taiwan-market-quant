from __future__ import annotations

import pytest

from src.data.migration import validate_observation_export


def make_export(*, include_parent: bool = True) -> dict[str, object]:
    parent = {
        "id": 1,
        "dataset_id": "twse_taiex_daily_v1",
        "schema_version": "0.1",
        "observation_date": "2026-09-15",
        "source_date": "2026-09-15",
        "source_name": "TWSE",
        "source_url": "https://example.test/taiex",
        "source_record_key": "TAIEX",
        "published_at": None,
        "publication_label": None,
        "effective_at": None,
        "retrieved_at": "2026-09-16T00:00:00+00:00",
        "last_retrieved_at": "2026-09-16T00:00:00+00:00",
        "ingested_at": "2026-09-16T00:01:00+00:00",
        "source_revision": None,
        "supersedes_id": None,
        "source_payload_hash": "1" * 64,
        "parser_version": "test-parser@1",
        "values": {"close": 22_000.5},
        "quality_status": "available",
        "quality_notes": None,
        "retrieval_count": 1,
        "created_at": "2026-09-16T00:01:00+00:00",
    }
    child = {**parent, "id": 2, "source_payload_hash": "2" * 64, "supersedes_id": 1}
    records = [parent, child] if include_parent else [child]
    return {
        "format_version": "0.1",
        "source_store": "sqlite",
        "observation_count": len(records),
        "observations": records,
    }


def test_validate_export_accepts_complete_revision_chain() -> None:
    records = validate_observation_export(make_export())
    assert [record["id"] for record in records] == [1, 2]


def test_validate_export_rejects_missing_parent_by_default() -> None:
    with pytest.raises(ValueError, match="not present in the export"):
        validate_observation_export(make_export(include_parent=False))


def test_validate_export_can_allow_external_parent_for_filtered_export() -> None:
    records = validate_observation_export(
        make_export(include_parent=False), allow_external_parents=True
    )
    assert records[0]["supersedes_id"] == 1


def test_validate_export_rejects_cross_identity_revision() -> None:
    payload = make_export()
    records = payload["observations"]
    assert isinstance(records, list)
    records[1]["observation_date"] = "2026-09-16"
    with pytest.raises(ValueError, match="same logical identity"):
        validate_observation_export(payload)
