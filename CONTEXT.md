# Domain Context

This repository describes a Taiwan market scoring system built from dated official market observations and derived factor results.

## Core terms

- **Observation**: A value reported by an official source for an observation date and source record key.
- **Source revision**: A distinct official version or correction of an observation that must remain traceable to the version it supersedes.
- **Quality status**: The availability state of an observation, including whether it is usable, not yet published, empty, failed, invalid, or not applicable.
- **Factor result**: A derived value and score calculated from a defined set of observations, formula, model version, and as-of boundary.
- **Market Score**: The weighted aggregate of the versioned factor results for a market date.
- **As-of boundary**: The latest information that the system is allowed to use when producing a factor result, Market Score, or backtest observation.
- **Dashboard data cutoff**: The trading date shown to a public dashboard visitor as `資料截至`; the UI intentionally does not expose the 16:30 or 22:00 collection checkpoint.
- **Forward-filled display**: A chart-only continuation of the last available score across a missing date, marked with a dashed segment and `前值遞補`; it never changes the persisted score.
- **Data-quality warning**: The warning icon and tooltip shown when a Market Score is unavailable or a factor has an explicit quality issue.
- **Factor explanation**: The four public fields shown below the selected factor chart: purpose, data window, calculation logic, and score direction.
