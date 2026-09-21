"""TAIFEX daily foreign futures open-interest snapshot collector."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import time
from collections.abc import Callable, Mapping
from dataclasses import replace
from datetime import date, datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .storage import Observation, ObservationStore, WriteResult

INSTITUTIONAL_FUTURES_DATASET_ID = "taifex_institutional_futures_oi_v1"
INSTITUTIONAL_FUTURES_ENDPOINT = (
    "https://openapi.taifex.com.tw/v1/"
    "MarketDataOfMajorInstitutionalTradersDetailsOfFuturesContractsBytheDate"
)
INSTITUTIONAL_FUTURES_PARSER_VERSION = "taifex-institutional-futures-oi-json@0.2"
INSTITUTIONAL_FUTURES_SOURCE_NAME = "TAIFEX"
INSTITUTIONAL_FUTURES_SOURCE_RECORD_KEY = "TX:foreign:institutional"

# Historical backfill path. Unlike INSTITUTIONAL_FUTURES_ENDPOINT (OpenAPI,
# latest snapshot only, no date parameter), this is the website's date-range
# download form. It only serves a rolling window of roughly the most recent
# three years (the page's own client-side check read as of 2026-09-17:
# 2023/09/17-2026/09/17). A request outside that window returns an HTML
# error page instead of CSV, which surfaces here as
# InstitutionalFuturesParseError rather than an empty result -- confirmed
# 2026-09-17 against both the exact boundary date and a date years earlier.
# Because the window rolls forward with the current date, delaying a
# backfill permanently loses its older end.
INSTITUTIONAL_FUTURES_RANGE_ENDPOINT = (
    "https://www.taifex.com.tw/cht/3/futContractsDateDown"
)
INSTITUTIONAL_FUTURES_RANGE_PARSER_VERSION = (
    "taifex-institutional-futures-oi-range-csv@0.1"
)
_RANGE_INSTITUTIONS = {"外資及陸資", "外資"}


class InstitutionalFuturesFetchError(RuntimeError):
    """The official TAIFEX institutional futures endpoint failed."""


class InstitutionalFuturesParseError(ValueError):
    """The official TAIFEX institutional futures payload was invalid."""


def payload_sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def parse_institutional_futures_payload(
    payload: bytes,
    *,
    source_url: str = INSTITUTIONAL_FUTURES_ENDPOINT,
    source_payload_hash: str | None = None,
    retrieved_at: str | None = None,
    ingested_at: str | None = None,
    parser_version: str = INSTITUTIONAL_FUTURES_PARSER_VERSION,
) -> list[Observation]:
    """Parse the latest official snapshot into the TX foreign OI row."""

    computed_hash = payload_sha256(payload)
    if source_payload_hash is not None and source_payload_hash != computed_hash:
        raise InstitutionalFuturesParseError(
            "institutional futures payload hash does not match response"
        )
    raw_rows = _decode_institutional_json(payload)
    if not isinstance(raw_rows, list):
        raise InstitutionalFuturesParseError(
            "institutional futures response is not a list"
        )

    candidates = [
        row
        for row in raw_rows
        if isinstance(row, Mapping)
        and str(row.get("ContractCode", "")).strip() in {"臺股期貨", "TX"}
        and str(row.get("Item", "")).strip() in {"外資及陸資", "外資"}
    ]
    if len(candidates) != 1:
        raise InstitutionalFuturesParseError(
            "expected exactly one foreign TX futures row in official snapshot"
        )
    row = candidates[0]
    source_date = str(row.get("Date", "")).strip()
    observation_date = _normalize_date(source_date)
    values = {
        "contract_code": str(row.get("ContractCode", "臺股期貨")).strip(),
        "institution": str(row.get("Item", "")).strip(),
        "trading_volume_long": _number(row, "TradingVolume(Long)"),
        "trading_volume_short": _number(row, "TradingVolume(Short)"),
        "trading_volume_net": _number(row, "TradingVolume(Net)"),
        "open_interest_long": _number(row, "OpenInterest(Long)"),
        "open_interest_short": _number(row, "OpenInterest(Short)"),
        "open_interest_net": _number(row, "OpenInterest(Net)"),
        "open_interest_net_value_thousands": _number(
            row, "ContractValueofOpenInterest(Net)(Thousands)"
        ),
        "unit": "contracts",
    }
    return [
        Observation(
            dataset_id=INSTITUTIONAL_FUTURES_DATASET_ID,
            schema_version="0.1",
            observation_date=observation_date,
            source_date=source_date,
            source_name=INSTITUTIONAL_FUTURES_SOURCE_NAME,
            source_url=source_url,
            source_record_key=INSTITUTIONAL_FUTURES_SOURCE_RECORD_KEY,
            retrieved_at=retrieved_at or _utc_now(),
            ingested_at=ingested_at or _utc_now(),
            source_payload_hash=source_payload_hash or computed_hash,
            parser_version=parser_version,
            values=values,
            quality_status="available",
            publication_label="latest",
        )
    ]


def fetch_institutional_futures_latest(
    *,
    http_get: Callable[[str], bytes] | None = None,
    parser_version: str = INSTITUTIONAL_FUTURES_PARSER_VERSION,
    sleep: Callable[[float], None] | None = None,
) -> list[Observation]:
    """Fetch and parse the latest official daily snapshot."""

    getter = http_get or _http_get
    pause = sleep or time.sleep
    retry_delays = (1.0, 3.0)
    for attempt in range(len(retry_delays) + 1):
        try:
            payload = getter(INSTITUTIONAL_FUTURES_ENDPOINT)
            if not isinstance(payload, bytes):
                raise InstitutionalFuturesFetchError(
                    "institutional futures response is not bytes"
                )
            return parse_institutional_futures_payload(
                payload,
                source_payload_hash=payload_sha256(payload),
                parser_version=parser_version,
            )
        except InstitutionalFuturesParseError:
            if attempt == len(retry_delays):
                raise
        except Exception as exc:
            if attempt == len(retry_delays):
                raise InstitutionalFuturesFetchError(
                    "institutional futures snapshot request failed"
                ) from exc
        pause(retry_delays[attempt])
    raise AssertionError("institutional futures retry loop did not return")


def collect_institutional_futures_latest(
    store: ObservationStore,
    *,
    http_get: Callable[[str], bytes] | None = None,
    parser_version: str = INSTITUTIONAL_FUTURES_PARSER_VERSION,
) -> list[WriteResult]:
    """Fetch the latest snapshot and persist it with revision lineage."""

    observations = fetch_institutional_futures_latest(
        http_get=http_get,
        parser_version=parser_version,
    )
    results: list[WriteResult] = []
    for observation in observations:
        previous_id = _latest_observation_id(store, observation)
        if previous_id is not None:
            observation = replace(observation, supersedes_id=previous_id)
        results.append(store.write_observation(observation))
    return results


def parse_institutional_futures_range_payload(
    payload: bytes,
    *,
    source_url: str = INSTITUTIONAL_FUTURES_RANGE_ENDPOINT,
    source_payload_hash: str | None = None,
    retrieved_at: str | None = None,
    ingested_at: str | None = None,
    parser_version: str = INSTITUTIONAL_FUTURES_RANGE_PARSER_VERSION,
) -> list[Observation]:
    """Parse the date-range CSV download into one row per trading date.

    The response covers every institution category and contract selected by
    the query; this keeps only the foreign/mainland investor row for the
    requested contract, matching the OpenAPI snapshot's filter so both paths
    populate the same ``values`` schema.
    """

    computed_hash = payload_sha256(payload)
    if source_payload_hash is not None and source_payload_hash != computed_hash:
        raise InstitutionalFuturesParseError(
            "institutional futures range payload hash does not match response"
        )
    payload_hash = source_payload_hash or computed_hash
    retrieved = retrieved_at or _utc_now()
    ingested = ingested_at or _utc_now()
    try:
        text = payload.decode("cp950")
    except UnicodeDecodeError as exc:
        raise InstitutionalFuturesParseError(
            "institutional futures range response is not valid CP950 text"
        ) from exc
    stripped = text.strip()
    if not stripped:
        return []

    rows = list(csv.reader(io.StringIO(stripped)))
    if not rows:
        return []
    header, *data_rows = rows
    expected_header = [
        "日期",
        "商品名稱",
        "身份別",
        "多方交易口數",
        "多方交易契約金額(千元)",
        "空方交易口數",
        "空方交易契約金額(千元)",
        "多空交易口數淨額",
        "多空交易契約金額淨額(千元)",
        "多方未平倉口數",
        "多方未平倉契約金額(千元)",
        "空方未平倉口數",
        "空方未平倉契約金額(千元)",
        "多空未平倉口數淨額",
        "多空未平倉契約金額淨額(千元)",
    ]
    if [column.strip() for column in header] != expected_header:
        raise InstitutionalFuturesParseError(
            "institutional futures range response has an unexpected header"
        )

    observations: list[Observation] = []
    seen_dates: set[str] = set()
    for line_number, row in enumerate(data_rows, start=2):
        if not row or not row[0].strip():
            continue
        if len(row) != len(expected_header):
            raise InstitutionalFuturesParseError(
                f"institutional futures range row {line_number} has "
                f"{len(row)} columns, expected {len(expected_header)}"
            )
        institution = row[2].strip()
        if institution not in _RANGE_INSTITUTIONS:
            continue
        source_date = row[0].strip()
        observation_date = _normalize_slash_date(source_date)
        if observation_date in seen_dates:
            raise InstitutionalFuturesParseError(
                f"institutional futures range row {line_number} repeats "
                f"date {observation_date!r}"
            )
        seen_dates.add(observation_date)
        values = {
            "contract_code": row[1].strip(),
            "institution": institution,
            "trading_volume_long": _range_number(row[3], "trading_volume_long"),
            "trading_volume_short": _range_number(row[5], "trading_volume_short"),
            "trading_volume_net": _range_number(row[7], "trading_volume_net"),
            "open_interest_long": _range_number(row[9], "open_interest_long"),
            "open_interest_short": _range_number(row[11], "open_interest_short"),
            "open_interest_net": _range_number(row[13], "open_interest_net"),
            "open_interest_net_value_thousands": _range_number(
                row[14], "open_interest_net_value_thousands"
            ),
            "unit": "contracts",
        }
        observations.append(
            Observation(
                dataset_id=INSTITUTIONAL_FUTURES_DATASET_ID,
                schema_version="0.1",
                observation_date=observation_date,
                source_date=source_date,
                source_name=INSTITUTIONAL_FUTURES_SOURCE_NAME,
                source_url=source_url,
                source_record_key=INSTITUTIONAL_FUTURES_SOURCE_RECORD_KEY,
                retrieved_at=retrieved,
                ingested_at=ingested,
                source_payload_hash=payload_hash,
                parser_version=parser_version,
                values=values,
                quality_status="available",
                publication_label=f"day:{observation_date}",
            )
        )
    return observations


def fetch_institutional_futures_range(
    start: date,
    end: date,
    *,
    contract_code: str = "TXF",
    http_post: Callable[[str, Mapping[str, str]], bytes] | None = None,
    parser_version: str = INSTITUTIONAL_FUTURES_RANGE_PARSER_VERSION,
) -> list[Observation]:
    """Fetch and parse the foreign TX position for a date range.

    ``start``/``end`` must fall inside the source's own rolling window
    (roughly the most recent three years); the server returns an HTML error
    page instead of CSV once any part of the request falls outside it, which
    raises :class:`InstitutionalFuturesParseError` here. Callers backfilling
    close to the window's older edge should leave a few days of margin
    rather than targeting the exact theoretical boundary.
    """

    if start > end:
        raise ValueError("start must not be after end")
    today = datetime.now(timezone.utc).date()
    form = {
        "firstDate": _three_years_before(today).strftime("%Y/%m/%d 00:00"),
        "lastDate": today.strftime("%Y/%m/%d 00:00"),
        "queryStartDate": start.strftime("%Y/%m/%d"),
        "queryEndDate": end.strftime("%Y/%m/%d"),
        "commodityId": contract_code,
    }
    try:
        payload = (http_post or _http_post)(INSTITUTIONAL_FUTURES_RANGE_ENDPOINT, form)
    except Exception as exc:
        if isinstance(exc, InstitutionalFuturesParseError):
            raise
        raise InstitutionalFuturesFetchError(
            "institutional futures range request failed"
        ) from exc
    if not isinstance(payload, bytes):
        raise InstitutionalFuturesFetchError(
            "institutional futures range response is not bytes"
        )
    return parse_institutional_futures_range_payload(
        payload,
        source_payload_hash=payload_sha256(payload),
        parser_version=parser_version,
    )


def collect_institutional_futures_range(
    store: ObservationStore,
    start: date,
    end: date,
    *,
    contract_code: str = "TXF",
    http_post: Callable[[str, Mapping[str, str]], bytes] | None = None,
    parser_version: str = INSTITUTIONAL_FUTURES_RANGE_PARSER_VERSION,
) -> list[WriteResult]:
    """Fetch a date range once and persist it with revision lineage."""

    observations = fetch_institutional_futures_range(
        start,
        end,
        contract_code=contract_code,
        http_post=http_post,
        parser_version=parser_version,
    )
    batch_writer = getattr(store, "write_observations", None)
    if callable(batch_writer):
        return batch_writer(observations)
    results: list[WriteResult] = []
    for observation in observations:
        previous_id = _latest_observation_id(store, observation)
        if previous_id is not None:
            observation = replace(observation, supersedes_id=previous_id)
        results.append(store.write_observation(observation))
    return results


def _three_years_before(value: date) -> date:
    try:
        return value.replace(year=value.year - 3)
    except ValueError:
        # value is Feb 29 on a leap year; three years back is never a leap year.
        return value.replace(month=2, day=28, year=value.year - 3)


def _normalize_slash_date(value: str) -> str:
    parts = value.split("/")
    if len(parts) != 3:
        raise InstitutionalFuturesParseError(f"unsupported official date {value!r}")
    try:
        return date(int(parts[0]), int(parts[1]), int(parts[2])).isoformat()
    except ValueError as exc:
        raise InstitutionalFuturesParseError(
            f"invalid official date {value!r}"
        ) from exc


def _decode_institutional_json(payload: bytes) -> object:
    """Decode the endpoint's JSON across the encodings used by TAIFEX."""

    errors: list[UnicodeDecodeError | json.JSONDecodeError] = []
    for encoding in ("utf-8-sig", "cp950"):
        try:
            return json.loads(payload.decode(encoding))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            errors.append(exc)
    raise InstitutionalFuturesParseError(
        "institutional futures response is not valid UTF-8 or CP950 JSON"
    ) from errors[-1]


def _range_number(raw: str, field: str) -> float:
    text = raw.strip()
    if text == "" or text in {"-", "--", "N/A"}:
        raise InstitutionalFuturesParseError(f"field {field!r} is unavailable")
    try:
        value = float(text.replace(",", ""))
    except ValueError as exc:
        raise InstitutionalFuturesParseError(f"field {field!r} is not numeric") from exc
    if not math.isfinite(value):
        raise InstitutionalFuturesParseError(f"field {field!r} is not finite")
    return value


def _normalize_date(value: str) -> str:
    if len(value) != 8 or not value.isdigit():
        raise InstitutionalFuturesParseError(f"unsupported official date {value!r}")
    try:
        return date(int(value[:4]), int(value[4:6]), int(value[6:])).isoformat()
    except ValueError as exc:
        raise InstitutionalFuturesParseError(
            f"invalid official date {value!r}"
        ) from exc


def _number(row: Mapping[str, object], field: str) -> float:
    raw = row.get(field)
    if raw is None or str(raw).strip() in {"", "-", "--", "N/A"}:
        raise InstitutionalFuturesParseError(f"field {field!r} is unavailable")
    try:
        value = float(str(raw).replace(",", ""))
    except ValueError as exc:
        raise InstitutionalFuturesParseError(f"field {field!r} is not numeric") from exc
    if not math.isfinite(value):
        raise InstitutionalFuturesParseError(f"field {field!r} is not finite")
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


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _http_get(url: str) -> bytes:
    request = Request(
        url,
        headers={
            "Accept": "application/json",
            "Accept-Encoding": "identity",
            "User-Agent": "HudaTaiwanQuant/0.1",
        },
    )
    try:
        with urlopen(request, timeout=30) as response:
            return response.read()
    except (HTTPError, URLError, OSError) as exc:
        raise InstitutionalFuturesFetchError(
            "institutional futures request failed"
        ) from exc


def _http_post(url: str, data: Mapping[str, str]) -> bytes:
    request = Request(
        url,
        data=urlencode(data).encode("ascii"),
        headers={
            "Accept": "text/csv,text/plain",
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": "HudaTaiwanQuant/0.1",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=30) as response:
            return response.read()
    except (HTTPError, URLError, OSError) as exc:
        raise InstitutionalFuturesFetchError(
            "institutional futures range request failed"
        ) from exc


__all__ = [
    "INSTITUTIONAL_FUTURES_DATASET_ID",
    "INSTITUTIONAL_FUTURES_ENDPOINT",
    "INSTITUTIONAL_FUTURES_PARSER_VERSION",
    "INSTITUTIONAL_FUTURES_RANGE_ENDPOINT",
    "INSTITUTIONAL_FUTURES_RANGE_PARSER_VERSION",
    "INSTITUTIONAL_FUTURES_SOURCE_NAME",
    "INSTITUTIONAL_FUTURES_SOURCE_RECORD_KEY",
    "InstitutionalFuturesFetchError",
    "InstitutionalFuturesParseError",
    "collect_institutional_futures_latest",
    "collect_institutional_futures_range",
    "fetch_institutional_futures_latest",
    "fetch_institutional_futures_range",
    "parse_institutional_futures_payload",
    "parse_institutional_futures_range_payload",
    "payload_sha256",
]
