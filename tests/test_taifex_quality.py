from __future__ import annotations

from src.data.taifex_quality import build_taifex_quality_report


def test_quality_report_preserves_unknown_calendar_and_does_not_fill_missing():
    report = build_taifex_quality_report(
        {
            "taifex_txo_oi_pcr_v1": [
                {"observation_date": "2024-01-02", "quality_status": "available"},
                {"observation_date": "2024-01-04", "quality_status": "available"},
            ]
        },
        requested_start="2024-01-01",
        requested_end="2024-01-05",
        calendar_source="TAIFEX calendar not available for this boundary",
    )

    dataset = report["datasets"]["taifex_txo_oi_pcr_v1"]
    assert report["gate_status"] == "unknown"
    assert report["calendar_boundary"]["status"] == "unknown"
    assert dataset["earliest_date"] == "2024-01-02"
    assert dataset["latest_date"] == "2024-01-04"
    assert dataset["missing_dates"] is None
    assert dataset["coverage"] == {
        "available_date_count": 2,
        "expected_date_count": None,
        "ratio": None,
    }
    assert dataset["calendar_boundary"]["expected_date_count"] is None


def test_quality_report_reconciles_known_calendar_and_records_empty_duplicates():
    report = build_taifex_quality_report(
        {
            "taifex_taiwan_vix_close_v1": {
                "records": [
                    {
                        "observation_date": "2024-01-02",
                        "quality_status": "available",
                    },
                    {
                        "observation_date": "2024-01-02",
                        "quality_status": "available",
                    },
                    {
                        "observation_date": "2024-01-03",
                        "quality_status": "source_empty",
                    },
                ],
                "empty_dates": ["2024-01-04"],
            }
        },
        requested_start="2024-01-02",
        requested_end="2024-01-04",
        expected_dates=["2024-01-02", "2024-01-03", "2024-01-04"],
        calendar_status="available",
        calendar_source="official-fixture",
    )

    dataset = report["datasets"]["taifex_taiwan_vix_close_v1"]
    assert report["gate_status"] == "fail"
    assert dataset["earliest_date"] == "2024-01-02"
    assert dataset["latest_date"] == "2024-01-03"
    assert dataset["empty_dates"] == ["2024-01-03", "2024-01-04"]
    assert dataset["duplicate_dates"] == ["2024-01-02"]
    assert dataset["missing_dates"] == ["2024-01-03", "2024-01-04"]
    assert dataset["calendar_boundary"]["status"] == "available"
    assert dataset["coverage"]["ratio"] == 1 / 3


def test_tx_contract_keys_do_not_make_legitimate_contract_rows_duplicates():
    report = build_taifex_quality_report(
        {
            "taifex_tx_daily_contract_v1": [
                {
                    "observation_date": "2024-01-02",
                    "source_record_key": "TX|202401|一般",
                },
                {
                    "observation_date": "2024-01-02",
                    "source_record_key": "TX|202402|一般",
                },
            ]
        },
        expected_dates=["2024-01-02"],
        calendar_status="available",
    )

    dataset = report["datasets"]["taifex_tx_daily_contract_v1"]
    assert dataset["duplicate_dates"] == []
    assert dataset["available_date_count"] == 1
    assert report["gate_status"] == "pass"
