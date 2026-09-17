from __future__ import annotations

from typing import Any

from src.dashboard.data import DashboardDataStore


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


def test_dashboard_reads_are_get_only_and_preserve_latest_unavailable() -> None:
    session = FakeSession()
    with DashboardDataStore(
        "https://example.supabase.co", "sb_secret_test", session=session
    ) as store:
        assert store.get_latest_market_score() is None
        score_call = session.calls[-1]
        assert score_call["params"] == {
            "select": "*",
            "order": "target_date.desc,created_at.desc,id.desc",
            "limit": "1",
        }
        assert store.get_latest_source_quality("twse_taiex_daily_v1") is None
        assert session.calls[-1]["params"]["order"] == "last_retrieved_at.desc,id.desc"
        assert session.calls[-1]["params"]["dataset_id"] == "eq.twse_taiex_daily_v1"
        response = FakeResponse()
        latest = {"status": "unavailable", "score": None}
        response.json = lambda: [latest]
        session.request = lambda *args, **kwargs: response
        assert store.get_latest_market_score() == latest
    assert all(call["method"] == "GET" for call in session.calls)
