from __future__ import annotations

import json
from datetime import date

import pytest

from src.data import (
    InstitutionalFuturesParseError,
    SQLiteObservationStore,
    collect_institutional_futures_latest,
    collect_institutional_futures_range,
    parse_institutional_futures_payload,
    parse_institutional_futures_range_payload,
)

_RANGE_HEADER = (
    "日期,商品名稱,身份別,多方交易口數,多方交易契約金額(千元),空方交易口數,"
    "空方交易契約金額(千元),多空交易口數淨額,多空交易契約金額淨額(千元),"
    "多方未平倉口數,多方未平倉契約金額(千元),空方未平倉口數,空方未平倉契約金額(千元),"
    "多空未平倉口數淨額,多空未平倉契約金額淨額(千元)"
)


def range_payload(*rows: str) -> bytes:
    lines = [_RANGE_HEADER, *rows]
    return ("\r\n".join(lines) + "\r\n").encode("cp950")


def foreign_row(trade_date: str, net_oi: int = -7012) -> str:
    return (
        f"{trade_date},臺股期貨,外資及陸資,56715,187119842,53643,176970389,"
        f"3072,10149454,21184,70144461,28196,93362451,{net_oi},-23217990"
    )


def dealer_row(trade_date: str) -> str:
    return f"{trade_date},臺股期貨,自營商,8502,28081918,9401,31050836,-899,-2968918,5323,17624827,6281,20796472,-958,-3171645"


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


def test_parse_latest_accepts_utf8_bom_csv_payload() -> None:
    csv_payload = (
        "\ufeff" + _RANGE_HEADER + "\r\n" + foreign_row("2026/09/18") + "\r\n"
    ).encode("utf-8")

    [observation] = parse_institutional_futures_payload(csv_payload)

    assert observation.observation_date == "2026-09-18"
    assert observation.source_date == "2026/09/18"
    assert observation.values["open_interest_net"] == -7012
    assert observation.publication_label == "latest"


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


def test_parse_range_payload_keeps_only_foreign_row_per_date() -> None:
    payload = range_payload(dealer_row("2023/10/02"), foreign_row("2023/10/02"))

    [observation] = parse_institutional_futures_range_payload(payload)

    assert observation.observation_date == "2023-10-02"
    assert observation.source_date == "2023/10/02"
    assert observation.values["institution"] == "外資及陸資"
    assert observation.values["open_interest_net"] == -7012
    assert observation.publication_label == "day:2023-10-02"
    assert observation.quality_status == "available"


def test_parse_range_payload_handles_multiple_dates_in_order() -> None:
    payload = range_payload(
        foreign_row("2023/10/02", net_oi=-7012),
        foreign_row("2023/10/03", net_oi=-6500),
    )

    observations = parse_institutional_futures_range_payload(payload)

    assert [o.observation_date for o in observations] == ["2023-10-02", "2023-10-03"]
    assert [o.values["open_interest_net"] for o in observations] == [-7012, -6500]


def test_parse_range_payload_rejects_unexpected_header() -> None:
    bad_payload = ("some,other,header\r\n" + foreign_row("2023/10/02") + "\r\n").encode(
        "cp950"
    )

    with pytest.raises(InstitutionalFuturesParseError, match="unexpected header"):
        parse_institutional_futures_range_payload(bad_payload)


def test_collect_range_is_idempotent_and_links_revision() -> None:
    with SQLiteObservationStore(":memory:") as store:
        first = collect_institutional_futures_range(
            store,
            date(2023, 10, 2),
            date(2023, 10, 2),
            http_post=lambda url, form: range_payload(foreign_row("2023/10/02")),
        )
        duplicate = collect_institutional_futures_range(
            store,
            date(2023, 10, 2),
            date(2023, 10, 2),
            http_post=lambda url, form: range_payload(foreign_row("2023/10/02")),
        )
        revised = collect_institutional_futures_range(
            store,
            date(2023, 10, 2),
            date(2023, 10, 2),
            http_post=lambda url, form: range_payload(
                foreign_row("2023/10/02", net_oi=-6500)
            ),
        )

    assert first[0].action == "inserted"
    assert duplicate[0].action == "duplicate"
    assert revised[0].action == "inserted"
