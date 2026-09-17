"""TWSE daily market turnover (FMTQIK) monthly report collector.

Used as the denominator for the foreign cash factor's 5-day ratio. Unlike
BFI82U, FMTQIK's own reported scope has not shown a documented mismatch, so
it carries no verified-start gate of its own; the foreign cash factor's gate
already bounds the window both series are actually combined over.
"""

from __future__ import annotations

import csv
import hashlib
import io
import math
import re
from collections.abc import Callable
from dataclasses import replace
from datetime import date, datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .storage import Observation, ObservationStore, WriteResult

MARKET_TURNOVER_DATASET_ID = "twse_market_turnover_fmtqik_v1"
MARKET_TURNOVER_SOURCE_NAME = "TWSE"
MARKET_TURNOVER_ENDPOINT = "https://www.twse.com.tw/exchangeReport/FMTQIK"
MARKET_TURNOVER_PARSER_VERSION = "twse-market-turnover-csv@0.1"
MARKET_TURNOVER_SOURCE_RECORD_KEY = "FMTQIK:market"

_TITLE_MONTH = re.compile(r"(?P<year>\d+)年(?P<month>\d+)月")
_EXPECTED_HEADER = {"日期", "成交股數", "成交金額", "成交筆數"}


class MarketTurnoverFetchError(RuntimeError):
    """The official FMTQIK endpoint could not be fetched."""


class MarketTurnoverParseError(ValueError):
    """The official FMTQIK response did not match the expected schema."""


def build_market_turnover_month_url(year: int, month: int) -> str:
    """Build the official month query without making a network request."""

    _validate_month(year, month)
    query = urlencode({"date": f"{year:04d}{month:02d}01", "response": "csv"})
    return f"{MARKET_TURNOVER_ENDPOINT}?{query}"


def payload_sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def parse_market_turnover_payload(
    payload: bytes,
    *,
    source_url: str,
    source_payload_hash: str | None = None,
    retrieved_at: str | None = None,
    ingested_at: str | None = None,
    parser_version: str = MARKET_TURNOVER_PARSER_VERSION,
    expected_month: str | None = None,
) -> list[Observation]:
    """Parse one monthly FMTQIK CSV report into daily turnover observations."""

    computed_hash = payload_sha256(payload)
    if source_payload_hash is not None and source_payload_hash != computed_hash:
        raise MarketTurnoverParseError(
            "market turnover payload hash does not match response"
        )
    payload_hash = source_payload_hash or computed_hash
    retrieved = retrieved_at or _utc_now()
    ingested = ingested_at or _utc_now()
    try:
        text = payload.decode("cp950")
    except UnicodeDecodeError as exc:
        raise MarketTurnoverParseError(
            "market turnover response is not valid CP950 text"
        ) from exc
    rows = [row for row in csv.reader(io.StringIO(text)) if row and any(row)]
    if not rows:
        raise MarketTurnoverParseError("market turnover response has no rows")

    response_month = _parse_title_month(rows[0][0] if rows[0] else "")
    if expected_month is not None and f"{response_month:%Y-%m}" != expected_month:
        raise MarketTurnoverParseError(
            f"market turnover response month {response_month:%Y-%m} does not "
            f"match requested month {expected_month}"
        )
    header = {cell.strip() for cell in rows[1]} if len(rows) > 1 else set()
    if not _EXPECTED_HEADER.issubset(header):
        raise MarketTurnoverParseError(
            "market turnover response has an unexpected header"
        )

    observations: list[Observation] = []
    seen_dates: set[str] = set()
    month_label = f"month:{response_month:%Y-%m}"
    for row_number, row in enumerate(rows[2:], start=3):
        if len(row) < 3 or not row[0].strip():
            continue
        source_date = row[0].strip()
        observation_date = _normalize_roc_date(source_date, row_number)
        if observation_date[:7] != f"{response_month:%Y-%m}":
            raise MarketTurnoverParseError(
                f"market turnover row {row_number} date {observation_date!r} "
                f"is outside response month {response_month:%Y-%m}"
            )
        if observation_date in seen_dates:
            raise MarketTurnoverParseError(
                f"market turnover row {row_number} repeats date {observation_date!r}"
            )
        seen_dates.add(observation_date)
        turnover = _parse_amount(row[2], "turnover", row_number)
        observations.append(
            Observation(
                dataset_id=MARKET_TURNOVER_DATASET_ID,
                schema_version="0.1",
                observation_date=observation_date,
                source_date=source_date,
                source_name=MARKET_TURNOVER_SOURCE_NAME,
                source_url=source_url,
                source_record_key=MARKET_TURNOVER_SOURCE_RECORD_KEY,
                retrieved_at=retrieved,
                ingested_at=ingested,
                source_payload_hash=payload_hash,
                parser_version=parser_version,
                values={"turnover": turnover, "unit": "TWD"},
                quality_status="available",
                publication_label=month_label,
            )
        )
    if not observations:
        raise MarketTurnoverParseError(
            "market turnover response contains no daily rows"
        )
    return observations


def fetch_market_turnover_month(
    year: int,
    month: int,
    *,
    http_get: Callable[[str], bytes] | None = None,
    parser_version: str = MARKET_TURNOVER_PARSER_VERSION,
) -> list[Observation]:
    """Fetch and parse one month; ``http_get`` is injectable for tests."""

    url = build_market_turnover_month_url(year, month)
    try:
        payload = (http_get or _http_get)(url)
    except Exception as exc:
        if isinstance(exc, MarketTurnoverParseError):
            raise
        raise MarketTurnoverFetchError(
            f"market turnover request failed for {url}"
        ) from exc
    return parse_market_turnover_payload(
        payload,
        source_url=url,
        source_payload_hash=payload_sha256(payload),
        parser_version=parser_version,
        expected_month=f"{year:04d}-{month:02d}",
    )


def collect_market_turnover_month(
    store: ObservationStore,
    year: int,
    month: int,
    *,
    http_get: Callable[[str], bytes] | None = None,
    parser_version: str = MARKET_TURNOVER_PARSER_VERSION,
) -> list[WriteResult]:
    """Fetch a month and persist each daily observation through the interface."""

    observations = fetch_market_turnover_month(
        year, month, http_get=http_get, parser_version=parser_version
    )
    results: list[WriteResult] = []
    for observation in observations:
        previous_id = _latest_observation_id(store, observation)
        if previous_id is not None:
            observation = replace(observation, supersedes_id=previous_id)
        results.append(store.write_observation(observation))
    return results


def _parse_title_month(title: str) -> date:
    match = _TITLE_MONTH.search(title)
    if match is None:
        raise MarketTurnoverParseError(
            f"unrecognized market turnover report title {title!r}"
        )
    year = int(match["year"])
    if year < 1000:
        year += 1911
    try:
        return date(year, int(match["month"]), 1)
    except ValueError as exc:
        raise MarketTurnoverParseError(
            f"invalid market turnover report month in title {title!r}"
        ) from exc


def _normalize_roc_date(value: str, row_number: int) -> str:
    parts = value.split("/")
    if len(parts) != 3 or not all(part.isdigit() for part in parts):
        raise MarketTurnoverParseError(
            f"market turnover row {row_number} has unsupported date {value!r}"
        )
    year = int(parts[0])
    if year < 1000:
        year += 1911
    try:
        return date(year, int(parts[1]), int(parts[2])).isoformat()
    except ValueError as exc:
        raise MarketTurnoverParseError(
            f"market turnover row {row_number} has invalid date {value!r}"
        ) from exc


def _parse_amount(raw: str, field: str, row_number: int) -> float:
    text = raw.strip()
    if text == "" or text in {"-", "--", "N/A"}:
        raise MarketTurnoverParseError(
            f"market turnover row {row_number} field {field!r} is unavailable"
        )
    try:
        value = float(text.replace(",", ""))
    except ValueError as exc:
        raise MarketTurnoverParseError(
            f"market turnover row {row_number} field {field!r} is not numeric"
        ) from exc
    if not math.isfinite(value):
        raise MarketTurnoverParseError(
            f"market turnover row {row_number} field {field!r} is not finite"
        )
    return value


def _latest_observation_id(
    store: ObservationStore, observation: Observation
) -> int | None:
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
        return None if row is None else int(row[0])
    select = getattr(store, "_select", None)
    if callable(select):
        rows = select(
            {
                "dataset_id": observation.dataset_id,
                "observation_date": observation.observation_date,
                "source_record_key": observation.source_record_key,
                "publication_label": observation.publication_label,
            },
            "id",
        )
        if rows:
            return max(int(row["id"]) for row in rows)
    return None


def _validate_month(year: int, month: int) -> None:
    if year < 1990 or year > 9999 or month < 1 or month > 12:
        raise ValueError("market turnover month must be between 1990-01 and 9999-12")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _http_get(url: str) -> bytes:
    request = Request(
        url,
        headers={"Accept": "text/csv,text/plain", "User-Agent": "HudaTaiwanQuant/0.1"},
    )
    try:
        with urlopen(request, timeout=30) as response:
            return response.read()
    except (HTTPError, URLError, OSError) as exc:
        raise MarketTurnoverFetchError("market turnover request failed") from exc


__all__ = [
    "MARKET_TURNOVER_DATASET_ID",
    "MARKET_TURNOVER_ENDPOINT",
    "MARKET_TURNOVER_PARSER_VERSION",
    "MARKET_TURNOVER_SOURCE_NAME",
    "MARKET_TURNOVER_SOURCE_RECORD_KEY",
    "MarketTurnoverFetchError",
    "MarketTurnoverParseError",
    "build_market_turnover_month_url",
    "collect_market_turnover_month",
    "fetch_market_turnover_month",
    "parse_market_turnover_payload",
    "payload_sha256",
]
