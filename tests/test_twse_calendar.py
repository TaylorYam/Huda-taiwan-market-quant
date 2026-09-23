from datetime import date

import pytest
import requests

from src.automation.twse_calendar import (
    TWSE_HOLIDAY_CALENDAR_URL,
    fetch_twse_closed_dates,
    parse_twse_closed_dates,
)


def test_parse_twse_calendar_distinguishes_holidays_from_special_open_days() -> None:
    payload = {
        "stat": "ok",
        "fields": ["日期", "名稱", "說明"],
        "data": [
            ["2026-09-28", "孔子誕辰紀念日/教師節", "依規定放假1日。"],
            ["2026-09-25", "中秋節", "依規定放假1日。"],
            ["2026-02-27", "和平紀念日", "2月28日適逢星期六，於2月27日補假。"],
            ["2026-02-23", "農曆春節後開始交易日", "農曆春節後開始交易。"],
            ["2026-02-11", "農曆春節前最後交易日", "農曆春節前最後交易。"],
            ["2026-02-15", "農曆除夕及春節", "依規定放假1日。"],
        ],
    }

    assert parse_twse_closed_dates(payload, year=2026) == frozenset(
        {date(2026, 9, 28), date(2026, 9, 25), date(2026, 2, 27)}
    )


def test_parse_twse_openapi_roc_date_and_no_trading_label() -> None:
    payload = [
        {
            "Date": "1150212",
            "Name": "市場無交易，僅辦理結算交割作業",
            "Description": "",
        },
        {
            "Date": "1150102",
            "Name": "國曆新年開始交易日",
            "Description": "國曆新年開始交易。",
        },
    ]

    assert parse_twse_closed_dates(payload, year=2026) == frozenset({date(2026, 2, 12)})


def test_parse_twse_calendar_fails_closed_for_unknown_weekday_label() -> None:
    payload = {
        "stat": "ok",
        "fields": ["日期", "名稱", "說明"],
        "data": [["2026-09-28", "臨時調整日", "請留意公告。"]],
    }

    with pytest.raises(ValueError, match="unknown weekday label"):
        parse_twse_closed_dates(payload, year=2026)


def test_parse_twse_calendar_rejects_unrequested_year() -> None:
    payload = [{"Date": "1140101", "Name": "中華民國開國紀念日", "Description": "放假"}]

    with pytest.raises(ValueError, match="outside 2026"):
        parse_twse_closed_dates(payload, year=2026)


class FakeResponse:
    def __init__(self, year: int) -> None:
        self.year = year

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return {
            "stat": "ok",
            "fields": ["日期", "名稱", "說明"],
            "data": [
                [
                    f"{self.year}-09-29" if self.year == 2025 else "2026-09-28",
                    "教師節",
                    "依規定放假1日。",
                ]
            ],
        }


class FakeSession:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict, dict, int]] = []

    def get(
        self, url: str, *, params: dict, headers: dict, timeout: int
    ) -> FakeResponse:
        self.calls.append((url, params, headers, timeout))
        return FakeResponse(params["queryYear"] + 1911)


def test_fetch_twse_calendar_requests_each_year() -> None:
    session = FakeSession()

    assert fetch_twse_closed_dates({2025, 2026}, session=session) == frozenset(
        {date(2025, 9, 29), date(2026, 9, 28)}
    )

    assert session.calls == [
        (
            TWSE_HOLIDAY_CALENDAR_URL,
            {"response": "json", "queryYear": 114},
            {"Accept": "application/json", "User-Agent": "HudaTaiwanQuant/0.1"},
            15,
        ),
        (
            TWSE_HOLIDAY_CALENDAR_URL,
            {"response": "json", "queryYear": 115},
            {"Accept": "application/json", "User-Agent": "HudaTaiwanQuant/0.1"},
            15,
        ),
    ]


def test_fetch_twse_calendar_wraps_network_failures() -> None:
    class BrokenSession:
        @staticmethod
        def get(url: str, *, params: dict, headers: dict, timeout: int) -> None:
            raise requests.Timeout("private transport detail")

    with pytest.raises(RuntimeError, match="request failed for 2026") as error:
        fetch_twse_closed_dates({2026}, session=BrokenSession())

    assert "private transport detail" not in str(error.value)
