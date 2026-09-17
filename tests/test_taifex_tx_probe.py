from __future__ import annotations

import csv
import io
import zipfile

import pytest

from src.data import (
    TXArchiveParseError,
    audit_tx_archives,
    iter_archive_years,
    parse_tx_archive,
)


def archive_payload(year: int = 2024, date_header: str = "交易日期") -> bytes:
    header = [
        date_header,
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
            "2024/01/02",
            "TX",
            "202401",
            "1",
            "2",
            "0",
            "1",
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
            "2024/01/02",
            "TX",
            "202401",
            "1",
            "2",
            "0",
            "1",
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
            "盤後",
            "",
        ],
        [
            "2024/01/02",
            "TXO",
            "202401",
            "1",
            "2",
            "0",
            "1",
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


def test_parser_handles_cp950_and_session_in_identity():
    result = parse_tx_archive(2024, archive_payload())

    assert result.encoding == "cp950"
    assert result.tx_row_count == 2
    assert result.tx_date_count == 1
    assert result.session_counts == {"一般": 1, "盤後": 1}
    assert result.duplicate_key_count == 0
    assert result.positive_volume_date_count == 1


def test_year_planner_is_inclusive():
    assert list(iter_archive_years(1998, 2000)) == [1998, 1999, 2000]
    with pytest.raises(ValueError):
        list(iter_archive_years(1997, 1998))


def test_audit_report_keeps_year_errors_separate():
    report = audit_tx_archives(
        2024, 2025, lambda year: archive_payload(year) if year == 2024 else b"bad"
    )

    assert report["planned_year_count"] == 2
    assert report["completed_year_count"] == 1
    assert report["error_year_count"] == 1
    assert report["archives"][1]["year"] == 2025
    assert "not a ZIP" in report["archives"][1]["error"]


def test_archive_rejects_missing_required_fields():
    payload = archive_payload(date_header="日期")
    with pytest.raises(TXArchiveParseError, match="field 'date'"):
        parse_tx_archive(2024, payload)
