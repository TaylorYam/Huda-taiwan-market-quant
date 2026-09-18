from dataclasses import asdict, replace
from datetime import date, timedelta

import pytest
from test_daily_score_pipeline import _observation
from test_supabase_rest import FakeResponse, FakeSession

from src.data.supabase_rest import SupabaseRestObservationStore
from src.scoring.daily_runner import main, run_daily_score


@pytest.fixture
def observations():
    target = date(2026, 9, 17)
    return [
        _observation(
            "twse_taiex_daily_v1",
            target - timedelta(days=offset),
            {"close": 20000 - offset},
            "TAIEX",
        )
        for offset in range(59, -1, -1)
    ]


class MemoryApi(FakeSession):
    """Exercise real Data API reader/writer through a capped fake transport."""

    def __init__(self, observations):
        super().__init__()
        self.rows = []
        self.scores = []
        for index, observation in enumerate(observations, 1):
            row = asdict(observation)
            row["values_json"] = row.pop("values")
            row["id"] = index
            self.rows.append(row)

    def request(self, method, url, **kwargs):
        self.calls.append({"method": method, "url": url, **kwargs})
        params = kwargs.get("params") or {}
        rows = []
        if url.endswith("/observations") and params.get("limit") != "0":
            cursor = int(params["id"].removeprefix("gt."))
            # Intentionally cap below the requested page size.
            rows = [row for row in self.rows if row["id"] > cursor][:7]
        elif url.endswith("/market_scores"):
            if method == "POST":
                rows = [{"id": len(self.scores) + 1, **kwargs["json"]}]
                self.scores.extend(rows)
            elif "calculation_hash" in params:
                rows = [
                    row
                    for row in self.scores
                    if params["calculation_hash"] == f"eq.{row['calculation_hash']}"
                ]
        response = FakeResponse()
        response.json = lambda: rows
        return response


def run(session, as_of="2026-09-17T20:00:00+08:00"):
    with SupabaseRestObservationStore(
        "https://example.supabase.co", "test-only", session=session
    ) as store:
        return run_daily_score(store, store, target_date="2026-09-17", as_of=as_of)


def test_paged_read_persists_unavailable_and_replay_is_duplicate(observations):
    api = MemoryApi(observations)
    first = run(api)
    second = run(api, "2026-09-17T12:00:00Z")
    assert first["status"] == "unavailable"
    assert first["score"] is None
    assert first["observation_count"] == 60
    assert first["factor_scores"]["taiex_ma20_ma60_trend"]["status"] == "available"
    # 60 consecutive TAIEX closes give 39 candidate dates with >=21 trailing
    # closes each, so momentum's own percentile history is now buildable.
    assert first["factor_scores"]["taiex_20d_momentum"]["status"] == "available"
    assert "foreign_cash_5d" in first["missing_factor_ids"]
    assert first["action"] == "inserted"
    assert second["action"] == "duplicate"
    assert first["calculation_hash"] == second["calculation_hash"]
    assert len(api.scores) == 1
    assert len(api.scores[0]["observation_identities_json"]) == 60
    page = next(call for call in api.calls if call["params"].get("id") == "gt.7")
    assert page["params"]["ingested_at"] == "lte.2026-09-17T20:00:00+08:00"


@pytest.mark.parametrize("field", ["published_at", "retrieved_at", "ingested_at"])
def test_future_evidence_is_excluded(observations, field):
    observations[-1] = replace(observations[-1], **{field: "2026-09-18T00:00:00Z"})
    result = run(MemoryApi(observations))
    assert result["observation_count"] == 59
    assert result["factor_scores"]["taiex_ma20_ma60_trend"]["status"] == "unavailable"


def test_known_revision_changes_hash_but_future_revision_does_not(observations):
    api = MemoryApi(observations)
    initial = run(api)
    revision = dict(
        api.rows[-1], id=61, source_revision="2", source_payload_hash="b" * 64
    )
    revision["retrieved_at"] = "2026-09-18T00:00:00Z"
    api.rows.append(revision)
    assert run(api)["action"] == "duplicate"
    revision["retrieved_at"] = "2026-09-17T01:00:00Z"
    revised = run(api)
    assert revised["calculation_hash"] != initial["calculation_hash"]
    assert len(api.scores) == 2


def test_empty_sources_still_persist_unavailable():
    api = MemoryApi([])
    result = run(api)
    assert result["status"] == "unavailable"
    assert len(result["missing_factor_ids"]) == 8
    assert len(api.scores) == 1


def test_non_available_quality_rows_are_not_counted_or_used(observations):
    observations[-1] = replace(observations[-1], quality_status="source_empty")
    result = run(MemoryApi(observations))

    assert result["observation_count"] == 59
    assert result["factor_scores"]["taiex_ma20_ma60_trend"]["status"] == "unavailable"


def test_target_date_requires_canonical_yyyy_mm_dd():
    with pytest.raises(ValueError, match="YYYY-MM-DD"):
        run_daily_score(
            MemoryApi([]),
            MemoryApi([]),
            target_date="20260917",
            as_of="2026-09-17T20:00:00+08:00",
        )


def test_main_rejects_future_target_before_connecting(monkeypatch, capsys):
    called = False

    def fail_if_connected(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("invalid run window must be rejected before I/O")

    monkeypatch.setattr(
        "src.scoring.daily_runner.SupabaseRestObservationStore", fail_if_connected
    )
    assert (
        main(
            [
                "--target-date",
                "2026-09-18",
                "--as-of",
                "2026-09-17T20:00:00+08:00",
            ]
        )
        == 1
    )
    assert called is False
    assert "failed" in capsys.readouterr().err


@pytest.mark.parametrize("boundary", ["2026-09-17", "bad", "2026-09-16T12:00:00Z"])
def test_invalid_boundary_writes_nothing(boundary):
    api = MemoryApi([])
    with pytest.raises(ValueError):
        run(api, boundary)
    assert not api.scores


def test_failure_does_not_log_transport_secrets(monkeypatch, capsys):
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SECRET_KEY", "secret-must-not-leak")

    def fail(*args, **kwargs):
        raise RuntimeError("secret-must-not-leak")

    monkeypatch.setattr(SupabaseRestObservationStore, "initialize", fail)
    assert (
        main(["--target-date", "2026-09-17", "--as-of", "2026-09-17T20:00:00+08:00"])
        == 1
    )
    output = capsys.readouterr()
    assert "secret-must-not-leak" not in output.err + output.out
    assert "failed" in output.err


def test_read_failure_does_not_write():
    class BrokenReader:
        def load_score_observations(self, **kwargs):
            raise RuntimeError("transport failed")

    class NoWrite:
        def write_market_score(self, record):
            pytest.fail("a read failure must not write an unavailable record")

    with pytest.raises(RuntimeError, match="transport failed"):
        run_daily_score(
            BrokenReader(),
            NoWrite(),
            target_date="2026-09-17",
            as_of="2026-09-17T20:00:00+08:00",
        )


def test_institutional_observations_reach_existing_adapter():
    from test_institutional_factor import observation

    target = date(2026, 9, 17)
    api = MemoryApi(
        [
            observation(target - timedelta(days=offset), -80000 + offset * 1000)
            for offset in range(5, -1, -1)
        ]
    )
    result = run(api)
    identities = api.scores[0]["observation_identities_json"]
    assert len(identities) == 6
    assert all(
        row["dataset_id"] == "taifex_institutional_futures_oi_v1" for row in identities
    )
    # 5 of the 6 fixture dates fall strictly before target, each with its own
    # institutional observation, so the position factor's percentile history
    # is now buildable from them.
    assert result["factor_scores"]["foreign_tx_net_position"]["status"] == "available"


def test_pagination_rejects_repeated_page(observations):
    class StuckApi(MemoryApi):
        def request(self, method, url, **kwargs):
            if "id" in (kwargs.get("params") or {}):
                kwargs["params"]["id"] = "gt.0"
            return super().request(method, url, **kwargs)

    api = StuckApi(observations)
    with pytest.raises(RuntimeError, match="did not advance"):
        run(api)
    assert not api.scores
