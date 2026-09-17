from __future__ import annotations

from datetime import date

from src.data.storage import SQLiteObservationStore
from src.data.taifex_pcr import (
    PCR_DATASET_ID,
    collect_pcr_day,
    fetch_pcr_day,
    parse_pcr_payload,
)
from src.data.taifex_pcr_probe import PCRWindow


def sample_payload() -> bytes:
    return (
        "日期,賣權成交量,買權成交量,買賣權成交量比率%,賣權未平倉量,買權未平倉量,買賣權未平倉量比率%\r\n"
        "2026/09/15,172547,162102,106.44,81556,94956,85.89,\r\n"
    ).encode("ms950")


def test_parser_builds_available_daily_observation_and_preserves_source_date():
    observations = parse_pcr_payload(sample_payload(), date(2026, 9, 15))
    observation = observations[0]

    assert observation.dataset_id == PCR_DATASET_ID
    assert observation.observation_date == "2026-09-15"
    assert observation.source_date == "2026/09/15"
    assert observation.quality_status == "available"
    assert observation.values["put_oi"] == 81556.0
    assert observation.values["call_oi"] == 94956.0
    assert observation.values["oi_pcr"] == 81556 / 94956


def test_header_only_response_is_stored_as_source_empty():
    payload = "日期,賣權成交量,買權成交量,買賣權成交量比率%,賣權未平倉量,買權未平倉量,買賣權未平倉量比率%\n".encode(
        "ms950"
    )
    observations = parse_pcr_payload(payload, date(2026, 9, 20))
    observation = observations[0]

    assert observation.quality_status == "source_empty"
    assert observation.values == {}
    assert observation.source_date == "2026/09/20"


def test_fetch_uses_one_day_canonical_window():
    windows: list[PCRWindow] = []

    def post(window: PCRWindow) -> bytes:
        windows.append(window)
        return sample_payload()

    observations = fetch_pcr_day(date(2026, 9, 15), http_post=post)

    assert windows == [PCRWindow(date(2026, 9, 15), date(2026, 9, 15))]
    assert observations[0].observation_date == "2026-09-15"


def test_collector_is_idempotent_and_links_source_revision():
    payloads = [sample_payload(), sample_payload().replace(b"81556", b"81557")]

    def post(window: PCRWindow) -> bytes:
        del window
        return payloads.pop(0)

    with SQLiteObservationStore(":memory:") as store:
        first = collect_pcr_day(store, date(2026, 9, 15), http_post=post)
        duplicate = collect_pcr_day(
            store, date(2026, 9, 15), http_post=lambda window: sample_payload()
        )
        revised = collect_pcr_day(store, date(2026, 9, 15), http_post=post)

        assert first[0].action == "inserted"
        assert duplicate[0].action == "duplicate"
        assert revised[0].action == "inserted"
        assert (
            store.get_observation(revised[0].observation_id).supersedes_id
            == first[0].observation_id
        )
