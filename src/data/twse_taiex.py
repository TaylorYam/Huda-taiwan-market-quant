"""TWSE TAIEX monthly history client and parser."""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Callable, Mapping, Sequence
from datetime import date, datetime, timezone
from typing import Any
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .storage import Observation, ObservationStore, WriteResult

TAIEX_DATASET_ID = "twse_taiex_daily_v1"
TAIEX_SOURCE_NAME = "TWSE"
TAIEX_ENDPOINT = "https://www.twse.com.tw/indicesReport/MI_5MINS_HIST"
TAIEX_PARSER_VERSION = "twse-taiex-json@0.1"


class TAIEXFetchError(RuntimeError):
    """The official endpoint could not be fetched."""


class TAIEXParseError(ValueError):
    """The official response did not match the expected TAIEX schema."""


def build_taiex_month_url(year: int, month: int) -> str:
    """Build the official month query without making a network request."""
    _validate_month(year, month)
    query = urlencode({"date": f"{year:04d}{month:02d}01", "response": "json"})
    return f"{TAIEX_ENDPOINT}?{query}"


def payload_sha256(payload: bytes) -> str:
    """Return the canonical SHA-256 used by the observation contract."""
    return hashlib.sha256(payload).hexdigest()


def parse_taiex_payload(
    payload: bytes,
    *,
    source_url: str,
    source_payload_hash: str | None = None,
    retrieved_at: str | None = None,
    ingested_at: str | None = None,
    parser_version: str = TAIEX_PARSER_VERSION,
) -> list[Observation]:
    """Parse one TWSE monthly JSON response into daily observations."""
    try:
        document = json.loads(payload.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise TAIEXParseError("TAIEX response is not valid UTF-8 JSON") from exc
    if not isinstance(document, Mapping):
        raise TAIEXParseError("TAIEX response must be a JSON object")
    if document.get("stat") != "OK":
        raise TAIEXParseError(f"TAIEX response status is {document.get('stat')!r}")

    fields = document.get("fields")
    rows = document.get("data")
    if not isinstance(fields, Sequence) or isinstance(fields, (str, bytes)):
        raise TAIEXParseError("TAIEX response fields are missing")
    if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes)):
        raise TAIEXParseError("TAIEX response data rows are missing")
    if not rows:
        raise TAIEXParseError("TAIEX response contains no daily rows")
    indexes = _field_indexes(fields)

    computed_hash = payload_sha256(payload)
    if source_payload_hash is not None and source_payload_hash != computed_hash:
        raise TAIEXParseError("TAIEX source payload hash does not match response")
    payload_hash = source_payload_hash or computed_hash
    retrieved = retrieved_at or _utc_now()
    ingested = ingested_at or _utc_now()
    expected_month = _response_month(document)
    month_label = _month_label(rows)
    observations: list[Observation] = []
    seen_dates: set[str] = set()
    for row_number, row in enumerate(rows, start=1):
        if not isinstance(row, Sequence) or isinstance(row, (str, bytes)):
            raise TAIEXParseError(f"TAIEX row {row_number} is not an array")
        try:
            source_date = str(row[indexes["date"]]).strip()
            observation_date = _normalize_source_date(source_date)
            if observation_date[:7] != expected_month:
                raise TAIEXParseError(
                    f"TAIEX row {row_number} date {observation_date!r} "
                    f"is outside response month {expected_month}"
                )
            if observation_date in seen_dates:
                raise TAIEXParseError(
                    f"TAIEX row {row_number} repeats date {observation_date!r}"
                )
            seen_dates.add(observation_date)
            values = {
                "open": _parse_number(row[indexes["open"]], "open", row_number),
                "high": _parse_number(row[indexes["high"]], "high", row_number),
                "low": _parse_number(row[indexes["low"]], "low", row_number),
                "close": _parse_number(row[indexes["close"]], "close", row_number),
                "unit": "index_points",
            }
        except (IndexError, TypeError) as exc:
            raise TAIEXParseError(f"TAIEX row {row_number} is incomplete") from exc
        observations.append(
            Observation(
                dataset_id=TAIEX_DATASET_ID,
                schema_version="0.1",
                observation_date=observation_date,
                source_date=source_date,
                source_name=TAIEX_SOURCE_NAME,
                source_url=source_url,
                source_record_key="TAIEX",
                retrieved_at=retrieved,
                ingested_at=ingested,
                source_payload_hash=payload_hash,
                parser_version=parser_version,
                values=values,
                quality_status="available",
                publication_label=month_label,
            )
        )
    return observations


def fetch_taiex_month(
    year: int,
    month: int,
    *,
    http_get: Callable[[str], bytes] | None = None,
    parser_version: str = TAIEX_PARSER_VERSION,
) -> list[Observation]:
    """Fetch and parse one month; ``http_get`` is injectable for tests."""
    url = build_taiex_month_url(year, month)
    try:
        payload = (http_get or _http_get)(url)
    except Exception as exc:
        if isinstance(exc, TAIEXParseError):
            raise
        raise TAIEXFetchError(f"TAIEX request failed for {url}") from exc
    return parse_taiex_payload(
        payload,
        source_url=url,
        source_payload_hash=payload_sha256(payload),
        parser_version=parser_version,
    )


def collect_taiex_month(
    store: ObservationStore,
    year: int,
    month: int,
    *,
    http_get: Callable[[str], bytes] | None = None,
    parser_version: str = TAIEX_PARSER_VERSION,
) -> list[WriteResult]:
    """Fetch a month and persist each daily observation through the interface."""
    observations = fetch_taiex_month(
        year,
        month,
        http_get=http_get,
        parser_version=parser_version,
    )
    return [store.write_observation(observation) for observation in observations]


def collect_taiex_range(
    store: ObservationStore,
    start_year: int,
    start_month: int,
    end_year: int,
    end_month: int,
    *,
    http_get: Callable[[str], bytes] | None = None,
    parser_version: str = TAIEX_PARSER_VERSION,
) -> list[WriteResult]:
    """Backfill an inclusive range of calendar months in chronological order."""
    results: list[WriteResult] = []
    for year, month in _month_range(start_year, start_month, end_year, end_month):
        results.extend(
            collect_taiex_month(
                store,
                year,
                month,
                http_get=http_get,
                parser_version=parser_version,
            )
        )
    return results


def _field_indexes(fields: Sequence[Any]) -> dict[str, int]:
    aliases = {
        "date": {"日期", "Date"},
        "open": {"開盤指數", "Opening Index"},
        "high": {"最高指數", "Highest Index"},
        "low": {"最低指數", "Lowest Index"},
        "close": {"收盤指數", "Closing Index"},
    }
    indexes: dict[str, int] = {}
    for key, names in aliases.items():
        for index, field in enumerate(fields):
            if str(field).strip() in names:
                indexes[key] = index
                break
        if key not in indexes:
            raise TAIEXParseError(f"TAIEX field {key!r} is missing")
    return indexes


def _month_label(rows: Sequence[Any]) -> str:
    first = rows[0]
    if not isinstance(first, Sequence) or isinstance(first, (str, bytes)) or not first:
        raise TAIEXParseError("TAIEX response has no usable first row")
    raw_date = str(first[0]).strip().replace("-", "/")
    parts = raw_date.split("/")
    if len(parts) != 3 or not parts[1].isdigit():
        return "monthly"
    year = int(parts[0])
    if year < 1000:
        year += 1911
    return f"month:{year:04d}-{int(parts[1]):02d}"


def _response_month(document: Mapping[str, Any]) -> str:
    raw_date = document.get("date")
    if not isinstance(raw_date, str) or len(raw_date) < 6 or not raw_date[:6].isdigit():
        raise TAIEXParseError("TAIEX response month is missing or invalid")
    year, month = int(raw_date[:4]), int(raw_date[4:6])
    try:
        return f"{date(year, month, 1):%Y-%m}"
    except ValueError as exc:
        raise TAIEXParseError("TAIEX response month is invalid") from exc


def _month_range(
    start_year: int, start_month: int, end_year: int, end_month: int
) -> list[tuple[int, int]]:
    _validate_month(start_year, start_month)
    _validate_month(end_year, end_month)
    start = start_year * 12 + start_month - 1
    end = end_year * 12 + end_month - 1
    if start > end:
        raise ValueError("TAIEX range start must not be after end")
    return [(index // 12, index % 12 + 1) for index in range(start, end + 1)]


def _normalize_source_date(source_date: str) -> str:
    normalized = source_date.replace("-", "/")
    parts = normalized.split("/")
    if len(parts) != 3 or not all(part.isdigit() for part in parts):
        if len(source_date) == 8 and source_date.isdigit():
            parts = [source_date[:4], source_date[4:6], source_date[6:]]
        else:
            raise TAIEXParseError(f"unsupported TAIEX source date {source_date!r}")
    year, month, day = (int(part) for part in parts)
    if year < 1000:
        year += 1911
    try:
        return f"{date(year, month, day):%Y-%m-%d}"
    except ValueError as exc:
        raise TAIEXParseError(f"invalid TAIEX source date {source_date!r}") from exc


def _parse_number(value: Any, field_name: str, row_number: int) -> float:
    text = str(value).replace(",", "").strip()
    if not text or text in {"--", "-", "N/A"}:
        raise TAIEXParseError(
            f"TAIEX row {row_number} field {field_name} is unavailable"
        )
    try:
        number = float(text)
    except ValueError as exc:
        raise TAIEXParseError(
            f"TAIEX row {row_number} field {field_name} is not numeric"
        ) from exc
    if not math.isfinite(number):
        raise TAIEXParseError(
            f"TAIEX row {row_number} field {field_name} is not finite"
        )
    return number


def _validate_month(year: int, month: int) -> None:
    if year < 1999 or year > 9999 or month < 1 or month > 12:
        raise ValueError("TAIEX month must be between 1999-01 and 9999-12")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _http_get(url: str) -> bytes:
    request = Request(
        url, headers={"Accept": "application/json", "User-Agent": "HudaTaiwanQuant/0.1"}
    )
    try:
        with urlopen(request, timeout=30) as response:
            return response.read()
    except URLError as exc:
        raise TAIEXFetchError(f"TAIEX request failed for {url}") from exc
