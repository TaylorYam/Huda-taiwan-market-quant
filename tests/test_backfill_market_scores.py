from __future__ import annotations

from dataclasses import dataclass

from scripts.backfill_market_scores import (
    existing_available_target_dates,
    existing_target_dates,
    existing_target_dates_for_refresh,
    group_observations,
    has_complete_raw_evidence,
    summarize_results,
)
from src.scoring.contracts import REQUIRED_FACTOR_IDS
from src.scoring.pipeline import calculate_daily_score


@dataclass(frozen=True)
class Row:
    dataset_id: str


def test_group_observations_keeps_only_declared_dataset_contracts() -> None:
    grouped = group_observations(
        [Row("twse_taiex_daily_v1"), Row("unknown"), Row("taifex_txo_oi_pcr_v1")]
    )

    assert [row.dataset_id for row in grouped["twse_taiex_daily_v1"]] == [
        "twse_taiex_daily_v1"
    ]
    assert [row.dataset_id for row in grouped["taifex_txo_oi_pcr_v1"]] == [
        "taifex_txo_oi_pcr_v1"
    ]
    assert all(
        not rows
        for dataset, rows in grouped.items()
        if dataset
        not in {
            "twse_taiex_daily_v1",
            "taifex_txo_oi_pcr_v1",
        }
    )


def test_existing_target_dates_include_unavailable_rows() -> None:
    assert existing_target_dates(
        [
            {"target_date": "2026-01-02", "status": "unavailable"},
            {"target_date": "2026-01-03", "status": "available"},
            {"target_date": None},
            {},
        ]
    ) == {"2026-01-02", "2026-01-03"}


def test_existing_available_target_dates_ignore_unavailable_rows() -> None:
    assert existing_available_target_dates(
        [
            {"target_date": "2026-01-02", "status": "unavailable"},
            {"target_date": "2026-01-03", "status": "available"},
            {"target_date": None, "status": "available"},
            {},
        ]
    ) == {"2026-01-03"}


def test_raw_evidence_refresh_only_selects_available_incomplete_rows() -> None:
    complete = {
        factor_id: {
            "status": "available",
            "raw_value": 1,
            "raw_values": {"value": 1},
        }
        for factor_id in REQUIRED_FACTOR_IDS
    }
    rows = [
        {
            "target_date": "2026-01-02",
            "status": "available",
            "factor_scores_json": complete,
        },
        {
            "target_date": "2026-01-03",
            "status": "available",
            "factor_scores_json": {
                REQUIRED_FACTOR_IDS[0]: complete[REQUIRED_FACTOR_IDS[0]]
            },
        },
        {"target_date": "2026-01-04", "status": "unavailable"},
    ]

    assert has_complete_raw_evidence(rows[0])
    assert not has_complete_raw_evidence(rows[1])
    assert existing_target_dates_for_refresh(
        rows,
        refresh_unavailable=False,
        refresh_missing_raw=True,
    ) == {"2026-01-02", "2026-01-04"}
    assert existing_target_dates_for_refresh(
        rows,
        refresh_unavailable=True,
        refresh_missing_raw=True,
    ) == {"2026-01-02"}


def test_summary_does_not_turn_unavailable_into_zero() -> None:
    result = calculate_daily_score(
        taiex_observations=[],
        pcr_observations=[],
        tx_observations=[],
        vix_observations=[],
        target_date="2026-01-02",
    )

    summary = summarize_results(
        [result],
        start_date="2026-01-01",
        end_date="2026-01-31",
        skipped_existing_dates=0,
        write=False,
    )

    assert summary["candidate_days"] == 1
    assert summary["start_date"] == "2026-01-01"
    assert summary["end_date"] == "2026-01-31"
    assert summary["available_days"] == 0
    assert summary["unavailable_days"] == 1
    assert summary["reason_counts"] == {"missing_or_unavailable_required_factors": 1}
    assert summary["missing_factor_counts"]
    assert summary["unavailable_samples"][0]["target_date"] == "2026-01-02"
