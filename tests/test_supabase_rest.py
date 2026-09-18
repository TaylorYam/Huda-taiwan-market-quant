from __future__ import annotations

from typing import Any

import pytest

from src.data import Observation, SupabaseRestObservationStore


class FakeResponse:
    ok = True
    status_code = 200
    content = b"[]"
    text = "[]"

    def json(self) -> list[dict[str, Any]]:
        return []


class FakeSession:
    def __init__(self) -> None:
        self.headers: dict[str, str] = {}
        self.calls: list[dict[str, Any]] = []

    def request(self, method: str, url: str, **kwargs: Any) -> FakeResponse:
        self.calls.append({"method": method, "url": url, **kwargs})
        return FakeResponse()

    def close(self) -> None:
        return None


class ScoreSession(FakeSession):
    def request(self, method: str, url: str, **kwargs: Any) -> FakeResponse:
        self.calls.append({"method": method, "url": url, **kwargs})
        response = FakeResponse()
        if method == "POST" and url.endswith("/rest/v1/market_scores"):
            response.content = b'[{"id": 9}]'
            response.text = response.content.decode()
            response.json = lambda: [{"id": 9}]  # type: ignore[method-assign]
        return response


class BulkObservationSession(FakeSession):
    def request(self, method: str, url: str, **kwargs: Any) -> FakeResponse:
        self.calls.append({"method": method, "url": url, **kwargs})
        response = FakeResponse()
        if method == "POST" and url.endswith("/rest/v1/observations"):
            payload = kwargs["json"]
            response.content = b"[{}]"
            response.text = response.content.decode()
            response.json = lambda payload=payload: [
                {
                    "id": 21,
                    "dataset_id": row["dataset_id"],
                    "observation_date": row["observation_date"],
                    "source_record_key": row["source_record_key"],
                    "publication_label": row["publication_label"],
                    "source_revision": row["source_revision"],
                    "source_payload_hash": row["source_payload_hash"],
                }
                for row in payload
            ]  # type: ignore[method-assign]
        return response


def _range_observation() -> Observation:
    return Observation(
        dataset_id="taifex_taiwan_vix_close_v1",
        schema_version="0.1",
        observation_date="2026-09-17",
        source_date="20260917",
        source_name="TAIFEX",
        source_url="https://example.test/vix",
        source_record_key="VIX:daily",
        retrieved_at="2026-09-18T00:00:00+00:00",
        ingested_at="2026-09-18T00:00:00+00:00",
        source_payload_hash="1" * 64,
        parser_version="test@0.1",
        values={"close": 27.29},
        quality_status="available",
    )


def test_supabase_rest_bulk_writes_range_in_one_insert() -> None:
    session = BulkObservationSession()

    with SupabaseRestObservationStore(
        "https://example.supabase.co",
        "sb_secret_test",
        session=session,
    ) as store:
        result = store.write_observations([_range_observation()])

    assert result[0].observation_id == 21
    assert result[0].action == "inserted"
    range_reads = [
        call
        for call in session.calls
        if call["method"] == "GET"
        and call["url"].endswith("/rest/v1/observations")
        and call["params"].get("limit") == "1000"
    ]
    assert len(range_reads) == 1
    post = session.calls[-1]
    assert post["method"] == "POST"
    assert isinstance(post["json"], list)
    assert post["json"][0]["values_json"] == {"close": 27.29}


def test_supabase_rest_store_uses_server_api_key_and_checks_table() -> None:
    session = FakeSession()

    with SupabaseRestObservationStore(
        "https://example.supabase.co",
        "sb_secret_test",
        session=session,
    ):
        pass

    assert session.headers["apikey"] == "sb_secret_test"
    assert session.headers["Authorization"] == "Bearer sb_secret_test"
    assert session.calls[0]["method"] == "GET"
    assert session.calls[0]["url"].endswith("/rest/v1/observations")


def test_supabase_rest_store_can_verify_derived_score_table() -> None:
    session = FakeSession()

    with SupabaseRestObservationStore(
        "https://example.supabase.co",
        "sb_secret_test",
        session=session,
    ) as store:
        store.verify_table("market_scores")

    assert session.calls[1]["url"].endswith("/rest/v1/market_scores")


def test_supabase_rest_store_writes_market_score_payload() -> None:
    session = ScoreSession()
    record = {
        "model_version": "v0.1",
        "target_date": "2026-09-17",
        "as_of": None,
        "status": "unavailable",
        "score": None,
        "direction": None,
        "reason": "missing_or_unavailable_required_factors",
        "calculation_hash": "a" * 64,
        "factor_scores_json": {},
        "observation_identities_json": [],
    }

    with SupabaseRestObservationStore(
        "https://example.supabase.co",
        "sb_secret_test",
        session=session,
    ) as store:
        result = store.write_market_score(record)

    assert result.score_id == 9
    assert result.action == "inserted"
    post = session.calls[-1]
    assert post["method"] == "POST"
    assert post["json"]["calculation_hash"] == "a" * 64


def test_supabase_rest_lists_market_score_identities_in_a_date_range() -> None:
    session = FakeSession()

    with SupabaseRestObservationStore(
        "https://example.supabase.co",
        "sb_secret_test",
        session=session,
    ) as store:
        assert (
            store.list_market_scores(
                model_version="v0.1",
                start_date="2026-01-01",
                end_date="2026-01-31",
                limit=100,
            )
            == []
        )

    request = session.calls[-1]
    assert request["url"].endswith("/rest/v1/market_scores")
    assert request["params"] == {
        "select": "id,model_version,target_date,calculation_hash",
        "order": "target_date.asc,id.asc",
        "limit": "100",
        "model_version": "eq.v0.1",
        "target_date": ["gte.2026-01-01", "lte.2026-01-31"],
    }


def _backtest_row(row_id: int, observation_date: str) -> dict[str, Any]:
    return {
        "id": row_id,
        "dataset_id": "twse_taiex_daily_v1",
        "schema_version": "0.1",
        "observation_date": observation_date,
        "source_date": observation_date,
        "source_name": "TWSE",
        "source_url": "https://example.test/taiex",
        "source_record_key": "TAIEX",
        "published_at": None,
        "publication_label": None,
        "effective_at": None,
        "retrieved_at": "2026-09-17T00:00:00+00:00",
        "ingested_at": "2026-09-17T00:00:00+00:00",
        "source_revision": None,
        "supersedes_id": None,
        "source_payload_hash": "0" * 64,
        "parser_version": "test@0.1",
        "values_json": {"close": 100.0},
        "quality_status": "available",
        "quality_notes": None,
    }


class PagedBacktestSession(FakeSession):
    """Returns one observation row per page to exercise cursor pagination."""

    def __init__(self, rows: list[dict[str, Any]]) -> None:
        super().__init__()
        self.rows = rows

    def request(self, method: str, url: str, **kwargs: Any) -> FakeResponse:
        self.calls.append({"method": method, "url": url, **kwargs})
        params = kwargs.get("params") or {}
        response = FakeResponse()
        if url.endswith("/observations") and params.get("limit") == "1000":
            cursor = int(params["id"].removeprefix("gt."))
            page = [row for row in self.rows if row["id"] > cursor][:1]
            response.json = lambda page=page: page  # type: ignore[method-assign]
        return response


def test_load_backtest_observations_pages_through_a_capped_transport() -> None:
    rows = [_backtest_row(i, f"2026-01-{i:02d}") for i in range(1, 4)]
    session = PagedBacktestSession(rows)

    with SupabaseRestObservationStore(
        "https://example.supabase.co",
        "sb_secret_test",
        session=session,
    ) as store:
        result = store.load_backtest_observations(
            dataset_ids=["twse_taiex_daily_v1"],
            start_date="2026-01-01",
            end_date="2026-01-31",
        )

    assert [observation.observation_date for observation in result] == [
        "2026-01-01",
        "2026-01-02",
        "2026-01-03",
    ]
    backtest_calls = [
        call
        for call in session.calls
        if call["url"].endswith("/observations")
        and call["params"].get("limit") == "1000"
    ]
    # 3 one-row pages plus the final empty page that ends the loop: pagination
    # must not stop just because a page came back shorter than the limit.
    assert len(backtest_calls) == 4
    assert backtest_calls[0]["params"]["observation_date"] == [
        "gte.2026-01-01",
        "lte.2026-01-31",
    ]


def test_load_backtest_observations_rejects_a_reversed_date_range() -> None:
    with (
        SupabaseRestObservationStore(
            "https://example.supabase.co",
            "sb_secret_test",
            session=FakeSession(),
        ) as store,
        pytest.raises(ValueError),
    ):
        store.load_backtest_observations(
            dataset_ids=["twse_taiex_daily_v1"],
            start_date="2026-02-01",
            end_date="2026-01-01",
        )
