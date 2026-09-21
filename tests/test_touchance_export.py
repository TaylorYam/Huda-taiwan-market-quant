from pathlib import Path

import pytest

from src.data.touchance_export import (
    TouchanceExportError,
    parse_touchance_oi_export,
    parse_touchance_vix_export,
)


def test_parse_touchance_oi_export_calculates_net_and_accepts_tsv(tmp_path: Path):
    path = tmp_path / "oi.txt"
    path.write_text(
        "日期\t查詢時間\t外資多方未平倉\t外資空方未平倉\n"
        "2021/09/01\t161500\t12000\t15000\n"
        "2021/09/02\t161500\t13000\t14500\n",
        encoding="utf-8",
    )

    report = parse_touchance_oi_export(path)

    assert report["kind"] == "foreign_tx_oi"
    assert report["row_count"] == 2
    assert report["records"][0]["foreign_net_oi"] == -3000
    assert report["records"][0]["query_time"] == "161500"


def test_parse_touchance_oi_export_rejects_reported_net_mismatch(tmp_path: Path):
    path = tmp_path / "oi.csv"
    path.write_text(
        "date,foreign_long_oi,foreign_short_oi,foreign_net_oi\n"
        "2021-09-01,12000,15000,-2000\n",
        encoding="utf-8",
    )

    with pytest.raises(TouchanceExportError, match="net OI mismatch"):
        parse_touchance_oi_export(path)


def test_parse_touchance_vix_export_supports_cp950_and_duplicates(tmp_path: Path):
    path = tmp_path / "vix.txt"
    path.write_bytes(
        "日期,收盤\r\n2021/09/01,18.20\r\n2021/09/01,18.20\r\n".encode("cp950")
    )

    report = parse_touchance_vix_export(path)

    assert report["kind"] == "taiwan_vix"
    assert report["records"][0]["vix_close"] == 18.2
    assert report["duplicate_dates"] == ["2021-09-01"]
