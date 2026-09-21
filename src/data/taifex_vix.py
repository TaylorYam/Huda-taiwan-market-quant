"""TAIFEX free daily VIX close files and observation collector."""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Callable
from dataclasses import replace
from datetime import date, datetime, time, timezone
from urllib.error import URLError
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from .storage import Observation, ObservationStore, WriteResult

VIX_DATASET_ID = "taifex_taiwan_vix_close_v1"
VIX_SOURCE_NAME = "TAIFEX"
VIX_ENDPOINT = "https://www.taifex.com.tw/file/taifex/Dailydownload/vix/log2data/"
VIX_PARSER_VERSION = "taifex-vix-txt@0.1"
TAIWAN_TIMEZONE = ZoneInfo("Asia/Taipei")

# Historical backfill path. The log2data monthly files above only cover a
# rolling ~3-4 month window; this is the JSON API behind the 指數專區 chart's
# own "3年" range picker, which serves a genuine rolling ~3-year window
# instead (confirmed 2026-09-17: a 2023-10 query returned real daily closes,
# a 2010-01 query returned an empty series rather than an error). Because
# the window rolls forward with the current date, delaying a backfill
# permanently loses its older end.
VIX_RANGE_ENDPOINT = "https://www.taifex.com.tw/indes/index.aspx/GetStockDayPrices"
VIX_RANGE_PARSER_VERSION = "taifex-vix-range-json@0.1"
VIX_RANGE_SERIES_ID = "TAIWANVIX"
VIX_RANGE_FLAG = "MS"


class VIXFetchError(RuntimeError):
    """The official VIX monthly file could not be fetched."""


class VIXParseError(ValueError):
    """The official VIX monthly file did not match the expected schema."""


def build_vix_month_url(year: int, month: int) -> str:
    """Build the official monthly VIX close-file URL."""

    _validate_month(year, month)
    return f"{VIX_ENDPOINT}{year:04d}{month:02d}new.txt"


def payload_sha256(payload: bytes) -> str:
    """Return the source payload SHA-256 used by the observation contract."""

    return hashlib.sha256(payload).hexdigest()


def parse_vix_payload(
    payload: bytes,
    *,
    source_url: str,
    source_payload_hash: str | None = None,
    retrieved_at: str | None = None,
    ingested_at: str | None = None,
    parser_version: str = VIX_PARSER_VERSION,
    expected_month: str | None = None,
) -> list[Observation]:
    """Parse one monthly tab-separated VIX close file into observations."""

    try:
        text = payload.decode("cp950")
    except UnicodeDecodeError as exc:
        raise VIXParseError("VIX response is not valid CP950 text") from exc

    computed_hash = payload_sha256(payload)
    if source_payload_hash is not None and source_payload_hash != computed_hash:
        raise VIXParseError("VIX source payload hash does not match response")
    payload_hash = source_payload_hash or computed_hash
    retrieved = retrieved_at or _utc_now()
    ingested = ingested_at or _utc_now()
    records: list[Observation] = []
    seen_dates: set[str] = set()
    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        columns = [column.strip() for column in line.split("\t")]
        if line_number <= 2 and not columns[0].isdigit():
            continue
        if len(columns) not in {4, 7}:
            raise VIXParseError(
                f"VIX row {line_number} must contain four or seven tab-separated columns"
            )
        source_date, source_time = columns[:2]
        close_text, average_text = (
            (columns[2], columns[3]) if len(columns) == 4 else (columns[4], columns[6])
        )
        observation_date = _normalize_source_date(source_date, line_number)
        if expected_month is not None and observation_date[:7] != expected_month:
            raise VIXParseError(
                f"VIX row {line_number} date {observation_date!r} "
                f"is outside requested month {expected_month}"
            )
        if observation_date in seen_dates:
            raise VIXParseError(
                f"VIX row {line_number} repeats date {observation_date!r}"
            )
        seen_dates.add(observation_date)
        effective_at = _effective_timestamp(observation_date, source_time, line_number)
        close = _parse_number(close_text, "close", line_number)
        close_1m_avg = _parse_number(average_text, "close_1m_avg", line_number)
        records.append(
            Observation(
                dataset_id=VIX_DATASET_ID,
                schema_version="0.1",
                observation_date=observation_date,
                source_date=source_date,
                source_name=VIX_SOURCE_NAME,
                source_url=source_url,
                source_record_key="VIX",
                retrieved_at=retrieved,
                ingested_at=ingested,
                source_payload_hash=payload_hash,
                parser_version=parser_version,
                values={
                    "close": close,
                    "close_1m_avg": close_1m_avg,
                    "unit": "index_points",
                    "source_time": source_time,
                },
                quality_status="available",
                publication_label=f"month:{observation_date[:7]}",
                effective_at=effective_at,
            )
        )
    if not records:
        raise VIXParseError("VIX response contains no daily rows")
    return records


def fetch_vix_month(
    year: int,
    month: int,
    *,
    http_get: Callable[[str], bytes] | None = None,
    parser_version: str = VIX_PARSER_VERSION,
) -> list[Observation]:
    """Fetch and parse one VIX monthly file."""

    url = build_vix_month_url(year, month)
    try:
        payload = (http_get or _http_get)(url)
    except Exception as exc:
        if isinstance(exc, VIXParseError):
            raise
        raise VIXFetchError(f"VIX request failed for {url}") from exc
    return parse_vix_payload(
        payload,
        source_url=url,
        source_payload_hash=payload_sha256(payload),
        parser_version=parser_version,
        expected_month=f"{year:04d}-{month:02d}",
    )


def collect_vix_month(
    store: ObservationStore,
    year: int,
    month: int,
    *,
    http_get: Callable[[str], bytes] | None = None,
    parser_version: str = VIX_PARSER_VERSION,
) -> list[WriteResult]:
    """Fetch one VIX month and persist its daily observations."""

    observations = fetch_vix_month(
        year,
        month,
        http_get=http_get,
        parser_version=parser_version,
    )
    results: list[WriteResult] = []
    for observation in observations:
        previous_id = _latest_month_observation_id(store, observation)
        if previous_id is not None:
            observation = replace(observation, supersedes_id=previous_id)
        results.append(store.write_observation(observation))
    return results


def parse_vix_range_payload(
    payload: bytes,
    *,
    source_url: str = VIX_RANGE_ENDPOINT,
    source_payload_hash: str | None = None,
    retrieved_at: str | None = None,
    ingested_at: str | None = None,
    parser_version: str = VIX_RANGE_PARSER_VERSION,
) -> list[Observation]:
    """Parse the chart API's date-range JSON response into daily closes.

    The endpoint reports only a daily close (``Price``); it does not provide
    the log2data files' close-before-last-minute average, so
    ``close_1m_avg`` is intentionally absent from these rows rather than
    filled with a placeholder. Nothing downstream reads that field.
    """

    computed_hash = payload_sha256(payload)
    if source_payload_hash is not None and source_payload_hash != computed_hash:
        raise VIXParseError("VIX range payload hash does not match response")
    payload_hash = source_payload_hash or computed_hash
    retrieved = retrieved_at or _utc_now()
    ingested = ingested_at or _utc_now()
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise VIXParseError("VIX range response is not valid UTF-8 JSON") from exc
    try:
        outer = json.loads(text)
        inner = json.loads(outer["d"])
        trend = inner["TrendData"]
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        raise VIXParseError("VIX range response has an unexpected shape") from exc
    if not isinstance(trend, list):
        raise VIXParseError("VIX range TrendData is not a list")

    records: list[Observation] = []
    seen_dates: set[str] = set()
    for index, point in enumerate(trend):
        if not isinstance(point, dict):
            raise VIXParseError(f"VIX range point {index} is not an object")
        source_date = str(point.get("Time", "")).strip()
        observation_date = _normalize_source_date(source_date, index)
        if observation_date in seen_dates:
            raise VIXParseError(
                f"VIX range point {index} repeats date {observation_date!r}"
            )
        seen_dates.add(observation_date)
        close = _parse_number(str(point.get("Price", "")), "close", index)
        records.append(
            Observation(
                dataset_id=VIX_DATASET_ID,
                schema_version="0.1",
                observation_date=observation_date,
                source_date=source_date,
                source_name=VIX_SOURCE_NAME,
                source_url=source_url,
                source_record_key="VIX",
                retrieved_at=retrieved,
                ingested_at=ingested,
                source_payload_hash=payload_hash,
                parser_version=parser_version,
                values={"close": close, "unit": "index_points"},
                quality_status="available",
                publication_label=f"day:{observation_date}",
            )
        )
    return records


def fetch_vix_range(
    start: date,
    end: date,
    *,
    http_post: Callable[[str, str], bytes] | None = None,
    parser_version: str = VIX_RANGE_PARSER_VERSION,
) -> list[Observation]:
    """Fetch and parse daily VIX closes for a date range.

    ``start``/``end`` must fall inside the source's own rolling window
    (roughly the most recent three years); a range entirely outside it
    returns zero rows rather than an error.
    """

    if start > end:
        raise ValueError("start must not be after end")
    body = json.dumps(
        {
            "syid": VIX_RANGE_SERIES_ID,
            "flag": VIX_RANGE_FLAG,
            "startDate": start.strftime("%Y/%m/%d"),
            "endDate": end.strftime("%Y/%m/%d"),
        }
    )
    try:
        payload = (http_post or _http_post_json)(VIX_RANGE_ENDPOINT, body)
    except Exception as exc:
        if isinstance(exc, VIXParseError):
            raise
        raise VIXFetchError(
            f"VIX range request failed for {VIX_RANGE_ENDPOINT}"
        ) from exc
    return parse_vix_range_payload(
        payload,
        source_payload_hash=payload_sha256(payload),
        parser_version=parser_version,
    )


def collect_vix_range(
    store: ObservationStore,
    start: date,
    end: date,
    *,
    http_post: Callable[[str, str], bytes] | None = None,
    parser_version: str = VIX_RANGE_PARSER_VERSION,
) -> list[WriteResult]:
    """Fetch a date range once and persist it with revision lineage."""

    observations = fetch_vix_range(
        start, end, http_post=http_post, parser_version=parser_version
    )
    batch_writer = getattr(store, "write_observations", None)
    if callable(batch_writer):
        return batch_writer(observations)
    results: list[WriteResult] = []
    for observation in observations:
        previous_id = _latest_range_observation_id(store, observation)
        if previous_id is not None:
            observation = replace(observation, supersedes_id=previous_id)
        results.append(store.write_observation(observation))
    return results


def _latest_range_observation_id(
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


def _latest_month_observation_id(
    store: ObservationStore, observation: Observation
) -> int | None:
    """Find the latest row for a monthly-file observation identity."""

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


def _normalize_source_date(source_date: str, line_number: int) -> str:
    if len(source_date) != 8 or not source_date.isdigit():
        raise VIXParseError(
            f"VIX row {line_number} has unsupported date {source_date!r}"
        )
    try:
        return date(
            int(source_date[:4]), int(source_date[4:6]), int(source_date[6:])
        ).isoformat()
    except ValueError as exc:
        raise VIXParseError(
            f"VIX row {line_number} has invalid date {source_date!r}"
        ) from exc


def _effective_timestamp(
    observation_date: str, source_time: str, line_number: int
) -> str:
    if len(source_time) != 8 or not source_time.isdigit():
        raise VIXParseError(
            f"VIX row {line_number} has unsupported time {source_time!r}"
        )
    try:
        parsed = time(
            int(source_time[:2]),
            int(source_time[2:4]),
            int(source_time[4:6]),
            int(source_time[6:]) * 1000,
        )
    except ValueError as exc:
        raise VIXParseError(
            f"VIX row {line_number} has invalid time {source_time!r}"
        ) from exc
    return datetime.combine(
        date.fromisoformat(observation_date), parsed, tzinfo=TAIWAN_TIMEZONE
    ).isoformat(timespec="milliseconds")


def _parse_number(value: str, field_name: str, line_number: int) -> float:
    if not value or value in {"-", "--", "N/A"}:
        raise VIXParseError(f"VIX row {line_number} field {field_name} is unavailable")
    try:
        number = float(value.replace(",", ""))
    except ValueError as exc:
        raise VIXParseError(
            f"VIX row {line_number} field {field_name} is not numeric"
        ) from exc
    if not math.isfinite(number):
        raise VIXParseError(f"VIX row {line_number} field {field_name} is not finite")
    return number


def _validate_month(year: int, month: int) -> None:
    if year < 2007 or year > 9999 or month < 1 or month > 12:
        raise ValueError("VIX month must be between 2007-01 and 9999-12")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _http_get(url: str) -> bytes:
    request = Request(
        url,
        headers={
            "Accept": "text/plain",
            "User-Agent": "HudaTaiwanQuant/0.1",
        },
    )
    try:
        with urlopen(request, timeout=30) as response:
            return response.read()
    except URLError as exc:
        raise VIXFetchError(f"VIX request failed for {url}") from exc


def _http_post_json(url: str, body: str) -> bytes:
    request = Request(
        url,
        data=body.encode("utf-8"),
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json; charset=utf-8",
            "User-Agent": "HudaTaiwanQuant/0.1",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=30) as response:
            return response.read()
    except URLError as exc:
        raise VIXFetchError(f"VIX range request failed for {url}") from exc


__all__ = [
    "VIX_DATASET_ID",
    "VIX_ENDPOINT",
    "VIX_PARSER_VERSION",
    "VIX_RANGE_ENDPOINT",
    "VIX_RANGE_PARSER_VERSION",
    "VIXFetchError",
    "VIXParseError",
    "build_vix_month_url",
    "collect_vix_month",
    "collect_vix_range",
    "fetch_vix_month",
    "fetch_vix_range",
    "parse_vix_payload",
    "parse_vix_range_payload",
    "payload_sha256",
]
