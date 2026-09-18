"""TAIFEX daily TX report parser for dates not yet in annual ZIP archives.

The annual TX archive is the preferred historical source.  TAIFEX also keeps a
date-based daily report, which is needed for the current calendar year before
the next annual ZIP is published.  This module parses only the selected TX
session and preserves the same observation identity used by the annual parser.
"""

from __future__ import annotations

import hashlib
import time
from collections.abc import Callable, Mapping, Sequence
from datetime import date, datetime, timezone
from html.parser import HTMLParser
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .storage import Observation

TX_DAILY_ENDPOINT = "https://www.taifex.com.tw/cht/3/futDailyMarketReport"
TX_DAILY_PARSER_VERSION = "taifex-tx-daily-html@0.1"
TX_DAILY_SOURCE_NAME = "TAIFEX"


class TXDailyFetchError(RuntimeError):
    """The official date-based TX report could not be fetched."""


class TXDailyParseError(ValueError):
    """The official date-based TX report did not match the expected table."""


def parse_tx_daily_payload(
    observation_date: date,
    payload: bytes,
    *,
    market_code: int = 0,
    source_url: str = TX_DAILY_ENDPOINT,
    source_payload_hash: str | None = None,
    retrieved_at: str | None = None,
    ingested_at: str | None = None,
    parser_version: str = TX_DAILY_PARSER_VERSION,
) -> list[Observation]:
    """Parse one date-based report into TX observations.

    ``market_code=0`` is the general (day) session and ``market_code=1`` is
    the after-hours session.  The basis factor deliberately selects the
    general session, while keeping the after-hours parser available for future
    diagnostics.
    """

    if market_code not in {0, 1}:
        raise TXDailyParseError("market_code must be 0 (day) or 1 (after-hours)")
    digest = hashlib.sha256(payload).hexdigest()
    if source_payload_hash is not None and source_payload_hash != digest:
        raise TXDailyParseError("TX daily source payload hash does not match response")
    rows = _first_table_rows(payload)
    data_rows = [row for row in rows if len(row) >= 6 and row[0].strip() == "TX"]
    if not data_rows:
        return []

    session = "一般" if market_code == 0 else "盤後"
    retrieved = retrieved_at or _utc_now()
    ingested = ingested_at or _utc_now()
    observations: list[Observation] = []
    for row_number, row in enumerate(data_rows, start=2):
        expiry = row[1].strip()
        if not expiry:
            raise TXDailyParseError(f"row {row_number} has empty expiry")
        values = {
            "open": _parse_optional_number(row, 2, "open", row_number),
            "high": _parse_optional_number(row, 3, "high", row_number),
            "low": _parse_optional_number(row, 4, "low", row_number),
            "close": _parse_optional_number(row, 5, "close", row_number),
            "settlement": _parse_optional_number(
                row, 11 if market_code == 0 else None, "settlement", row_number
            ),
            "volume": _parse_optional_number(
                row, 9 if market_code == 0 else 8, "volume", row_number, integer=True
            ),
            "open_interest": _parse_optional_number(
                row,
                12 if market_code == 0 else None,
                "open_interest",
                row_number,
                integer=True,
            ),
            "price_unit": "index_points",
            "volume_unit": "contracts",
            "open_interest_unit": "contracts",
        }
        observations.append(
            Observation(
                dataset_id="taifex_tx_daily_contract_v1",
                schema_version="0.1",
                observation_date=observation_date.isoformat(),
                source_date=observation_date.strftime("%Y/%m/%d"),
                source_name=TX_DAILY_SOURCE_NAME,
                source_url=source_url,
                source_record_key=f"TX:{expiry}:{session}",
                retrieved_at=retrieved,
                ingested_at=ingested,
                source_payload_hash=source_payload_hash or digest,
                parser_version=parser_version,
                values=values,
                quality_status="available"
                if values["close"] is not None
                else "invalid",
                quality_notes=(
                    None
                    if values["close"] is not None
                    else "Official TX daily row has no close price."
                ),
                publication_label=f"daily:{observation_date.isoformat()}:{session}",
            )
        )
    return observations


def fetch_tx_day(
    observation_date: date,
    *,
    market_code: int = 0,
    http_post: Callable[[str, Mapping[str, str]], bytes] | None = None,
    parser_version: str = TX_DAILY_PARSER_VERSION,
    retries: int = 5,
    retry_delay: float = 2.0,
) -> list[Observation]:
    """Fetch and parse one official date-based TX report."""

    if not isinstance(observation_date, date):
        raise TXDailyFetchError("observation_date must be a date")
    if retries < 0:
        raise TXDailyFetchError("retries must not be negative")
    if retry_delay < 0:
        raise TXDailyFetchError("retry_delay must not be negative")
    form = build_daily_form(observation_date, market_code=market_code)
    request = http_post or _http_post
    for attempt in range(retries + 1):
        try:
            payload = request(TX_DAILY_ENDPOINT, form)
            break
        except Exception as exc:
            if attempt >= retries:
                raise TXDailyFetchError(
                    f"TX daily request failed for {observation_date.isoformat()}"
                ) from exc
            if retry_delay:
                time.sleep(retry_delay)
    if not isinstance(payload, bytes):
        raise TXDailyFetchError("TX daily request returned a non-bytes payload")
    try:
        return parse_tx_daily_payload(
            observation_date,
            payload,
            market_code=market_code,
            source_payload_hash=hashlib.sha256(payload).hexdigest(),
            parser_version=parser_version,
        )
    except TXDailyParseError:
        raise
    except Exception as exc:
        raise TXDailyParseError(
            f"TX daily response could not be parsed for {observation_date.isoformat()}"
        ) from exc


def build_daily_form(observation_date: date, *, market_code: int = 0) -> dict[str, str]:
    """Build the POST body used by the official daily report page."""

    if market_code not in {0, 1}:
        raise ValueError("market_code must be 0 (day) or 1 (after-hours)")
    return {
        "queryType": "2",
        "marketCode": str(market_code),
        "dateaddcnt": "",
        "commodity_id": "TX",
        "commodity_id2": "",
        "queryDate": observation_date.strftime("%Y/%m/%d"),
        "MarketCode": str(market_code),
    }


class _TableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.tables: list[list[list[str]]] = []
        self._table_depth = 0
        self._rows: list[list[str]] = []
        self._row: list[str] | None = None
        self._cell: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "table":
            self._table_depth += 1
            if self._table_depth == 1:
                self._rows = []
        elif self._table_depth == 1 and tag == "tr":
            self._row = []
        elif self._table_depth == 1 and tag in {"td", "th"}:
            self._cell = []

    def handle_data(self, data: str) -> None:
        if self._cell is not None:
            self._cell.append(data)

    def handle_endtag(self, tag: str) -> None:
        if self._table_depth == 1 and tag in {"td", "th"}:
            if self._cell is not None and self._row is not None:
                self._row.append(" ".join("".join(self._cell).split()))
            self._cell = None
        elif self._table_depth == 1 and tag == "tr":
            if self._row:
                self._rows.append(self._row)
            self._row = None
        elif tag == "table":
            if self._table_depth == 1:
                self.tables.append(self._rows)
            self._table_depth = max(0, self._table_depth - 1)


def _first_table_rows(payload: bytes) -> list[list[str]]:
    parser = _TableParser()
    try:
        parser.feed(payload.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise TXDailyParseError("TX daily response is not UTF-8 HTML") from exc
    if not parser.tables:
        raise TXDailyParseError("TX daily response contains no HTML table")
    return parser.tables[0]


def _parse_optional_number(
    row: Sequence[str],
    index: int | None,
    field_name: str,
    row_number: int,
    *,
    integer: bool = False,
) -> int | float | None:
    if index is None or len(row) <= index:
        return None
    text = row[index].strip().replace(",", "")
    if not text or text in {"-", "--", "N/A", "NULL"}:
        return None
    try:
        number = float(text)
    except ValueError as exc:
        raise TXDailyParseError(
            f"row {row_number} field {field_name} is not numeric: {text!r}"
        ) from exc
    if integer:
        if not number.is_integer():
            raise TXDailyParseError(
                f"row {row_number} field {field_name} is not an integer"
            )
        return int(number)
    return int(number) if number.is_integer() else number


def _http_post(url: str, data: Mapping[str, str]) -> bytes:
    request = Request(
        url,
        data=urlencode(data).encode("utf-8"),
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Referer": TX_DAILY_ENDPOINT + "?commodityId=TX",
            "User-Agent": "HudaTaiwanQuant/0.1",
        },
        method="POST",
    )
    with urlopen(request, timeout=60) as response:
        return response.read()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


__all__ = [
    "TX_DAILY_ENDPOINT",
    "TX_DAILY_PARSER_VERSION",
    "TX_DAILY_SOURCE_NAME",
    "TXDailyFetchError",
    "TXDailyParseError",
    "build_daily_form",
    "fetch_tx_day",
    "parse_tx_daily_payload",
]
