from __future__ import annotations

import json
from typing import Self

from scripts import collect_taifex_institutional as collector
from src.data.taifex_institutional import parse_institutional_futures_payload


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


def test_expected_date_rejects_before_write(monkeypatch, capsys) -> None:
    [observation] = parse_institutional_futures_payload(payload())
    store = FakeStore()

    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SECRET_KEY", "test-secret")
    monkeypatch.setattr(collector, "SupabaseRestObservationStore", lambda *_: store)

    def fake_collect(guarded_store):
        return [guarded_store.write_observation(observation)]

    monkeypatch.setattr(collector, "collect_institutional_futures_latest", fake_collect)

    assert collector.main(["--write", "--expected-date", "2026-09-17"]) == 1
    assert store.writes == []
    assert "observation_date mismatch" in capsys.readouterr().out


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
