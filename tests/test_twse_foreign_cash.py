from __future__ import annotations

from datetime import date

import pytest

from src.data import (
    ForeignCashParseError,
    SQLiteObservationStore,
    collect_foreign_cash_day,
    parse_foreign_cash_payload,
)
from src.data.twse_foreign_cash import (
    FOREIGN_CASH_VERIFIED_START,
    build_foreign_cash_day_url,
)


def modern_payload(net: str = "-36,963,571,856") -> bytes:
    lines = [
        '"115年09月14日 三大法人買賣金額統計表"',
        '"單位名稱","買進金額","賣出金額","買賣差額",',
        '"自營商(自行買賣)","5,878,730,505","9,857,183,925","-3,978,453,420",',
        '"自營商(避險)","21,261,160,728","32,375,418,926","-11,114,258,198",',
        '"投信","16,619,233,322","12,923,730,780","3,695,502,542",',
        f'"外資及陸資(不含外資自營商)","236,359,477,681","273,323,049,537","{net}",',
        '"外資自營商","0","0","0",',
        '"合計","280,118,602,236","328,479,383,168","-48,360,780,932",',
        '"說明:"',
        '"因外資自營商買賣金額已計入自營商買賣金額，故不納入三大法人買賣金額之合計數計算。"',
        '"本統計資訊含一般、零股、盤後定價、鉅額，不含拍賣、標購。"',
    ]
    return ("\r\n".join(lines) + "\r\n").encode("cp950")


def legacy_2008_payload() -> bytes:
    lines = [
        '"097年06月05日 三大法人買賣金額統計表"',
        '"單位名稱","買進金額","賣出金額","買賣差額",',
        '"自營商","4,518,585,070","3,005,273,530","1,513,311,540",',
        '"投信","2,644,292,870","2,305,919,152","338,373,718",',
        '"外資","29,823,627,041","32,238,887,556","-2,415,260,515",',
        '"合計","36,986,504,981","37,550,080,238","-563,575,257",',
        '"說明:"',
        '"本統計資訊含一般、零股、盤後定價、鉅額，不含拍賣、標購。"',
    ]
    return ("\r\n".join(lines) + "\r\n").encode("cp950")


def test_build_url_rejects_dates_before_verified_start():
    with pytest.raises(ValueError, match="2010-01-01"):
        build_foreign_cash_day_url(date(2004, 4, 7))


def test_parse_modern_payload_selects_foreign_row_excluding_dealer_split():
    [observation] = parse_foreign_cash_payload(modern_payload())

    assert observation.observation_date == "2026-09-14"
    assert observation.values["net_buy_sell"] == -36963571856.0
    assert observation.values["category"] == "外資及陸資(不含外資自營商)"
    assert observation.quality_status == "available"


def test_parse_legacy_2008_payload_uses_plain_foreign_label():
    [observation] = parse_foreign_cash_payload(legacy_2008_payload())

    assert observation.observation_date == "2008-06-05"
    assert observation.values["net_buy_sell"] == -2415260515.0
    assert observation.values["category"] == "外資"


def test_parse_rejects_response_with_no_foreign_row():
    bad = (
        '"115年09月14日 三大法人買賣金額統計表"\r\n'
        '"單位名稱","買進金額","賣出金額","買賣差額",\r\n'
        '"自營商","1","2","-1",\r\n'
    ).encode("cp950")

    with pytest.raises(ForeignCashParseError, match="no matching foreign investor row"):
        parse_foreign_cash_payload(bad)


def test_parse_rejects_mismatched_expected_date():
    with pytest.raises(ForeignCashParseError, match="does not match"):
        parse_foreign_cash_payload(modern_payload(), expected_date=date(2026, 9, 15))


def test_collect_is_idempotent_and_links_revision():
    with SQLiteObservationStore(":memory:") as store:
        first = collect_foreign_cash_day(
            store, date(2026, 9, 14), http_get=lambda _: modern_payload()
        )
        duplicate = collect_foreign_cash_day(
            store, date(2026, 9, 14), http_get=lambda _: modern_payload()
        )
        revised = collect_foreign_cash_day(
            store,
            date(2026, 9, 14),
            http_get=lambda _: modern_payload("-1,000,000,000"),
        )

    assert first[0].action == "inserted"
    assert duplicate[0].action == "duplicate"
    assert revised[0].action == "inserted"


def test_verified_start_constant_matches_documented_buffer():
    assert FOREIGN_CASH_VERIFIED_START == date(2010, 1, 1)
