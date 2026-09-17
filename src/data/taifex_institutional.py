"""TAIFEX daily foreign futures open-interest snapshot collector."""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Callable, Mapping
from dataclasses import replace
from datetime import date, datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .storage import Observation, ObservationStore, WriteResult

INSTITUTIONAL_FUTURES_DATASET_ID = "taifex_institutional_futures_oi_v1"
INSTITUTIONAL_FUTURES_ENDPOINT = (
    "https://openapi.taifex.com.tw/v1/"
    "MarketDataOfMajorInstitutionalTradersDetailsOfFuturesContractsBytheDate"
)
INSTITUTIONAL_FUTURES_PARSER_VERSION = "taifex-institutional-futures-oi-json@0.1"
INSTITUTIONAL_FUTURES_SOURCE_NAME = "TAIFEX"
INSTITUTIONAL_FUTURES_SOURCE_RECORD_KEY = "TX:foreign:institutional"


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
    try:
        decoded = payload.decode("utf-8-sig")
        raw_rows = json.loads(decoded)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise InstitutionalFuturesParseError(
            "institutional futures response is not valid UTF-8 JSON"
        ) from exc
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
) -> list[Observation]:
    """Fetch and parse the latest official daily snapshot."""

    try:
        payload = (http_get or _http_get)(INSTITUTIONAL_FUTURES_ENDPOINT)
    except Exception as exc:
        if isinstance(exc, InstitutionalFuturesParseError):
            raise
        raise InstitutionalFuturesFetchError(
            "institutional futures snapshot request failed"
        ) from exc
    if not isinstance(payload, bytes):
        raise InstitutionalFuturesFetchError(
            "institutional futures response is not bytes"
        )
    return parse_institutional_futures_payload(
        payload,
        source_payload_hash=payload_sha256(payload),
        parser_version=parser_version,
    )


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


__all__ = [
    "INSTITUTIONAL_FUTURES_DATASET_ID",
    "INSTITUTIONAL_FUTURES_ENDPOINT",
    "INSTITUTIONAL_FUTURES_PARSER_VERSION",
    "INSTITUTIONAL_FUTURES_SOURCE_NAME",
    "INSTITUTIONAL_FUTURES_SOURCE_RECORD_KEY",
    "InstitutionalFuturesFetchError",
    "InstitutionalFuturesParseError",
    "collect_institutional_futures_latest",
    "fetch_institutional_futures_latest",
    "parse_institutional_futures_payload",
    "payload_sha256",
]
