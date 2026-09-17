from __future__ import annotations

from typing import Any

from src.data import SupabaseRestObservationStore


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
