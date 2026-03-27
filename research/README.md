# research/ – Features, News Context & Regimes

## Purpose

This module transforms raw price data into the **feature and context layer**
used by both research and live execution.

It is responsible for:

- technical feature computation
- optional macro-news context joins
- structured regime classification
- preserving a simple compatibility regime label for older logic

Pass 3 increases the importance of this module because live execution now uses
more of the structured context directly instead of collapsing everything into a
single coarse label.

## Core Outputs

The research pipeline produces feature sets that can include:

- OHLC-derived indicators
- moving-average context
- RSI
- ATR
- volatility
- ATR-normalized trend strength
- Ichimoku state
- Fibonacci-zone flags
- macro-news context fields
- legacy `regime`
- structured regime fields:
  - `regime_class`
  - `regime_type`
  - `regime_confidence`
  - `vol_regime`

These outputs are saved under `data/features/` and used across backtests,
scheduler research jobs, and live signal routing.

## Key Files

### `features.py`

Builds the main feature matrix.

Important helpers include:

- `compute_rsi(...)`
- `compute_atr(...)`
- `compute_volatility(...)`
- `compute_trend_strength(...)`
- `compute_ichimoku(...)`
- `compute_fib_zones(...)`

News-related helpers include:

- `_load_news_events()`
  - loads normalized news data from `data/raw/news_events.parquet`
- `_add_news_features(...)`
  - adds fields such as:
    - `news_impact_level`
    - `news_time_delta_min`
    - `has_news_window`
    - `in_news_lockout`

Main entry points:

- `compute_features(df, symbol, timeframe, ...)`
- `save_features(df, symbol, timeframe)`
- `load_features(symbol, timeframe)`

### `regime.py`

Builds the market-regime layer.

Important functions include:

- `detect_regime_structured(...)`
  - classifies each bar into structured regime outputs
- `detect_regime(...)`
  - returns a legacy simplified regime label
- `add_regime_column(df, ...)`
  - attaches both compatibility and structured regime fields
- `calibrate_thresholds(...)`
  - helps tune thresholds if feature definitions change materially

Important concepts include:

- `RegimeClass`
- `RegimeType`
- `RegimeHints`
- `RegimeSnapshot`

## Pass 3 Role

In pass 3, `research/` becomes the **context engine** for live routing.

The execution path now depends on this module not only for indicators, but for
higher-level context such as:

- whether the market is trending, ranging, spiking, or event-driven
- whether volatility state mismatches a strategy’s specialty
- whether regime confidence is strong enough to allow routing
- whether the market is within a high-impact macro lockout window

That means this module now affects:

- candidate evaluation quality
- live gating quality
- specialist-regime matching
- news-aware execution safety

## How It’s Used

### `scheduler.job_update_data()`

1. raw OHLC is fetched from `data/`
2. `compute_features(...)` builds the indicator + context matrix
3. `add_regime_column(...)` attaches regime outputs
4. final feature parquet is saved

### `scheduler.job_research_strategies()`

- loads saved features
- uses the data for backtests and strategy evaluation
- benefits from both legacy regime labels and richer context inside explainability

### `scheduler.job_execute_signals()` / `execution.signals`

- reads latest feature row
- uses `in_news_lockout` to skip trading near high-impact events
- uses `regime`, `regime_class`, `regime_type`, `regime_confidence`, and
  `vol_regime` to route specialists more intelligently

## Design Notes

### Legacy + structured coexistence

The simplified `regime` label still exists because older code paths and some
reporting flows rely on it. But new logic should prefer structured fields where
possible.

### ATR-normalized trend strength

Trend strength is normalized relative to ATR so thresholds remain more stable
across different price levels and instruments.

### Optional news context

News joins are designed to degrade gracefully:

- if valid news data exists, features gain macro context
- if not, safe default columns are created so downstream code keeps working

## Gotchas / Notes

- Timezone hygiene is critical. Feature timestamps and news timestamps should
  remain UTC-aware.
- If indicator windows or ATR logic change materially, regime thresholds may
  need recalibration.
- Structured regime output should be treated as probabilistic context, not
  infallible truth; this is why `regime_confidence` exists.
- For pass 3, bad context here will propagate into both research scoring and
  live execution routing.

## Changelog (Docs)

- 2026-03-21: Documented features, ATR-normalized trend strength, news context,
  and structured regime outputs.
- 2026-03-27: Updated for pass 3 with stronger framing of `research/` as the
  live-routing context engine and clarified the importance of structured fields.