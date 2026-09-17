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
from .taiex_pipeline import (
    TAIWAN_TIMEZONE,
    current_taiwan_month,
    summarize_write_results,
)
from .taifex_pcr_probe import (
    PCR_ENDPOINT,
    PCR_FIRST_VERIFIED_DATE,
    PCRParseError,
    PCRRecord,
    PCRWindow,
    audit_pcr_range,
    iter_pcr_windows,
    parse_pcr_csv,
)
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
    "PCR_ENDPOINT",
    "PCR_FIRST_VERIFIED_DATE",
    "QUALITY_STATUSES",
    "TAIEX_DATASET_ID",
    "TAIEX_ENDPOINT",
    "TAIWAN_TIMEZONE",
    "Observation",
    "ObservationStore",
    "PCRParseError",
    "PCRRecord",
    "PCRWindow",
    "PostgresObservationStore",
    "SQLiteObservationStore",
    "SupabaseRestObservationStore",
    "TAIEXFetchError",
    "TAIEXParseError",
    "WriteResult",
    "audit_pcr_range",
    "build_taiex_month_url",
    "collect_taiex_month",
    "collect_taiex_range",
    "current_taiwan_month",
    "fetch_taiex_month",
    "iter_pcr_windows",
    "parse_pcr_csv",
    "parse_taiex_payload",
    "summarize_write_results",
]
