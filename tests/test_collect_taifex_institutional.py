from __future__ import annotations

import gzip
import json
from typing import Self

import pytest

from scripts import collect_taifex_institutional as collector
from src.data.taifex_institutional import (
    fetch_institutional_futures_latest,
    parse_institutional_futures_payload,
)


def payload(trade_date: str = "20260916", *, encoding: str = "utf-8") -> bytes:
    return json.dumps(
        [
            {
                "Date": trade_date,
                "ContractCode": "臺股期貨",
                "Item": "外資及陸資",
                "TradingVolume(Long)": "53295",
                "TradingVolume(Short)": "50697",
                "TradingVolume(Net)": "2598",
                "OpenInterest(Long)": "7805",
                "OpenInterest(Short)": "84156",
                "OpenInterest(Net)": "-76351",
                "ContractValueofOpenInterest(Net)(Thousands)": "-703395432",
            }
        ],
        ensure_ascii=False,
    ).encode(encoding)


def test_cp950_json_payload_is_supported() -> None:
    [observation] = parse_institutional_futures_payload(payload(encoding="cp950"))

    assert observation.observation_date == "2026-09-16"
    assert observation.values["open_interest_net"] == -76351


def test_fetch_retries_transient_non_json_response() -> None:
    responses = iter([b"temporarily unavailable", payload(encoding="cp950")])
    delays: list[float] = []

    observations = fetch_institutional_futures_latest(
        http_get=lambda _url: next(responses),
        sleep=delays.append,
    )

    assert observations[0].observation_date == "2026-09-16"
    assert delays == [1.0]


def test_gzip_json_payload_is_supported() -> None:
    compressed = gzip.compress(payload())

    [observation] = parse_institutional_futures_payload(compressed)

    assert observation.observation_date == "2026-09-16"


def test_expected_date_match_passes() -> None:
    [observation] = parse_institutional_futures_payload(payload())

    collector._assert_expected_date(observation, "2026-09-16")


def test_expected_date_rejects_stale_read_only_snapshot(monkeypatch, capsys) -> None:
    [observation] = parse_institutional_futures_payload(payload())
    monkeypatch.setattr(
        collector, "fetch_institutional_futures_latest", lambda: [observation]
    )

    assert collector.main(["--expected-date", "2026-09-17"]) == 1

    output = capsys.readouterr().out
    assert "observation_date mismatch" in output
    assert "expected 2026-09-17, got 2026-09-16" in output


class FakeStore:
    def __init__(self) -> None:
        self.writes = []

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def write_observation(self, observation):
        self.writes.append(observation)
        return type("Result", (), {"action": "inserted", "observation_id": 1})()


@pytest.mark.parametrize(
    ("expected_date", "snapshot_date"),
    [
        ("2026-09-17", "20260916"),
        # If the requested Monday is a market holiday or the report is late,
        # Friday's snapshot must not be relabeled as Monday's observation.
        ("2026-09-21", "20260918"),
    ],
    ids=["stale-daily-snapshot", "previous-session-after-weekend-or-holiday"],
)
def test_expected_date_rejects_before_write(
    monkeypatch, capsys, expected_date: str, snapshot_date: str
) -> None:
    [observation] = parse_institutional_futures_payload(payload(snapshot_date))
    store = FakeStore()

    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SECRET_KEY", "test-secret")
    monkeypatch.setattr(collector, "SupabaseRestObservationStore", lambda *_: store)

    def fake_collect(guarded_store):
        return [guarded_store.write_observation(observation)]

    monkeypatch.setattr(collector, "collect_institutional_futures_latest", fake_collect)

    assert collector.main(["--write", "--expected-date", expected_date]) == 1
    assert store.writes == []
    output = capsys.readouterr().out
    assert "observation_date mismatch" in output
    assert f"expected {expected_date}, got {observation.observation_date}" in output


def test_without_expected_date_keeps_write_path(monkeypatch, capsys) -> None:
    [observation] = parse_institutional_futures_payload(payload())
    store = FakeStore()

    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SECRET_KEY", "test-secret")
    monkeypatch.setattr(collector, "SupabaseRestObservationStore", lambda *_: store)

    def fake_collect(passed_store):
        assert passed_store is store
        return [passed_store.write_observation(observation)]

    monkeypatch.setattr(collector, "collect_institutional_futures_latest", fake_collect)

    assert collector.main(["--write"]) == 0
    assert store.writes == [observation]
    assert "inserted" in capsys.readouterr().out
