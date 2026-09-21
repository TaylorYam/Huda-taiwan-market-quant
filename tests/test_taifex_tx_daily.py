from datetime import date

from src.data.storage import SQLiteObservationStore
from src.data.taifex_tx_daily import (
    TX_DAILY_ENDPOINT,
    build_daily_form,
    collect_tx_day,
    fetch_tx_day,
    parse_tx_daily_payload,
)


def daily_payload() -> bytes:
    return b"""
    <html><body>
      <table>
        <tr><th>\xe5\x9c\x96</th><th>\xe5\x88\xb0\xe6\x9c\x9f\xe6\x9c\x88\xe4\xbb\xbd</th><th>Open</th><th>High</th><th>Low</th><th>Last</th><th>Change</th><th>%</th><th>NightVolume</th><th>DayVolume</th><th>TotalVolume</th><th>Settlement</th><th>OpenInterest</th></tr>
        <tr><td>TX</td><td>202610</td><td>46,495</td><td>47,037</td><td>46,376</td><td>46,445</td><td>385</td><td>0.84%</td><td>32,283</td><td>50,102</td><td>82,385</td><td>46,459</td><td>99,476</td></tr>
      </table>
    </body></html>
    """


def test_parser_keeps_general_session_and_basis_fields() -> None:
    observations = parse_tx_daily_payload(
        date(2026, 9, 17), daily_payload(), retrieved_at="2026-09-17T00:00:00+00:00"
    )

    assert len(observations) == 1
    observation = observations[0]
    assert observation.source_record_key == "TX:202610:一般"
    assert observation.observation_date == "2026-09-17"
    assert observation.values["close"] == 46445
    assert observation.values["volume"] == 50102
    assert observation.values["open_interest"] == 99476
    assert observation.publication_label == "daily:2026-09-17:一般"


def test_build_daily_form_uses_official_date_fields() -> None:
    assert build_daily_form(date(2026, 9, 17)) == {
        "queryType": "2",
        "marketCode": "0",
        "dateaddcnt": "",
        "commodity_id": "TX",
        "commodity_id2": "",
        "queryDate": "2026/09/17",
        "MarketCode": "0",
    }


def test_fetch_daily_posts_requested_date() -> None:
    calls: list[tuple[str, dict[str, str]]] = []

    def post(url: str, data: dict[str, str]) -> bytes:
        calls.append((url, data))
        return daily_payload()

    observations = fetch_tx_day(date(2026, 9, 17), http_post=post)

    assert len(observations) == 1
    assert calls == [(TX_DAILY_ENDPOINT, build_daily_form(date(2026, 9, 17)))]


def test_fetch_daily_retries_transient_request_failure() -> None:
    attempts = 0

    def post(url: str, data: dict[str, str]) -> bytes:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise OSError("temporary connection reset")
        return daily_payload()

    observations = fetch_tx_day(date(2026, 9, 17), http_post=post, retry_delay=0)

    assert len(observations) == 1
    assert attempts == 2


def test_empty_daily_table_is_a_non_trading_day() -> None:
    assert (
        parse_tx_daily_payload(
            date(2026, 9, 19), b"<html><table><tr><td>none</td></tr></table></html>"
        )
        == []
    )


def test_collector_is_idempotent_for_same_daily_payload() -> None:
    payload = daily_payload()
    with SQLiteObservationStore(":memory:") as store:
        first = collect_tx_day(
            store, date(2026, 9, 17), http_post=lambda _url, _data: payload
        )
        duplicate = collect_tx_day(
            store, date(2026, 9, 17), http_post=lambda _url, _data: payload
        )

    assert [result.action for result in first] == ["inserted"]
    assert [result.action for result in duplicate] == ["duplicate"]


def test_collector_links_changed_daily_payload_as_revision() -> None:
    with SQLiteObservationStore(":memory:") as store:
        first = collect_tx_day(
            store,
            date(2026, 9, 17),
            http_post=lambda _url, _data: daily_payload(),
        )
        revised_payload = daily_payload().replace(b"46,445", b"46,446")
        revised = collect_tx_day(
            store,
            date(2026, 9, 17),
            http_post=lambda _url, _data: revised_payload,
        )
        current = store.get_observation(revised[0].observation_id)

    assert revised[0].action == "inserted"
    assert current is not None
    assert current.supersedes_id == first[0].observation_id
    assert current.values["close"] == 46446
