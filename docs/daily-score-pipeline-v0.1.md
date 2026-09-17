# Daily Score Pipeline v0.1

`src/scoring/pipeline.py` is the first executable join between the factor
adapters and the Market Score contract. It accepts the saved daily
observations, applies the explicit target date and `as_of` boundary, scores
each factor, and returns a report that retains source identities.

```python
from src.scoring import calculate_daily_score

result = calculate_daily_score(
    taiex_observations=taiex_rows,
    pcr_observations=pcr_rows,
    tx_observations=tx_rows,
    vix_observations=vix_rows,
    target_date="2026-09-17",
    historical_values={
        "taiex_20d_momentum": previous_momentum_values,
        "tx_basis": previous_basis_values,
        "txo_oi_pcr": previous_pcr_values,
        "taiwan_vix": previous_vix_values,
    },
)
```

The history mapping must contain only values known by the selected `as_of`
boundary. If a percentile history is absent, or if a required source factor is
unavailable, the result remains explicitly `unavailable`; the pipeline does
not fill the gap with a neutral score or renormalize weights.

`DailyScoreResult.as_dict()` is intended as the stable handoff to a future
dashboard or persistence writer. It includes the model version, score state,
factor values, factor score states, windows, reasons, and source observation
identities.

The current source contract still marks the foreign cash factor and the two
foreign TX open-interest factors unavailable. Therefore this pipeline can
produce a fully evidenced partial factor report now, while the aggregate
Market Score remains unavailable until those source gates are closed.
