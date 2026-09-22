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


def test_dashboard_history_reads_are_get_only() -> None:
    session = FakeSession()
    with DashboardDataStore(
        "https://example.supabase.co", "sb_secret_test", session=session
    ) as store:
        assert store.get_market_score_history(limit=12) == []
        assert store.get_observation_history("twse_taiex_daily_v1", limit=24) == []

    score_call = session.calls[-2]
    assert score_call["method"] == "GET"
    assert score_call["url"].endswith("/market_scores")
    assert score_call["params"] == {
        "select": (
            "id,target_date,as_of,status,score,direction,reason,"
            "factor_scores_json,created_at"
        ),
        "order": "target_date.asc,created_at.asc,id.asc",
        "limit": "12",
        "offset": "0",
    }
    observation_call = session.calls[-1]
    assert observation_call["method"] == "GET"
    assert observation_call["url"].endswith("/observations")
    assert observation_call["params"]["dataset_id"] == "eq.twse_taiex_daily_v1"
    assert observation_call["params"]["limit"] == "24"
    assert observation_call["params"]["offset"] == "0"
    assert all(call["method"] == "GET" for call in session.calls)


def test_dashboard_history_limits_are_bounded() -> None:
    session = FakeSession()
    with DashboardDataStore(
        "https://example.supabase.co", "sb_secret_test", session=session
    ) as store:
        for limit in (0, 5001, True):
            try:
                store.get_market_score_history(limit=limit)
            except ValueError:
                pass
            else:
                raise AssertionError("invalid history limit was accepted")


class PagedResponse:
    ok = True
    status_code = 200

    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows
        self.content = b"[{}]" if rows else b"[]"
        self.text = "[]"

    def json(self) -> list[dict[str, Any]]:
        return self._rows


def test_dashboard_history_paginates_past_postgrest_page_cap() -> None:
    session = FakeSession()
    first_page = [{"id": index} for index in range(1000)]
    second_page = [{"id": 1000}]

    def request(method: str, url: str, **kwargs: Any) -> PagedResponse:
        session.calls.append({"method": method, "url": url, **kwargs})
        offset = int(kwargs["params"].get("offset", 0))
        return PagedResponse(first_page if offset == 0 else second_page)

    session.request = request
    with DashboardDataStore(
        "https://example.supabase.co", "sb_secret_test", session=session
    ) as store:
        rows = store.get_market_score_history(limit=1001)

    assert len(rows) == 1001
    history_calls = [
        call for call in session.calls if call["url"].endswith("/market_scores")
    ]
    assert [call["params"]["offset"] for call in history_calls] == ["0", "1000"]
