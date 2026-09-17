from __future__ import annotations

import csv
import io
import zipfile

import pytest

from src.data.storage import SQLiteObservationStore
from src.data.taifex_tx import (
    TXParseError,
    collect_tx_year,
    fetch_tx_year,
    parse_tx_payload,
)


def archive_payload(
    year: int = 2024, *, close: str = "1", second_session: str = "盤後"
) -> bytes:
    header = [
        "交易日期",
        "契約",
        "到期月份(週別)",
        "開盤價",
        "最高價",
        "最低價",
        "收盤價",
        "漲跌價",
        "漲跌%",
        "成交量",
        "結算價",
        "未沖銷契約數",
        "最後最佳買價",
        "最後最佳賣價",
        "歷史最高價",
        "歷史最低價",
        "是否因訊息面暫停交易",
        "交易時段",
        "價差對單式委託成交量",
    ]
    rows = [
        [
            f"{year}/01/02",
            "TX",
            "202401",
            "1",
            "2",
            "0",
            close,
            "0",
            "0",
            "10",
            "1",
            "20",
            "1",
            "1",
            "2",
            "0",
            "",
            "一般",
            "",
        ],
        [
            f"{year}/01/02",
            "TX",
            "202401",
            "1",
            "2",
            "0",
            close,
            "0",
            "0",
            "11",
            "1",
            "20",
            "1",
            "1",
            "2",
            "0",
            "",
            second_session,
            "",
        ],
        [
            f"{year}/01/02",
            "TXO",
            "202401",
            "1",
            "2",
            "0",
            close,
            "0",
            "0",
            "10",
            "1",
            "20",
            "1",
            "1",
            "2",
            "0",
            "",
            "一般",
            "",
        ],
    ]
    output = io.StringIO()
    csv.writer(output, lineterminator="\r\n").writerows([header, *rows, ["\x1a"]])
    payload = io.BytesIO()
    with zipfile.ZipFile(payload, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(f"{year}_fut.csv", output.getvalue().encode("cp950"))
    return payload.getvalue()


def test_parser_keeps_expiry_and_session_dimensions():
    observations = parse_tx_payload(
        2024,
        archive_payload(),
        retrieved_at="2026-09-16T00:00:00+00:00",
        ingested_at="2026-09-16T00:00:00+00:00",
    )

    assert len(observations) == 2
    assert [item.source_record_key for item in observations] == [
        "TX:202401:一般",
        "TX:202401:盤後",
    ]
    assert observations[0].observation_date == "2024-01-02"
    assert observations[0].source_date == "2024/01/02"
    assert observations[0].values["volume"] == 10
    assert observations[0].values["open_interest"] == 20
    assert observations[0].publication_label == "year:2024"


def test_fetch_posts_verified_annual_form():
    calls: list[tuple[str, dict[str, str]]] = []
    payload = archive_payload()

    def post(url: str, data: dict[str, str]) -> bytes:
        calls.append((url, data))
        return payload

    observations = fetch_tx_year(2024, http_post=post)

    assert len(observations) == 2
    assert calls == [
        (
            "https://www.taifex.com.tw/cht/3/futDataDown",
            {"down_type": "2", "his_year": "2024"},
        )
    ]


def test_collector_is_idempotent_for_same_annual_payload():
    payload = archive_payload()
    with SQLiteObservationStore(":memory:") as store:
        first = collect_tx_year(store, 2024, http_post=lambda _url, _data: payload)
        second = collect_tx_year(store, 2024, http_post=lambda _url, _data: payload)

    assert [result.action for result in first] == ["inserted", "inserted"]
    assert [result.action for result in second] == ["duplicate", "duplicate"]


def test_collector_links_changed_annual_payload_as_revision():
    with SQLiteObservationStore(":memory:") as store:
        first = collect_tx_year(
            store, 2024, http_post=lambda _url, _data: archive_payload(close="1")
        )
        revised = collect_tx_year(
            store, 2024, http_post=lambda _url, _data: archive_payload(close="2")
        )
        previous = store.get_observation(first[0].observation_id)
        current = store.get_observation(revised[0].observation_id)

    assert previous is not None
    assert current is not None
    assert revised[0].action == "inserted"
    assert current.supersedes_id == first[0].observation_id
    assert current.values["close"] == 2


def test_parser_rejects_duplicate_dimension_key():
    payload = archive_payload(second_session="一般")
    with pytest.raises(TXParseError, match="repeats key"):
        parse_tx_payload(2024, payload)
