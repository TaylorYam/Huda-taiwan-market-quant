"""Source adapters and normalized market observations."""

from .postgres import PostgresObservationStore
from .storage import (
    QUALITY_STATUSES,
    Observation,
    ObservationStore,
    SQLiteObservationStore,
    WriteResult,
)
from .supabase_rest import SupabaseRestObservationStore
from .twse_taiex import (
    TAIEX_DATASET_ID,
    TAIEX_ENDPOINT,
    TAIEXFetchError,
    TAIEXParseError,
    build_taiex_month_url,
    collect_taiex_month,
    collect_taiex_range,
    fetch_taiex_month,
    parse_taiex_payload,
)

__all__ = [
    "QUALITY_STATUSES",
    "TAIEX_DATASET_ID",
    "TAIEX_ENDPOINT",
    "Observation",
    "ObservationStore",
    "PostgresObservationStore",
    "SQLiteObservationStore",
    "SupabaseRestObservationStore",
    "TAIEXFetchError",
    "TAIEXParseError",
    "WriteResult",
    "build_taiex_month_url",
    "collect_taiex_month",
    "collect_taiex_range",
    "fetch_taiex_month",
    "parse_taiex_payload",
]
