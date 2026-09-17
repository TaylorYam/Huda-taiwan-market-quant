"""Read-only TAIFEX annual TX ZIP inventory and schema audit helpers."""

from __future__ import annotations

import csv
import hashlib
import io
import math
import zipfile
from collections import Counter
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any

TX_ARCHIVE_ENDPOINT = "https://www.taifex.com.tw/cht/3/futDataDown"
TX_FIRST_ARCHIVE_YEAR = 1998


class TXArchiveParseError(ValueError):
    """An annual TAIFEX ZIP did not match the expected daily schema."""


@dataclass(frozen=True)
class TXArchive:
    """A downloaded annual archive with its parsed TX evidence."""

    year: int
    zip_sha256: str
    zip_size_bytes: int
    csv_name: str
    csv_sha256: str
    csv_size_bytes: int
    encoding: str
    header: tuple[str, ...]
    row_column_counts: dict[str, int]
    tx_row_count: int
    tx_date_count: int
    tx_min_date: str | None
    tx_max_date: str | None
    positive_volume_date_count: int | None
    duplicate_key_count: int
    session_counts: dict[str, int]

    def as_dict(self) -> dict[str, Any]:
        return {
            "year": self.year,
            "zip_sha256": self.zip_sha256,
            "zip_size_bytes": self.zip_size_bytes,
            "csv_name": self.csv_name,
            "csv_sha256": self.csv_sha256,
            "csv_size_bytes": self.csv_size_bytes,
            "encoding": self.encoding,
            "header": list(self.header),
            "row_column_counts": self.row_column_counts,
            "tx_row_count": self.tx_row_count,
            "tx_date_count": self.tx_date_count,
            "tx_min_date": self.tx_min_date,
            "tx_max_date": self.tx_max_date,
            "positive_volume_date_count": self.positive_volume_date_count,
            "duplicate_key_count": self.duplicate_key_count,
            "session_counts": self.session_counts,
        }


def build_archive_form(year: int) -> dict[str, str]:
    """Return the official annual ZIP form fields."""

    if year < TX_FIRST_ARCHIVE_YEAR:
        raise ValueError(f"TX archive year must be >= {TX_FIRST_ARCHIVE_YEAR}")
    return {"down_type": "2", "his_year": str(year)}


def iter_archive_years(start_year: int, end_year: int) -> Iterator[int]:
    """Yield an inclusive annual range."""

    if start_year > end_year:
        raise ValueError("TX archive start year must not be after end year")
    if start_year < TX_FIRST_ARCHIVE_YEAR:
        raise ValueError(f"TX archive year must be >= {TX_FIRST_ARCHIVE_YEAR}")
    yield from range(start_year, end_year + 1)


def parse_tx_archive(year: int, payload: bytes) -> TXArchive:
    """Parse one annual ZIP and summarize TX daily rows."""

    zip_sha256 = hashlib.sha256(payload).hexdigest()
    try:
        archive = zipfile.ZipFile(io.BytesIO(payload))
    except zipfile.BadZipFile as exc:
        raise TXArchiveParseError(f"{year}: response is not a ZIP archive") from exc
    with archive:
        names = [name for name in archive.namelist() if not name.endswith("/")]
        csv_names = [name for name in names if name.lower().endswith(".csv")]
        if not csv_names:
            raise TXArchiveParseError(f"{year}: ZIP contains no CSV file")
        preferred_name = f"{year}_fut.csv".lower()
        csv_name = next(
            (
                name
                for name in csv_names
                if name.rsplit("/", 1)[-1].lower() == preferred_name
            ),
            csv_names[0],
        )
        csv_payload = archive.read(csv_name)

    text, encoding = _decode_csv(csv_payload)
    rows = [
        row
        for row in csv.reader(io.StringIO(text))
        if any(cell.strip() for cell in row)
    ]
    if not rows:
        raise TXArchiveParseError(f"{year}: CSV has no rows")
    header = tuple(cell.strip() for cell in rows[0])
    indexes = _field_indexes(header, year)
    tx_rows: list[tuple[list[str], date, tuple[str, ...]]] = []
    row_column_counts = Counter()
    for row_number, raw_row in enumerate(rows[1:], start=2):
        row = _trim_trailing_empty(raw_row)
        row_column_counts[str(len(raw_row))] += 1
        if len(row) == 1 and row[0].strip() in {"", "\x1a"}:
            continue
        if len(row) <= indexes["contract"]:
            raise TXArchiveParseError(f"{year}: row {row_number} is missing contract")
        if row[indexes["contract"]].strip() != "TX":
            continue
        try:
            parsed_date = _parse_source_date(row[indexes["date"]])
        except ValueError as exc:
            raise TXArchiveParseError(
                f"{year}: row {row_number} has invalid date {row[indexes['date']]!r}"
            ) from exc
        expiry = row[indexes["expiry"]].strip()
        session = (
            row[indexes["session"]].strip() if indexes["session"] is not None else ""
        )
        key = (parsed_date.isoformat(), "TX", expiry, session)
        tx_rows.append((row, parsed_date, key))

    dates = [parsed_date for _, parsed_date, _ in tx_rows]
    keys = [key for _, _, key in tx_rows]
    positive_dates = _positive_volume_dates(tx_rows, indexes.get("volume"))
    session_counts = Counter(key[3] or "<missing>" for key in keys)
    return TXArchive(
        year=year,
        zip_sha256=zip_sha256,
        zip_size_bytes=len(payload),
        csv_name=csv_name,
        csv_sha256=hashlib.sha256(csv_payload).hexdigest(),
        csv_size_bytes=len(csv_payload),
        encoding=encoding,
        header=header,
        row_column_counts=dict(sorted(row_column_counts.items())),
        tx_row_count=len(tx_rows),
        tx_date_count=len(set(dates)),
        tx_min_date=min(dates).isoformat() if dates else None,
        tx_max_date=max(dates).isoformat() if dates else None,
        positive_volume_date_count=len(positive_dates)
        if indexes.get("volume") is not None
        else None,
        duplicate_key_count=len(keys) - len(set(keys)),
        session_counts=dict(sorted(session_counts.items())),
    )


def audit_tx_archives(
    start_year: int,
    end_year: int,
    fetch: Callable[[int], bytes],
) -> dict[str, Any]:
    """Audit every requested annual archive and return JSON evidence."""

    started_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    archives: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    years = list(iter_archive_years(start_year, end_year))
    for year in years:
        try:
            archives.append(parse_tx_archive(year, fetch(year)).as_dict())
        except Exception as exc:  # noqa: BLE001 - preserve one failure per year
            errors.append({"year": str(year), "error": str(exc)})
            archives.append({"year": year, "error": str(exc)})
    return {
        "audit_started_at": started_at,
        "requested_start_year": start_year,
        "requested_end_year": end_year,
        "planned_year_count": len(years),
        "completed_year_count": len(years) - len(errors),
        "error_year_count": len(errors),
        "errors": errors,
        "archives": archives,
    }


def _decode_csv(payload: bytes) -> tuple[str, str]:
    for encoding in ("cp950", "ms950", "utf-8-sig"):
        try:
            return payload.decode(encoding), encoding
        except UnicodeDecodeError:
            continue
    raise TXArchiveParseError("CSV is neither CP950/MS950 nor UTF-8")


def _parse_source_date(value: str) -> date:
    parts = value.strip().replace("-", "/").split("/")
    if len(parts) != 3 or not all(part.isdigit() for part in parts):
        raise ValueError(f"invalid date {value!r}")
    return date(int(parts[0]), int(parts[1]), int(parts[2]))


def _field_indexes(header: Sequence[str], year: int) -> dict[str, int | None]:
    aliases = {
        "date": {"交易日期", "Date"},
        "contract": {"契約", "Contract"},
        "expiry": {"到期月份(週別)", "到期月份", "Contract Month"},
        "session": {"交易時段", "Trading Session"},
        "volume": {"成交量", "Volume"},
    }
    indexes: dict[str, int | None] = {}
    for field, names in aliases.items():
        indexes[field] = next(
            (index for index, value in enumerate(header) if value.strip() in names),
            None,
        )
        if field in {"date", "contract", "expiry"} and indexes[field] is None:
            raise TXArchiveParseError(f"{year}: CSV field {field!r} is missing")
    return indexes


def _positive_volume_dates(
    rows: Sequence[tuple[list[str], date, tuple[str, ...]]], volume_index: int | None
) -> set[date]:
    if volume_index is None:
        return set()
    positive: set[date] = set()
    for row, observation_date, _ in rows:
        if len(row) <= volume_index:
            continue
        value = row[volume_index].strip().replace(",", "")
        if value in {"", "-", "--"}:
            continue
        try:
            if math.isfinite(float(value)) and float(value) > 0:
                positive.add(observation_date)
        except ValueError:
            continue
    return positive


def _trim_trailing_empty(row: Sequence[str]) -> list[str]:
    values = list(row)
    while values and not values[-1].strip():
        values.pop()
    return values


__all__ = [
    "TX_ARCHIVE_ENDPOINT",
    "TX_FIRST_ARCHIVE_YEAR",
    "TXArchive",
    "TXArchiveParseError",
    "audit_tx_archives",
    "build_archive_form",
    "iter_archive_years",
    "parse_tx_archive",
]
