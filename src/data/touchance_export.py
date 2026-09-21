"""Read-only validation helpers for TOUCHANCE/MultiCharts text exports."""

from __future__ import annotations

import csv
import io
import re
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any


class TouchanceExportError(ValueError):
    """Raised when a TOUCHANCE export cannot be mapped to the expected schema."""


def _read_text(path: Path) -> str:
    raw = path.read_bytes()
    for encoding in ("utf-8-sig", "cp950", "big5", "utf-8"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise TouchanceExportError(f"could not decode export: {path}")


def _delimiter(text: str) -> str:
    sample = "\n".join(text.splitlines()[:10])
    try:
        return csv.Sniffer().sniff(sample, delimiters=",\t;|").delimiter
    except csv.Error:
        counts = {delimiter: sample.count(delimiter) for delimiter in ("\t", ",", ";", "|")}
        return max(counts, key=counts.get) if max(counts.values()) else ","


def _header_key(value: str) -> str:
    return re.sub(r"[\s_\-:/()（）\[\]【】]+", "", value.strip().lower())


def _rows(path: Path) -> list[dict[str, str]]:
    text = _read_text(path)
    reader = csv.DictReader(io.StringIO(text), delimiter=_delimiter(text))
    if not reader.fieldnames:
        raise TouchanceExportError("export must contain a header row")
    headers = [field.strip() for field in reader.fieldnames if field]
    if not headers:
        raise TouchanceExportError("export header is empty")
    normalized = {_header_key(field): field for field in headers}
    rows: list[dict[str, str]] = []
    for row in reader:
        if not any((value or "").strip() for value in row.values()):
            continue
        rows.append({key: (row.get(source) or "").strip() for key, source in normalized.items()})
    return rows


def _field(row: dict[str, str], *names: str, required: bool = True) -> str | None:
    for name in names:
        value = row.get(_header_key(name), "")
        if value:
            return value
    if required:
        raise TouchanceExportError(
            f"missing required field; expected one of: {', '.join(names)}"
        )
    return None


def _parse_date(value: str) -> str:
    compact = re.sub(r"[^0-9]", "", value)
    if len(compact) == 8:
        parsed = date(int(compact[:4]), int(compact[4:6]), int(compact[6:8]))
    elif len(compact) == 7 and compact.startswith("1"):
        parsed = date(
            int(compact[:3]) + 1911,
            int(compact[3:5]),
            int(compact[5:7]),
        )
    else:
        raise TouchanceExportError(f"unsupported date value: {value!r}")
    return parsed.isoformat()


def _number(value: str, *, integer: bool = False) -> float | int:
    cleaned = value.replace(",", "").replace(" ", "")
    try:
        parsed = float(cleaned)
    except ValueError as exc:
        raise TouchanceExportError(f"invalid numeric value: {value!r}") from exc
    if integer:
        if not parsed.is_integer():
            raise TouchanceExportError(f"expected integer value: {value!r}")
        return int(parsed)
    return parsed


def _summary(records: list[dict[str, Any]], *, kind: str) -> dict[str, Any]:
    dates = [record["date"] for record in records]
    counts = Counter(dates)
    return {
        "kind": kind,
        "row_count": len(records),
        "unique_date_count": len(counts),
        "duplicate_dates": sorted(date_value for date_value, count in counts.items() if count > 1),
        "earliest_date": min(dates) if dates else None,
        "latest_date": max(dates) if dates else None,
        "records": records,
    }


def parse_touchance_oi_export(path: str | Path) -> dict[str, Any]:
    """Parse foreign TX open-interest rows without writing to any store."""

    rows = _rows(Path(path))
    records: list[dict[str, Any]] = []
    for row in rows:
        long_oi = int(_number(_field(row, "foreign_long_oi", "外資多方未平倉", "外資多單口數"), integer=True))
        short_oi = int(_number(_field(row, "foreign_short_oi", "外資空方未平倉", "外資空單口數"), integer=True))
        net_text = _field(row, "foreign_net_oi", "外資淨未平倉", "淨未平倉", required=False)
        net_oi = int(_number(net_text, integer=True)) if net_text else long_oi - short_oi
        if net_oi != long_oi - short_oi:
            raise TouchanceExportError(
                f"net OI mismatch on {_field(row, 'date', '日期')}: "
                f"reported={net_oi}, calculated={long_oi - short_oi}"
            )
        records.append(
            {
                "date": _parse_date(_field(row, "date", "trade_date", "日期")),
                "query_time": _field(row, "query_time", "查詢時間", required=False),
                "foreign_long_oi": long_oi,
                "foreign_short_oi": short_oi,
                "foreign_net_oi": net_oi,
            }
        )
    return _summary(records, kind="foreign_tx_oi")


def parse_touchance_vix_export(path: str | Path) -> dict[str, Any]:
    """Parse a TOUCHANCE VIX daily-close export without writing to any store."""

    rows = _rows(Path(path))
    records: list[dict[str, Any]] = []
    for row in rows:
        close = float(_number(_field(row, "vix_close", "close", "收盤", "VIX")))
        records.append(
            {
                "date": _parse_date(_field(row, "date", "trade_date", "日期")),
                "vix_close": close,
            }
        )
    return _summary(records, kind="taiwan_vix")
