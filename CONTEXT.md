# Domain Context

This repository describes a Taiwan market scoring system built from dated official market observations and derived factor results.

## Core terms

- **Observation**: A value reported by an official source for an observation date and source record key.
- **Source revision**: A distinct official version or correction of an observation that must remain traceable to the version it supersedes.
- **Quality status**: The availability state of an observation, including whether it is usable, not yet published, empty, failed, invalid, or not applicable.
- **Factor result**: A derived value and score calculated from a defined set of observations, formula, model version, and as-of boundary.
- **Market Score**: The weighted aggregate of the versioned factor results for a market date.
- **As-of boundary**: The latest information that the system is allowed to use when producing a factor result, Market Score, or backtest observation.
