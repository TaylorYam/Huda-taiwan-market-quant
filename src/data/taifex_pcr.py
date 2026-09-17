"""TAIFEX daily TXO put/call open-interest ratio collector.

The TAIFEX PCR form accepts windows of at most 31 calendar dates.  The
operational collector deliberately uses a one-day window so each stored row
has one canonical source request and can be retried or revised independently.
"""

from __future__ import annotations

import hashlib
import math
from collections.abc import Callable, Mapping
from dataclasses import replace
from datetime import date, datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .storage import Observation, ObservationStore, WriteResult
from .taifex_pcr_probe import (
    PCR_ENDPOINT,
    PCR_FIRST_VERIFIED_DATE,
    PCRParseError,
    PCRRecord,
    PCRWindow,
    parse_pcr_csv,
)

PCR_DATASET_ID = "taifex_txo_oi_pcr_v1"
PCR_SOURCE_NAME = "TAIFEX"
PCR_PARSER_VERSION = "taifex-pcr-csv@0.1"
PCR_SOURCE_RECORD_KEY = "TXO"


class PCRFetchError(RuntimeError):
    """The official TAIFEX PCR endpoint could not be fetched."""


def payload_sha256(payload: bytes) -> str:
    """Return the SHA-256 used to identify the exact official response."""

    return hashlib.sha256(payload).hexdigest()


def parse_pcr_payload(
    payload: bytes,
    observation_date: date,
    *,
    source_url: str = PCR_ENDPOINT,
    source_payload_hash: str | None = None,
    retrieved_at: str | None = None,
    ingested_at: str | None = None,
    parser_version: str = PCR_PARSER_VERSION,
) -> list[Observation]:
    """Parse one canonical-day response into one observation.

    An official header-only response is a successful request with no row for
    the requested date, and is stored as ``source_empty``.  This distinction
    lets callers distinguish a non-trading day from a transport or parse
    failure without inventing zero values.
    """

    _validate_observation_date(observation_date)
    window = PCRWindow(observation_date, observation_date)
    computed_hash = payload_sha256(payload)
    if source_payload_hash is not None and source_payload_hash != computed_hash:
        raise PCRParseError("PCR source payload hash does not match response")
    payload_hash = source_payload_hash or computed_hash
    retrieved = retrieved_at or _utc_now()
    ingested = ingested_at or _utc_now()
    if not payload.strip():
        records: list[PCRRecord] = []
    else:
        _, records = parse_pcr_csv(payload, window)
    if len(records) > 1:
        raise PCRParseError(
            f"{window.label}: canonical response returned {len(records)} rows"
        )

    publication_label = f"day:{observation_date.isoformat()}"
    if not records:
        return [
            Observation(
                dataset_id=PCR_DATASET_ID,
                schema_version="0.1",
                observation_date=observation_date.isoformat(),
                source_date=observation_date.strftime("%Y/%m/%d"),
                source_name=PCR_SOURCE_NAME,
                source_url=source_url,
                source_record_key=PCR_SOURCE_RECORD_KEY,
                retrieved_at=retrieved,
                ingested_at=ingested,
                source_payload_hash=payload_hash,
                parser_version=parser_version,
                values={},
                quality_status="source_empty",
                quality_notes="Official PCR response contained no row for the requested date.",
                publication_label=publication_label,
            )
        ]

    record = records[0]
    return [
        _observation_from_record(
            record,
            source_url=source_url,
            source_payload_hash=payload_hash,
            retrieved_at=retrieved,
            ingested_at=ingested,
            parser_version=parser_version,
            publication_label=publication_label,
        )
    ]


def fetch_pcr_day(
    observation_date: date,
    *,
    http_post: Callable[..., bytes] | None = None,
    parser_version: str = PCR_PARSER_VERSION,
) -> list[Observation]:
    """Fetch and parse one TAIFEX PCR canonical day."""

    _validate_observation_date(observation_date)
    window = PCRWindow(observation_date, observation_date)
    try:
        if http_post is None:
            payload = _http_post(PCR_ENDPOINT, window.form_values())
        else:
            try:
                # Window callbacks are convenient for local tests and mirror
                # the probe API.
                payload = http_post(window)
            except TypeError as one_argument_error:
                try:
                    # URL/form callbacks match the other TAIFEX collectors.
                    payload = http_post(PCR_ENDPOINT, window.form_values())
                except TypeError:
                    raise one_argument_error
    except PCRParseError:
        raise
    except Exception as exc:
        raise PCRFetchError(f"PCR request failed for {window.label}") from exc
    if not isinstance(payload, bytes):
        raise PCRFetchError("PCR request returned a non-bytes payload")
    return parse_pcr_payload(
        payload,
        observation_date,
        source_url=PCR_ENDPOINT,
        source_payload_hash=payload_sha256(payload),
        parser_version=parser_version,
    )


def collect_pcr_day(
    store: ObservationStore,
    observation_date: date,
    *,
    http_post: Callable[..., bytes] | None = None,
    parser_version: str = PCR_PARSER_VERSION,
) -> list[WriteResult]:
    """Fetch one day and persist it with idempotency and revision lineage."""

    observations = fetch_pcr_day(
        observation_date,
        http_post=http_post,
        parser_version=parser_version,
    )
    results: list[WriteResult] = []
    for observation in observations:
        previous_id = _latest_observation_id(store, observation)
        if previous_id is not None:
            observation = replace(observation, supersedes_id=previous_id)
        results.append(store.write_observation(observation))
    return results


def parse_pcr_day(*args: object, **kwargs: object) -> list[Observation]:
    """Compatibility alias for the daily payload parser."""

    return parse_pcr_payload(*args, **kwargs)  # type: ignore[arg-type]


def fetch_pcr_daily(*args: object, **kwargs: object) -> list[Observation]:
    """Compatibility alias for callers using the daily-series name."""

    return fetch_pcr_day(*args, **kwargs)  # type: ignore[arg-type]


def collect_pcr_daily(*args: object, **kwargs: object) -> list[WriteResult]:
    """Compatibility alias for the daily collector entry point."""

    return collect_pcr_day(*args, **kwargs)  # type: ignore[arg-type]


def _observation_from_record(
    record: PCRRecord,
    *,
    source_url: str,
    source_payload_hash: str,
    retrieved_at: str,
    ingested_at: str,
    parser_version: str,
    publication_label: str,
) -> Observation:
    if record.call_oi == 0:
        oi_pcr: float | None = None
        quality_notes = "call_oi is zero; oi_pcr is unavailable."
    else:
        oi_pcr = record.put_oi / record.call_oi
        if not math.isfinite(oi_pcr):
            oi_pcr = None
            quality_notes = (
                "oi_pcr is unavailable because the derived value is non-finite."
            )
        else:
            quality_notes = None
    return Observation(
        dataset_id=PCR_DATASET_ID,
        schema_version="0.1",
        observation_date=record.observation_date.isoformat(),
        source_date=record.source_date or record.observation_date.isoformat(),
        source_name=PCR_SOURCE_NAME,
        source_url=source_url,
        source_record_key=PCR_SOURCE_RECORD_KEY,
        retrieved_at=retrieved_at,
        ingested_at=ingested_at,
        source_payload_hash=source_payload_hash,
        parser_version=parser_version,
        values={
            "put_volume": record.put_volume,
            "call_volume": record.call_volume,
            "volume_ratio_percent": record.volume_ratio,
            "put_oi": record.put_oi,
            "call_oi": record.call_oi,
            "oi_ratio_percent": record.oi_ratio,
            "oi_pcr": oi_pcr,
            "unit": "contracts",
        },
        quality_status="available",
        quality_notes=quality_notes,
        publication_label=publication_label,
    )


def _validate_observation_date(value: date) -> None:
    if value < PCR_FIRST_VERIFIED_DATE:
        raise ValueError(
            f"PCR observation date must be on or after {PCR_FIRST_VERIFIED_DATE.isoformat()}"
        )


def _latest_observation_id(
    store: ObservationStore, observation: Observation
) -> int | None:
    """Find the latest canonical row through the two bundled store adapters.

    The public store protocol intentionally returns observations without their
    database ids.  Both production adapters expose their query boundary, so
    use that boundary here to preserve revision lineage before writing.
    """

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
        raise PCRFetchError("PCR request failed") from exc


__all__ = [
    "PCR_DATASET_ID",
    "PCR_ENDPOINT",
    "PCR_FIRST_VERIFIED_DATE",
    "PCR_PARSER_VERSION",
    "PCR_SOURCE_NAME",
    "PCR_SOURCE_RECORD_KEY",
    "PCRFetchError",
    "PCRParseError",
    "collect_pcr_daily",
    "collect_pcr_day",
    "fetch_pcr_daily",
    "fetch_pcr_day",
    "parse_pcr_day",
    "parse_pcr_payload",
    "payload_sha256",
]
