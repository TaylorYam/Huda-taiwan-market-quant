"""TWSE daily foreign/mainland investor cash net buy-sell (BFI82U) collector.

The free report's own trading-scope footnote (block-trade / 鉅額 inclusion)
changed at some point between 2004-04-07 (excludes block trades) and
2008-06-05 (includes them, matching the FMTQIK market-turnover denominator).
Confirmed "includes block trades" on 2008-06-05, 2015-06-15, 2022-10-24 and
2026-09-14 -- an 18-year span of consistency. ``FOREIGN_CASH_VERIFIED_START``
sits comfortably after the earliest confirmed-consistent sample as a
conservative buffer; dates before it are a known, unresolved gap and are
never collected. See docs/phase0-cash-factor-source-verification-v0.1.md.

The row label for the foreign/mainland investor category has also changed
across report vintages (plain "外資" through ~2008, "外資及陸資" around
2015, "外資及陸資(不含外資自營商)" alongside a separate "外資自營商" row
from roughly 2022 onward). The parser matches any of these; it never sums
in a separate "外資自營商" row, matching the report's own footnote that
foreign-dealer amounts are already folded into the dealer total and
excluded from the three-institutional-investor aggregate.
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

FOREIGN_CASH_DATASET_ID = "twse_foreign_cash_bfi82u_v1"
FOREIGN_CASH_SOURCE_NAME = "TWSE"
FOREIGN_CASH_ENDPOINT = "https://www.twse.com.tw/fund/BFI82U"
FOREIGN_CASH_PARSER_VERSION = "twse-foreign-cash-csv@0.1"
FOREIGN_CASH_SOURCE_RECORD_KEY = "BFI82U:foreign"
FOREIGN_CASH_VERIFIED_START = date(2010, 1, 1)

_FOREIGN_ROW_LABELS = {
    "外資",
    "外資及陸資",
    "外資及陸資(不含外資自營商)",
    "外資及陸資（不含外資自營商）",
}
_TITLE_DATE = re.compile(r"(?P<year>\d+)年(?P<month>\d+)月(?P<day>\d+)日")


class ForeignCashFetchError(RuntimeError):
    """The official BFI82U endpoint could not be fetched."""


class ForeignCashParseError(ValueError):
    """The official BFI82U response did not match the expected schema."""


def build_foreign_cash_day_url(target: date) -> str:
    """Build the official day query without making a network request."""

    _validate_date(target)
    stamp = f"{target:%Y%m%d}"
    query = urlencode(
        {
            "response": "csv",
            "dayDate": stamp,
            "weekDate": stamp,
            "monthDate": stamp,
            "type": "day",
        }
    )
    return f"{FOREIGN_CASH_ENDPOINT}?{query}"


def payload_sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def parse_foreign_cash_payload(
    payload: bytes,
    *,
    source_url: str = FOREIGN_CASH_ENDPOINT,
    source_payload_hash: str | None = None,
    retrieved_at: str | None = None,
    ingested_at: str | None = None,
    parser_version: str = FOREIGN_CASH_PARSER_VERSION,
    expected_date: date | None = None,
) -> list[Observation]:
    """Parse one daily BFI82U CSV report into the foreign net buy/sell row."""

    computed_hash = payload_sha256(payload)
    if source_payload_hash is not None and source_payload_hash != computed_hash:
        raise ForeignCashParseError("foreign cash payload hash does not match response")
    payload_hash = source_payload_hash or computed_hash
    retrieved = retrieved_at or _utc_now()
    ingested = ingested_at or _utc_now()
    try:
        text = payload.decode("cp950")
    except UnicodeDecodeError as exc:
        raise ForeignCashParseError(
            "foreign cash response is not valid CP950 text"
        ) from exc
    rows = [row for row in csv.reader(io.StringIO(text)) if row and any(row)]
    if not rows:
        raise ForeignCashParseError("foreign cash response has no rows")

    observation_date = _parse_title_date(rows[0][0] if rows[0] else "")
    if expected_date is not None and observation_date != expected_date:
        raise ForeignCashParseError(
            f"foreign cash response date {observation_date} does not match "
            f"requested date {expected_date}"
        )

    foreign_row = next(
        (row for row in rows[1:] if row and row[0].strip() in _FOREIGN_ROW_LABELS),
        None,
    )
    if foreign_row is None:
        raise ForeignCashParseError(
            "foreign cash response has no matching foreign investor row"
        )
    if len(foreign_row) < 4:
        raise ForeignCashParseError("foreign cash row is missing the net column")
    net = _parse_amount(foreign_row[3], "net_buy_sell")

    return [
        Observation(
            dataset_id=FOREIGN_CASH_DATASET_ID,
            schema_version="0.1",
            observation_date=observation_date.isoformat(),
            source_date=observation_date.isoformat(),
            source_name=FOREIGN_CASH_SOURCE_NAME,
            source_url=source_url,
            source_record_key=FOREIGN_CASH_SOURCE_RECORD_KEY,
            retrieved_at=retrieved,
            ingested_at=ingested,
            source_payload_hash=payload_hash,
            parser_version=parser_version,
            values={
                "net_buy_sell": net,
                "category": foreign_row[0].strip(),
                "unit": "TWD",
            },
            quality_status="available",
            publication_label=f"day:{observation_date.isoformat()}",
        )
    ]


def fetch_foreign_cash_day(
    target: date,
    *,
    http_get: Callable[[str], bytes] | None = None,
    parser_version: str = FOREIGN_CASH_PARSER_VERSION,
) -> list[Observation]:
    """Fetch and parse one day's foreign cash net buy/sell amount."""

    url = build_foreign_cash_day_url(target)
    try:
        payload = (http_get or _http_get)(url)
    except Exception as exc:
        if isinstance(exc, ForeignCashParseError):
            raise
        raise ForeignCashFetchError(f"foreign cash request failed for {url}") from exc
    return parse_foreign_cash_payload(
        payload,
        source_url=url,
        source_payload_hash=payload_sha256(payload),
        parser_version=parser_version,
        expected_date=target,
    )


def collect_foreign_cash_day(
    store: ObservationStore,
    target: date,
    *,
    http_get: Callable[[str], bytes] | None = None,
    parser_version: str = FOREIGN_CASH_PARSER_VERSION,
) -> list[WriteResult]:
    """Fetch one day and persist it with idempotency and revision lineage."""

    observations = fetch_foreign_cash_day(
        target, http_get=http_get, parser_version=parser_version
    )
    results: list[WriteResult] = []
    for observation in observations:
        previous_id = _latest_observation_id(store, observation)
        if previous_id is not None:
            observation = replace(observation, supersedes_id=previous_id)
        results.append(store.write_observation(observation))
    return results


def _validate_date(target: date) -> None:
    if target < FOREIGN_CASH_VERIFIED_START:
        raise ValueError(
            "foreign cash date must be on or after "
            f"{FOREIGN_CASH_VERIFIED_START.isoformat()} (unresolved block-trade "
            "scope before this date; see phase0-cash-factor-source-verification-v0.1.md)"
        )


def _parse_title_date(title: str) -> date:
    match = _TITLE_DATE.search(title)
    if match is None:
        raise ForeignCashParseError(f"unrecognized foreign cash report title {title!r}")
    year = int(match["year"])
    if year < 1000:
        year += 1911
    try:
        return date(year, int(match["month"]), int(match["day"]))
    except ValueError as exc:
        raise ForeignCashParseError(
            f"invalid foreign cash report date in title {title!r}"
        ) from exc


def _parse_amount(raw: str, field: str) -> float:
    text = raw.strip()
    if text == "" or text in {"-", "--", "N/A"}:
        raise ForeignCashParseError(f"field {field!r} is unavailable")
    try:
        value = float(text.replace(",", ""))
    except ValueError as exc:
        raise ForeignCashParseError(f"field {field!r} is not numeric") from exc
    if not math.isfinite(value):
        raise ForeignCashParseError(f"field {field!r} is not finite")
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
        headers={"Accept": "text/csv,text/plain", "User-Agent": "HudaTaiwanQuant/0.1"},
    )
    try:
        with urlopen(request, timeout=30) as response:
            return response.read()
    except (HTTPError, URLError, OSError) as exc:
        raise ForeignCashFetchError("foreign cash request failed") from exc


__all__ = [
    "FOREIGN_CASH_DATASET_ID",
    "FOREIGN_CASH_ENDPOINT",
    "FOREIGN_CASH_PARSER_VERSION",
    "FOREIGN_CASH_SOURCE_NAME",
    "FOREIGN_CASH_SOURCE_RECORD_KEY",
    "FOREIGN_CASH_VERIFIED_START",
    "ForeignCashFetchError",
    "ForeignCashParseError",
    "build_foreign_cash_day_url",
    "collect_foreign_cash_day",
    "fetch_foreign_cash_day",
    "parse_foreign_cash_payload",
    "payload_sha256",
]
