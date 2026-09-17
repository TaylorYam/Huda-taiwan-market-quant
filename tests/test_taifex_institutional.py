from __future__ import annotations

import json

import pytest

from src.data import (
    InstitutionalFuturesParseError,
    SQLiteObservationStore,
    collect_institutional_futures_latest,
    parse_institutional_futures_payload,
)


def payload(net: int = -76351) -> bytes:
    row = {
        "Date": "20260916",
        "ContractCode": "臺股期貨",
        "Item": "外資及陸資",
        "TradingVolume(Long)": "53295",
        "TradingVolume(Short)": "50697",
        "TradingVolume(Net)": "2598",
        "OpenInterest(Long)": "7805",
        "OpenInterest(Short)": "84156",
        "OpenInterest(Net)": str(net),
        "ContractValueofOpenInterest(Net)(Thousands)": "-703395432",
    }
    return json.dumps([row], ensure_ascii=False).encode()


def test_parse_institutional_futures_payload_selects_foreign_tx_row() -> None:
    [observation] = parse_institutional_futures_payload(payload())

    assert observation.observation_date == "2026-09-16"
    assert observation.values["open_interest_net"] == -76351
    assert observation.values["contract_code"] == "臺股期貨"
    assert observation.quality_status == "available"


def test_parse_requires_exactly_one_foreign_tx_row() -> None:
    with pytest.raises(InstitutionalFuturesParseError, match="exactly one"):
        parse_institutional_futures_payload(
            json.dumps(
                [
                    {
                        "Date": "20260916",
                        "ContractCode": "電子期貨",
                        "Item": "外資及陸資",
                    }
                ]
            ).encode()
        )


def test_collect_is_idempotent_and_links_revision() -> None:
    with SQLiteObservationStore(":memory:") as store:
        first = collect_institutional_futures_latest(
            store, http_get=lambda _: payload()
        )
        duplicate = collect_institutional_futures_latest(
            store, http_get=lambda _: payload()
        )
        revised = collect_institutional_futures_latest(
            store, http_get=lambda _: payload(-70000)
        )

    assert first[0].action == "inserted"
    assert duplicate[0].action == "duplicate"
    assert revised[0].action == "inserted"
