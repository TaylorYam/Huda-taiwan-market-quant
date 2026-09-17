from __future__ import annotations

import pytest

from src.data import (
    MarketTurnoverParseError,
    SQLiteObservationStore,
    build_market_turnover_month_url,
    collect_market_turnover_month,
    parse_market_turnover_payload,
)


def sample_payload() -> bytes:
    lines = [
        '"115年09月市場成交資訊"',
        '"日期","成交股數","成交金額","成交筆數","發行量加權股價指數","漲跌點數",',
        '"115/09/01","13,000,849,196","1,187,571,567,117","5,301,801","46,948.72","820.25",',
        '"115/09/02","10,824,863,832","976,499,979,054","5,093,402","46,164.72","-784.00",',
    ]
    return ("\r\n".join(lines) + "\r\n").encode("cp950")


def test_build_month_url_uses_verified_query_pattern():
    url = build_market_turnover_month_url(2026, 9)
    assert "date=20260901" in url
    assert "response=csv" in url


def test_parser_creates_daily_observations_with_roc_dates_converted():
    records = parse_market_turnover_payload(
        sample_payload(),
        source_url=build_market_turnover_month_url(2026, 9),
        expected_month="2026-09",
    )

    assert [record.observation_date for record in records] == [
        "2026-09-01",
        "2026-09-02",
    ]
    assert records[0].values == {"turnover": 1187571567117.0, "unit": "TWD"}
    assert records[0].source_date == "115/09/01"


def test_parser_rejects_duplicate_dates_and_wrong_month():
    duplicate = sample_payload().replace(b"115/09/02", b"115/09/01")
    with pytest.raises(MarketTurnoverParseError, match="repeats"):
        parse_market_turnover_payload(
            duplicate,
            source_url="https://example.invalid/fmtqik.csv",
            expected_month="2026-09",
        )

    with pytest.raises(MarketTurnoverParseError, match="does not match"):
        parse_market_turnover_payload(
            sample_payload(),
            source_url="https://example.invalid/fmtqik.csv",
            expected_month="2026-08",
        )


def test_parser_rejects_unavailable_turnover_value():
    bad = (
        '"115年09月市場成交資訊"\r\n'
        '"日期","成交股數","成交金額","成交筆數","發行量加權股價指數","漲跌點數",\r\n'
        '"115/09/01","1","-","1","1","1",\r\n'
    ).encode("cp950")

    with pytest.raises(MarketTurnoverParseError, match="unavailable"):
        parse_market_turnover_payload(
            bad, source_url="https://example.invalid/fmtqik.csv"
        )


def test_collector_writes_month_through_observation_store():
    with SQLiteObservationStore(":memory:") as store:
        results = collect_market_turnover_month(
            store, 2026, 9, http_get=lambda url: sample_payload()
        )

        assert [result.action for result in results] == ["inserted", "inserted"]
        observation = store.get_observation(results[0].observation_id)
        assert observation is not None
        assert observation.dataset_id == "twse_market_turnover_fmtqik_v1"
