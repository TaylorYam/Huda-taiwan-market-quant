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
