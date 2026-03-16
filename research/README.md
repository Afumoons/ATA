# research/ – Features & Regimes

## Purpose

This module turns raw OHLC data into **feature-rich, regime-aware datasets**
used by backtests, strategy evolution, and live signal generation.

It focuses on:

- Computing technical indicators and derived features.
- Joining optional macro news context.
- Classifying market regimes (trend, range, volatility spike, etc.).
- Providing a simple legacy `regime` label column for compatibility.

## Key Files

- `features.py`
  - Feature engineering for each symbol/timeframe.
  - Core indicator helpers:
    - `compute_rsi(close, period=14)`.
    - `compute_atr(df, period=14)`.
    - `compute_volatility(close, window=20)`.
    - `compute_trend_strength(close, window=50)` – normalized slope of a rolling mean.
    - `compute_ichimoku(df)` – adds Ichimoku lines (Tenkan/Kijun/Senkou/Chikou).
    - `compute_fib_zones(df, window=100)` – flags when price is near 38.2% or
      61.8% retracement in a rolling range.
  - News-related helpers:
    - `_load_news_events()` – loads `data/raw/news_events.parquet` if present,
      returning a DataFrame of macro events (time, impact, surprise, etc.).
    - `_add_news_features(df, news, window_min=30)` – adds columns such as:
      - `news_time_delta_min` – minutes to nearest news event.
      - `news_impact_level` – mapped to integer impact (low/medium/high).
      - `news_surprise` – surprise metric from the news file.
      - `has_news_window` – within a configurable window of any event.
      - `in_news_lockout` – high-impact event within the window.
  - Main entry points:
    - `compute_features(df, symbol, timeframe, ...)`:
      - Assumes OHLC input: `["time", "open", "high", "low", "close", "tick_volume"]`.
      - Sorts by time, computes all indicators, joins optional news features,
        drops incomplete rows, and returns a cleaned feature DataFrame.
    - `save_features(df, symbol, timeframe)` – stores features in
      `data/features/{symbol}_{timeframe}_features.parquet`.
    - `load_features(symbol, timeframe)` – loads precomputed features.

- `regime.py`
  - Implements **structured regime detection** aligned with Clio's trading
    regime spec.
  - Key types:
    - `RegimeClass` – high-level categories: `"trend"`, `"range"`,
      `"breakout"`, `"mean_reversion"`, `"volatility_spike"`, etc.
    - `RegimeType` – more granular labels (e.g. `"uptrend_strong"`,
      `"range_tight"`, `"vol_spike_up"`, ...).
    - `RegimeHints` – suggestions for risk/playbooks
      (e.g. `risk_mode`, `position_sizing_factor`, allowed/disabled playbooks).
    - `RegimeSnapshot` – dataclass capturing a full regime snapshot for a bar.
  - Core functions:
    - `detect_regime_structured(df, timeframe, cfg=DEFAULT_REGIME_CONFIG, version="v1")`:
      - Requires `trend_strength` and `volatility` columns in `df`.
      - Computes volatility quantiles from the sample.
      - Classifies each bar into `regime_class` / `regime_type`.
      - Computes `regime_confidence` and a volatility bucket (`vol_regime`).
      - Produces hints (`regime_hints`) and an explain object (`regime_explain`).
      - Returns a DataFrame of snapshots indexed like `df`.
    - `detect_regime(df, cfg=DEFAULT_REGIME_CONFIG)`:
      - Legacy helper returning a simple `RegimeLabel` series
        ("trending_up", "trending_down", "ranging", "high_vol", "low_vol").
      - Internally uses `detect_regime_structured` and compresses the result.
    - `add_regime_column(df, cfg=DEFAULT_REGIME_CONFIG)`:
      - Convenience wrapper that adds a `regime` column to `df` using
        `detect_regime` (legacy interface).

## Directories

- `data/features/`
  - Destination for feature parquet files created by `save_features(...)`.
  - Read by `scheduler.job_research_strategies` and `job_execute_signals`.

## How It’s Used

- `scheduler/job_update_data()`:
  - Calls `compute_features(df, symbol, TIMEFRAME)` after fetching OHLC.
  - Calls `add_regime_column(feat)` to attach a simple `regime` label.
  - Saves the result via `save_features(...)`.

- `scheduler/job_research_strategies()`:
  - Loads features with `load_features(symbol, TIMEFRAME)`.
  - Uses the `regime` column (legacy label) for backtests and evaluation.
  - Future work can adopt the full `detect_regime_structured` output.

## Gotchas / Notes

- News features are **optional**: if `news_events.parquet` is missing or
  malformed, they are quietly skipped, and only technical features are used.
- Regime detection currently relies on `trend_strength` and `volatility` from
  `compute_features`; any change to those definitions will impact regime labels.
- For new code, prefer **structured regimes** (`detect_regime_structured`) and
  join them explicitly instead of relying solely on the legacy `regime` label.
