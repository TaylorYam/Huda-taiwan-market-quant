# Factor Specification Index

The current v0.1 factor definitions, weights, and initial scoring rules live in [`factor-model-v0.1.md`](factor-model-v0.1.md). Keep that versioned model as the single source of truth for factor meaning and score behavior; this index intentionally avoids duplicating its rules.

Supporting policies:

- [`data-window-policy-v0.1.md`](data-window-policy-v0.1.md) defines historical lookback windows and point-in-time data rules.
- [`backtest-spec-v0.1.md`](backtest-spec-v0.1.md) defines the initial backtest design and evaluation requirements.
- [`roadmap-v0.1.md`](roadmap-v0.1.md) sequences the future data, factor, scoring, backtest, dashboard, and automation work, with issue-ready acceptance criteria.
- [`data-contract-v0.1.md`](data-contract-v0.1.md) defines shared date, timestamp, unit, revision, and missing-data semantics for future collectors.
- [`phase0-source-research-v0.1.md`](phase0-source-research-v0.1.md) records verified official source windows, free BFI82U/FMTQIK candidates, and remaining retrieval checks.

The model, data-window policy, and backtest spec are draft v0.1 specifications. Confirm source fields, publication times, and historical availability before implementation, then validate scoring thresholds and weights against reproducible historical data. Use the roadmap to sequence that work; it does not override the model definitions.
