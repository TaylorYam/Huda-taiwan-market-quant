from __future__ import annotations

import pytest

from src.data import Observation, SQLiteObservationStore


def make_observation(**changes: object) -> Observation:
    default_values = {
        "close": 22_000.5,
        "unit": "index_points",
    }
    values = changes.pop("values", default_values)
    fields: dict[str, object] = {
        "dataset_id": "twse_taiex_daily_v1",
        "schema_version": "0.1",
        "observation_date": "2026-09-15",
        "source_date": "2026-09-15",
        "source_name": "TWSE",
        "source_url": "https://example.test/taiex",
        "source_record_key": "TAIEX",
        "retrieved_at": "2026-09-16T00:00:00+00:00",
        "ingested_at": "2026-09-16T00:01:00+00:00",
        "source_payload_hash": "1" * 64,
        "parser_version": "test-parser@1",
        "values": values,
        "quality_status": "available",
    }
    fields.update(changes)
    return Observation(**fields)


def test_same_payload_is_idempotent_and_tracks_retrieval(tmp_path):
    with SQLiteObservationStore(tmp_path / "market.sqlite3") as store:
        first = store.write_observation(make_observation())
        second = store.write_observation(
            make_observation(retrieved_at="2026-09-16T00:02:00+00:00")
        )

        assert first.action == "inserted"
        assert second == type(first)(first.observation_id, "duplicate")
        row = store._connection.execute(
            "SELECT retrieval_count, last_retrieved_at FROM observations WHERE id = ?",
            (first.observation_id,),
        ).fetchone()
        assert row["retrieval_count"] == 2
        assert row["last_retrieved_at"] == "2026-09-16T00:02:00+00:00"


def test_revision_appends_and_preserves_previous_value(tmp_path):
    with SQLiteObservationStore(tmp_path / "market.sqlite3") as store:
        first = store.write_observation(make_observation())
        revised = store.write_observation(
            make_observation(
                values={"close": 22_001.5, "unit": "index_points"},
                source_payload_hash="2" * 64,
                supersedes_id=first.observation_id,
            )
        )

        assert revised.action == "inserted"
        assert revised.observation_id != first.observation_id
        assert store.get_observation(first.observation_id).values["close"] == 22_000.5
        assert (
            store.get_observation(revised.observation_id).supersedes_id
            == first.observation_id
        )


def test_new_source_revision_can_link_to_previous_revision(tmp_path):
    with SQLiteObservationStore(tmp_path / "market.sqlite3") as store:
        first = store.write_observation(make_observation(source_revision="r1"))
        revised = store.write_observation(
            make_observation(
                source_revision="r2",
                source_payload_hash="2" * 64,
                supersedes_id=first.observation_id,
            )
        )

        assert revised.action == "inserted"
        assert store.list_revisions(make_observation())[-1].source_revision == "r2"


def test_new_source_revision_requires_lineage_link(tmp_path):
    with SQLiteObservationStore(tmp_path / "market.sqlite3") as store:
        store.write_observation(make_observation(source_revision="r1"))

        with pytest.raises(ValueError, match="requires supersedes_id"):
            store.write_observation(
                make_observation(source_revision="r2", source_payload_hash="2" * 64)
            )


def test_changed_payload_requires_explicit_revision_link(tmp_path):
    with SQLiteObservationStore(tmp_path / "market.sqlite3") as store:
        store.write_observation(make_observation())

        with pytest.raises(ValueError, match="requires supersedes_id"):
            store.write_observation(
                make_observation(
                    values={"close": 22_001.5, "unit": "index_points"},
                    source_payload_hash="2" * 64,
                )
            )


def test_unavailable_state_is_stored_without_zero_substitution(tmp_path):
    with SQLiteObservationStore(tmp_path / "market.sqlite3") as store:
        result = store.write_observation(
            make_observation(
                values={},
                quality_status="not_published",
                quality_notes="Official endpoint has not published the date.",
            )
        )

        stored = store.get_observation(result.observation_id)
        assert stored.quality_status == "not_published"
        assert stored.values == {}
        assert stored.quality_notes.startswith("Official")


def test_timestamps_require_timezone_and_utc_for_retrieval(tmp_path):
    with SQLiteObservationStore(tmp_path / "market.sqlite3") as store:
        with pytest.raises(ValueError, match="retrieved_at.*UTC"):
            store.write_observation(
                make_observation(retrieved_at="2026-09-16T08:00:00+08:00")
            )

        with pytest.raises(ValueError, match="published_at.*timezone"):
            store.write_observation(
                make_observation(published_at="2026-09-16T08:00:00")
            )


def test_source_date_preserves_official_raw_format(tmp_path):
    with SQLiteObservationStore(tmp_path / "market.sqlite3") as store:
        result = store.write_observation(
            make_observation(source_date="20260915", source_payload_hash="3" * 64)
        )
        assert store.get_observation(result.observation_id).source_date == "20260915"


def test_source_identity_and_hash_are_validated(tmp_path):
    with SQLiteObservationStore(tmp_path / "market.sqlite3") as store:
        with pytest.raises(ValueError, match="SHA-256"):
            store.write_observation(make_observation(source_payload_hash="hash-1"))
        with pytest.raises(ValueError, match="TWSE or TAIFEX"):
            store.write_observation(
                make_observation(source_name="OTHER", source_payload_hash="4" * 64)
            )


def test_out_of_order_retry_does_not_move_last_retrieval_backwards(tmp_path):
    with SQLiteObservationStore(tmp_path / "market.sqlite3") as store:
        first = store.write_observation(
            make_observation(retrieved_at="2026-09-16T00:02:00+00:00")
        )
        store.write_observation(
            make_observation(retrieved_at="2026-09-16T00:01:00+00:00")
        )
        row = store._connection.execute(
            "SELECT last_retrieved_at FROM observations WHERE id = ?",
            (first.observation_id,),
        ).fetchone()
        assert row["last_retrieved_at"] == "2026-09-16T00:02:00+00:00"


def test_non_json_numbers_are_rejected(tmp_path):
    with (
        SQLiteObservationStore(tmp_path / "market.sqlite3") as store,
        pytest.raises(ValueError, match="JSON serializable"),
    ):
        store.write_observation(make_observation(values={"close": float("nan")}))


def test_export_preserves_storage_ids_and_revision_lineage(tmp_path):
    with SQLiteObservationStore(tmp_path / "market.sqlite3") as store:
        first = store.write_observation(make_observation())
        revised = store.write_observation(
            make_observation(
                values={"close": 22_001.5, "unit": "index_points"},
                source_payload_hash="2" * 64,
                supersedes_id=first.observation_id,
            )
        )

        exported = store.export_observations()

    assert [row["id"] for row in exported] == [
        first.observation_id,
        revised.observation_id,
    ]
    assert exported[0]["values"] == {
        "close": 22_000.5,
        "unit": "index_points",
    }
    assert exported[1]["supersedes_id"] == first.observation_id
    assert "values_json" not in exported[0]


def test_export_filters_by_dataset_and_date_without_changing_order(tmp_path):
    with SQLiteObservationStore(tmp_path / "market.sqlite3") as store:
        store.write_observation(make_observation(observation_date="2026-09-14"))
        store.write_observation(
            make_observation(
                observation_date="2026-09-15",
                source_payload_hash="2" * 64,
                source_record_key="other",
            )
        )
        result = store.export_observations(
            dataset_ids=["twse_taiex_daily_v1"],
            start_date="2026-09-15",
            end_date="2026-09-15",
        )

    assert len(result) == 1
    assert result[0]["observation_date"] == "2026-09-15"
    assert result[0]["source_record_key"] == "other"
