"""Source adapters and normalized market observations."""

from .storage import (
    QUALITY_STATUSES,
    Observation,
    ObservationStore,
    SQLiteObservationStore,
    WriteResult,
)
from .twse_taiex import (
    TAIEX_DATASET_ID,
    TAIEX_ENDPOINT,
    TAIEXFetchError,
    TAIEXParseError,
    build_taiex_month_url,
    collect_taiex_month,
    fetch_taiex_month,
    parse_taiex_payload,
)

__all__ = [
    "QUALITY_STATUSES",
    "TAIEX_DATASET_ID",
    "TAIEX_ENDPOINT",
    "Observation",
    "ObservationStore",
    "SQLiteObservationStore",
    "TAIEXFetchError",
    "TAIEXParseError",
    "WriteResult",
    "build_taiex_month_url",
    "collect_taiex_month",
    "fetch_taiex_month",
    "parse_taiex_payload",
]
