# Dashboard Frontend v0.2

This document records the public display contract confirmed for the Streamlit
dashboard. It describes presentation behavior only; scoring remains calculated
and persisted by the daily scoring pipeline.

## Page order

1. Summary: Market Score, market state, daily change, data cutoff date, model
   version, and a data-quality warning when the score is unavailable.
2. Linked chart: Taiwan Weighted Index daily candlesticks as the main pane and
   Market Score as the score pane.
3. Factor tabs and selected-factor trend pane.
4. Persisted factor table. It renders all persisted factor rows without an
   inner vertical scroll area.
5. Collapsed source data quality section.

Factor tabs wrap onto additional rows when the viewport is narrow, so every
label remains directly visible and selectable without horizontal scrolling.

## Linked chart behavior

- The chart title is `台灣加權指數 · Market Score`.
- The main pane renders daily OHLC candlesticks only.
- The Market Score pane and selected factor pane share the candle dates, visible
  range, crosshair, and zoom/pan interaction.
- The default visible range is the latest six months. Buttons switch to 1M, 3M,
  6M, 1Y, or 全部.
- Mouse-wheel zoom changes the horizontal and vertical view together; dragging
  moves the visible date range. Each pane auto-scales its Y axis to visible data.
- Market Score uses a stable blue. The eight factors use eight additional stable
  colors so a factor keeps the same color across sessions.
- Missing values remain missing. When a previous value is continued for visual
  context, the segment is dashed and the chart marks it `前值遞補`.

## Summary and quality states

- Scores and factor values display to one decimal place.
- Every factor score is labelled `分數（0–100）`. The page explains that this is
  a historical-distribution or rule-based transformation, not the source unit.
- New persisted score rows expose the raw factor input and unit next to the
  normalized score. Older rows that do not contain raw evidence say
  `原始值尚未儲存`; the dashboard never reconstructs it.
- `資料截至` displays only the trading target date. Collection checkpoints and
  write timestamps are hidden from the public page.
- Daily change compares the current available score with the previous available
  score date, skipping unavailable dates.
- An unavailable Market Score remains unavailable and is never converted to zero.
  The warning icon tooltip includes the reason and asks the visitor to contact
  the developer.
- K-line and any available factor data remain visible when the Market Score is
  unavailable.

## Factor explanations

Each factor tab follows the selected factor and shows exactly four explanation
fields below its chart:

- 判斷用途
- 資料窗口
- 計算邏輯
- 分數方向

Source attribution and data-quality detail stay in the collapsed source section;
they are not repeated in every factor explanation.
