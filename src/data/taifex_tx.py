"""TAIFEX TX annual ZIP parser and daily observation collector.

The official TX history endpoint returns one ZIP per calendar year.  A ZIP
contains one CSV with rows for the TX contract in each expiry month and
trading session.  This module turns those rows into the shared Observation
envelope without collapsing the expiry or session dimensions.
"""

from __future__ import annotations

import csv
import hashlib
import io
import math
import zipfile
from collections.abc import Callable, Mapping, Sequence
from dataclasses import replace
from datetime import date, datetime, timezone
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .storage import Observation, ObservationStore, WriteResult
from .taifex_tx_probe import (
    TX_ARCHIVE_ENDPOINT,
    TX_FIRST_ARCHIVE_YEAR,
    build_archive_form,
)

TX_DATASET_ID = "taifex_tx_daily_contract_v1"
TX_SOURCE_NAME = "TAIFEX"
TX_PARSER_VERSION = "taifex-tx-zip@0.1"


class TXFetchError(RuntimeError):
    """The official annual TX ZIP could not be fetched."""


class TXParseError(ValueError):
    """The official annual TX ZIP did not match the expected schema."""


def payload_sha256(payload: bytes) -> str:
    """Return the SHA-256 digest used by the observation contract."""

    return hashlib.sha256(payload).hexdigest()


def parse_tx_payload(
    year: int,
    payload: bytes,
    *,
    source_url: str = TX_ARCHIVE_ENDPOINT,
    source_payload_hash: str | None = None,
    retrieved_at: str | None = None,
    ingested_at: str | None = None,
    parser_version: str = TX_PARSER_VERSION,
) -> list[Observation]:
    """Parse one annual TX ZIP into daily contract observations."""

    _validate_year(year)
    computed_hash = payload_sha256(payload)
    if source_payload_hash is not None and source_payload_hash != computed_hash:
        raise TXParseError("TX source payload hash does not match response")
    payload_hash = source_payload_hash or computed_hash
    csv_name, csv_payload = _read_csv_from_zip(year, payload)
    text, _encoding = _decode_csv(csv_payload)
    rows = [
        row
        for row in csv.reader(io.StringIO(text))
        if any(cell.strip() for cell in row)
    ]
    if not rows:
        raise TXParseError(f"{year}: CSV has no rows")

    header = tuple(cell.strip() for cell in rows[0])
    indexes = _field_indexes(header, year)
    retrieved = retrieved_at or _utc_now()
    ingested = ingested_at or _utc_now()
    observations: list[Observation] = []
    seen_keys: set[tuple[str, str, str, str]] = set()
    for row_number, raw_row in enumerate(rows[1:], start=2):
        row = _trim_trailing_empty(raw_row)
        if len(row) == 1 and row[0].strip() in {"", "\x1a"}:
            continue
        if len(row) <= indexes["contract"]:
            raise TXParseError(f"{year}: row {row_number} is missing contract")
        if row[indexes["contract"]].strip() != "TX":
            continue
        try:
            source_date = row[indexes["date"]].strip()
            observation_date = _normalize_source_date(source_date, year, row_number)
            expiry = row[indexes["expiry"]].strip()
            if not expiry:
                raise TXParseError(f"{year}: row {row_number} has empty expiry")
            session = (
                row[indexes["session"]].strip()
                if indexes["session"] is not None and len(row) > indexes["session"]
                else ""
            )
            key = (observation_date, "TX", expiry, session)
            if key in seen_keys:
                raise TXParseError(
                    f"{year}: row {row_number} repeats key "
                    f"{observation_date}/{expiry}/{session or '<missing>'}"
                )
            seen_keys.add(key)
            values = {
                "open": _parse_optional_number(
                    row, indexes["open"], "open", year, row_number
                ),
                "high": _parse_optional_number(
                    row, indexes["high"], "high", year, row_number
                ),
                "low": _parse_optional_number(
                    row, indexes["low"], "low", year, row_number
                ),
                "close": _parse_optional_number(
                    row, indexes["close"], "close", year, row_number
                ),
                "settlement": _parse_optional_number(
                    row, indexes["settlement"], "settlement", year, row_number
                ),
                "volume": _parse_optional_number(
                    row, indexes["volume"], "volume", year, row_number, integer=True
                ),
                "open_interest": _parse_optional_number(
                    row,
                    indexes["open_interest"],
                    "open_interest",
                    year,
                    row_number,
                    integer=True,
                ),
                "price_unit": "index_points",
                "volume_unit": "contracts",
                "open_interest_unit": "contracts",
            }
        except IndexError as exc:
            raise TXParseError(f"{year}: row {row_number} is incomplete") from exc
        observations.append(
            Observation(
                dataset_id=TX_DATASET_ID,
                schema_version="0.1",
                observation_date=observation_date,
                source_date=source_date,
                source_name=TX_SOURCE_NAME,
                source_url=source_url,
                source_record_key=_record_key(expiry, session),
                retrieved_at=retrieved,
                ingested_at=ingested,
                source_payload_hash=payload_hash,
                parser_version=parser_version,
                values=values,
                quality_status="available"
                if values["close"] is not None
                else "invalid",
                quality_notes=(
                    None
                    if values["close"] is not None
                    else "Official TX row has no close price."
                ),
                publication_label=f"year:{year:04d}",
            )
        )
    if not observations:
        raise TXParseError(f"{year}: CSV contains no TX rows (file {csv_name!r})")
    return observations


def parse_tx_archive_payload(*args: Any, **kwargs: Any) -> list[Observation]:
    """Compatibility alias for callers that name the source as an archive."""

    return parse_tx_payload(*args, **kwargs)


def fetch_tx_year(
    year: int,
    *,
    http_post: Callable[[str, Mapping[str, str]], bytes] | None = None,
    parser_version: str = TX_PARSER_VERSION,
) -> list[Observation]:
    """Fetch and parse one official annual TX ZIP."""

    _validate_year(year)
    try:
        payload = (http_post or _http_post)(
            TX_ARCHIVE_ENDPOINT,
            build_archive_form(year),
        )
    except TXParseError:
        raise
    except Exception as exc:
        raise TXFetchError(f"TX request failed for year {year}") from exc
    if not isinstance(payload, bytes):
        raise TXFetchError("TX request returned a non-bytes payload")
    return parse_tx_payload(
        year,
        payload,
        source_payload_hash=payload_sha256(payload),
        parser_version=parser_version,
    )


def collect_tx_year(
    store: ObservationStore,
    year: int,
    *,
    http_post: Callable[[str, Mapping[str, str]], bytes] | None = None,
    parser_version: str = TX_PARSER_VERSION,
) -> list[WriteResult]:
    """Fetch one annual TX ZIP and persist its daily observations.

    A current-year ZIP changes as new trading days are published.  When the
    store supports ``list_revisions`` (the built-in SQLite and Supabase
    adapters do), changed rows are linked to the latest prior row so a daily
    rerun appends a revision instead of failing the storage contract.
    """

    observations = fetch_tx_year(
        year,
        http_post=http_post,
        parser_version=parser_version,
    )
    results: list[WriteResult] = []
    list_revisions = getattr(store, "list_revisions", None)
    for observation in observations:
        if callable(list_revisions):
            revisions = list_revisions(observation)
            if revisions and all(
                revision.source_payload_hash != observation.source_payload_hash
                for revision in revisions
            ):
                prior_id = _latest_revision_id(store, observation, revisions)
                if prior_id is not None:
                    observation = replace(observation, supersedes_id=prior_id)
        results.append(store.write_observation(observation))
    return results


def collect_tx_daily(*args: Any, **kwargs: Any) -> list[WriteResult]:
    """Compatibility alias for the daily collector entry point."""

    return collect_tx_year(*args, **kwargs)


def _read_csv_from_zip(year: int, payload: bytes) -> tuple[str, bytes]:
    try:
        archive = zipfile.ZipFile(io.BytesIO(payload))
    except zipfile.BadZipFile as exc:
        raise TXParseError(f"{year}: response is not a ZIP archive") from exc
    with archive:
        names = [name for name in archive.namelist() if not name.endswith("/")]
        csv_names = [name for name in names if name.lower().endswith(".csv")]
        if not csv_names:
            raise TXParseError(f"{year}: ZIP contains no CSV file")
        preferred = f"{year}_fut.csv".lower()
        csv_name = next(
            (
                name
                for name in csv_names
                if name.rsplit("/", 1)[-1].lower() == preferred
            ),
            csv_names[0],
        )
        return csv_name, archive.read(csv_name)


def _decode_csv(payload: bytes) -> tuple[str, str]:
    for encoding in ("cp950", "ms950", "utf-8-sig"):
        try:
            return payload.decode(encoding), encoding
        except UnicodeDecodeError:
            continue
    raise TXParseError("TX CSV is neither CP950/MS950 nor UTF-8")


def _field_indexes(header: Sequence[str], year: int) -> dict[str, int | None]:
    aliases: dict[str, set[str]] = {
        "date": {"交易日期", "日期", "Date"},
        "contract": {"契約", "Contract"},
        "expiry": {"到期月份(週別)", "到期月份", "Contract Month"},
        "session": {"交易時段", "盤別", "Trading Session", "Session"},
        "open": {"開盤價", "開盤", "Open"},
        "high": {"最高價", "最高", "High"},
        "low": {"最低價", "最低", "Low"},
        "close": {"收盤價", "收盤", "Close"},
        "settlement": {"結算價", "結算", "Settlement Price", "Settlement"},
        "volume": {"成交量", "Volume"},
        "open_interest": {"未沖銷契約數", "未平倉量", "Open Interest"},
    }
    indexes: dict[str, int | None] = {}
    for field, names in aliases.items():
        indexes[field] = next(
            (index for index, value in enumerate(header) if value.strip() in names),
            None,
        )
        if field != "session" and indexes[field] is None:
            raise TXParseError(f"{year}: CSV field {field!r} is missing")
    return indexes


def _normalize_source_date(source_date: str, year: int, row_number: int) -> str:
    parts = source_date.strip().replace("-", "/").split("/")
    if len(parts) != 3 or not all(part.isdigit() for part in parts):
        raise TXParseError(f"{year}: row {row_number} has invalid date {source_date!r}")
    parsed_year = int(parts[0])
    if parsed_year < 1000:
        parsed_year += 1911
    try:
        parsed = date(parsed_year, int(parts[1]), int(parts[2]))
    except ValueError as exc:
        raise TXParseError(
            f"{year}: row {row_number} has invalid date {source_date!r}"
        ) from exc
    if parsed.year != year:
        raise TXParseError(
            f"{year}: row {row_number} date {parsed.isoformat()} is outside annual archive"
        )
    return parsed.isoformat()


def _parse_number(
    row: Sequence[str],
    index: int | None,
    field_name: str,
    year: int,
    row_number: int,
    *,
    integer: bool = False,
) -> int | float:
    if index is None or len(row) <= index:
        raise TXParseError(f"{year}: row {row_number} is missing {field_name}")
    text = row[index].strip().replace(",", "")
    if not text or text in {"-", "--", "N/A"}:
        raise TXParseError(
            f"{year}: row {row_number} field {field_name} is unavailable"
        )
    try:
        number = float(text)
    except ValueError as exc:
        raise TXParseError(
            f"{year}: row {row_number} field {field_name} is not numeric"
        ) from exc
    if not math.isfinite(number):
        raise TXParseError(f"{year}: row {row_number} field {field_name} is not finite")
    if integer and not number.is_integer():
        raise TXParseError(
            f"{year}: row {row_number} field {field_name} is not an integer"
        )
    return int(number) if integer or number.is_integer() else number


def _parse_optional_number(
    row: Sequence[str],
    index: int | None,
    field_name: str,
    year: int,
    row_number: int,
    *,
    integer: bool = False,
) -> int | float | None:
    """Keep an official blank field as null instead of inventing a value."""

    if (
        index is None
        or len(row) <= index
        or row[index].strip() in {"", "-", "--", "N/A"}
    ):
        return None
    return _parse_number(row, index, field_name, year, row_number, integer=integer)


def _record_key(expiry: str, session: str) -> str:
    return f"TX:{expiry}:{session or '<missing>'}"


def _latest_revision_id(
    store: ObservationStore,
    observation: Observation,
    revisions: Sequence[Observation],
) -> int | None:
    """Resolve a revision ID from the built-in adapters' read boundaries."""

    # Observation deliberately contains no database ID.  SQLite and Supabase
    # expose their existing rows through private adapter details while the
    # public storage protocol remains source-oriented.
    connection = getattr(store, "_connection", None)
    if connection is not None:
        row = connection.execute(
            """
            SELECT id FROM observations
            WHERE dataset_id = ? AND observation_date = ?
              AND source_record_key = ?
              AND IFNULL(publication_label, '') = IFNULL(?, '')
            ORDER BY id DESC LIMIT 1
            """,
            (
                observation.dataset_id,
                observation.observation_date,
                observation.source_record_key,
                observation.publication_label,
            ),
        ).fetchone()
        if row is not None:
            return int(row[0])
    selector = getattr(store, "_select", None)
    if callable(selector):
        rows = selector(
            {
                "dataset_id": observation.dataset_id,
                "observation_date": observation.observation_date,
                "source_record_key": observation.source_record_key,
                "publication_label": observation.publication_label,
            },
            "id,source_payload_hash",
        )
        if rows:
            return int(rows[-1]["id"])
    return None


def _trim_trailing_empty(row: Sequence[str]) -> list[str]:
    values = list(row)
    while values and not values[-1].strip():
        values.pop()
    return values


def _validate_year(year: int) -> None:
    if year < TX_FIRST_ARCHIVE_YEAR or year > 9999:
        raise ValueError(
            f"TX archive year must be between {TX_FIRST_ARCHIVE_YEAR} and 9999"
        )


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _http_post(url: str, data: Mapping[str, str]) -> bytes:
    request = Request(
        url,
        data=urlencode(data).encode("ascii"),
        headers={
            "Accept": "application/zip,application/octet-stream",
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": "HudaTaiwanQuant/0.1",
        },
        method="POST",
    )
    with urlopen(request, timeout=60) as response:
        return response.read()


# Keep the source form visible in this module for callers that only import the
# collector rather than the read-only probe module.
__all__ = [
    "TX_ARCHIVE_ENDPOINT",
    "TX_DATASET_ID",
    "TX_PARSER_VERSION",
    "TX_SOURCE_NAME",
    "TXFetchError",
    "TXParseError",
    "build_archive_form",
    "collect_tx_daily",
    "collect_tx_year",
    "fetch_tx_year",
    "parse_tx_archive_payload",
    "parse_tx_payload",
    "payload_sha256",
]
