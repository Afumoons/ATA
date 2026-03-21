# research/ – Features, News Context & Regimes

## Purpose

This module turns raw OHLC data into **feature-rich, regime-aware datasets**
used by backtests, strategy evolution, live signal generation, and
news-aware risk controls.

It focuses on:

- Computing technical indicators and derived features.
- Joining optional macro news context from `data/news_collector.py`.
- Classifying market regimes (trend, range, volatility spike, event-driven, etc.).
- Providing a simple legacy `regime` label column for compatibility while also
  exposing richer structured regime information.

## Key Files

- `features.py`
  - Feature engineering for each symbol/timeframe.
  - Core indicator helpers:
    - `compute_rsi(close, period=14)` – Wilder-style RSI using `ewm(..., adjust=False)`
      to match MT5 / TradingView.
    - `compute_atr(df, period=14)` – Wilder ATR using `ewm(..., adjust=False)`.
    - `compute_volatility(close, window=20)` – rolling std of returns.
    - `compute_trend_strength(close, atr, window=50)` – **ATR-normalised** slope of a
      rolling mean; this keeps values in a stable range across different price
      levels and underpins the regime thresholds.
    - `compute_ichimoku(df)` – adds unshifted Ichimoku lines (Tenkan/Kijun/Senkou
      A/B) plus boolean flags (`above_cloud`, `below_cloud`, `in_cloud`).
      - Senkou spans are **not shifted into the future**; they represent the
        instantaneous cloud a live system would actually see.
      - `chikou_span` is intentionally excluded to avoid forward-looking data.
    - `compute_fib_zones(df, window=100)` – flags when price is near 38.2% or
      61.8% retracement in a rolling range.
  - News-related helpers (backed by `data/news_collector.py`):
    - `_load_news_events()` – loads `data/raw/news_events.parquet` (via
      `news_collector.load_news_events()`), filters to `is_gold_relevant`, and
      normalises timestamps to `datetime_utc` (UTC-aware).
      - Falls back to a legacy format with a `time` column if present.
      - Returns `None` if no usable data exists; caller degrades gracefully.
    - `_add_news_features(df, news, window_min=60, lockout_min=15)` – adds columns:
      - `news_impact_level` – integer impact level (0–3).
      - `news_time_delta_min` – signed minutes to nearest event
        (negative = before event).
      - `has_news_window` – within `window_min` of an impact ≥ 2 event.
      - `in_news_lockout` – within `lockout_min` of an impact = 3 event.
      - Implementation is fully vectorised (`O(n_bars + n_events)`), not
        `O(n_bars × n_events)`.
  - Main entry points:
    - `compute_features(df, symbol, timeframe, ...)`:
      - Assumes OHLC input: `['time', 'open', 'high', 'low', 'close', 'tick_volume']`.
      - Sorts by time and converts `time` to **UTC-aware** datetimes.
      - Computes all indicators and trend-strength using ATR-normalisation.
      - Adds Ichimoku and Fibonacci-zone features.
      - Joins optional news features; if no news is available, creates safe
        default columns so downstream code never `KeyError`s.
      - Drops rows with `NaN` in core feature columns (`rsi`, `ma_short`,
        `ma_long`, `atr`, `volatility`, `trend_strength`).
      - Returns a cleaned feature DataFrame.
    - `save_features(df, symbol, timeframe)` – stores features in
      `data/features/{symbol}_{timeframe}_features.parquet`.
    - `load_features(symbol, timeframe)` – loads precomputed features.

- `regime.py`
  - Implements **structured regime detection** aligned with Clio's trading
    regime spec and the ATR-normalised `trend_strength` scale.
  - Key types:
    - `RegimeClass` – high-level categories: `"trend"`, `"range"`,
      `"breakout"`, `"mean_reversion"`, `"volatility_spike"`,
      `"low_liquidity"`, `"event_driven"`, `"unknown"`.
    - `RegimeType` – more granular labels (e.g. `"uptrend_strong"`,
      `"range_tight"`, `"vol_spike_up"`, `"macro_news_high_impact"`, ...).
    - `RegimeHints` – suggestions for risk/playbooks
      (e.g. `risk_mode`, `position_sizing_factor`, allowed/disabled playbooks).
    - `RegimeSnapshot` – dataclass capturing a full regime snapshot for a bar
      (used internally; written out as dicts in the final DataFrame).
  - Core functions:
    - `detect_regime_structured(df, timeframe, cfg=DEFAULT_REGIME_CONFIG, version="v2")`:
      - Requires `trend_strength` and `volatility` columns in `df`.
      - Optionally uses `in_news_lockout` and `news_impact_level` when present
        to label **event-driven** regimes around high-impact macro events.
      - Computes volatility quantiles using a rolling window
        (`cfg.vol_quantile_window`) for more stable thresholds.
      - Classifies each bar into `regime_class` / `regime_type`.
      - Computes `regime_confidence` and a volatility bucket (`vol_regime`).
      - Produces hints (`regime_hints`) and an explain object (`regime_explain`).
      - Returns a **fully vectorised** DataFrame of snapshots aligned with `df`.
    - `detect_regime(df, cfg=DEFAULT_REGIME_CONFIG)`:
      - Legacy helper returning a simple `RegimeLabel` series
        (`"trending_up"`, `"trending_down"`, `"ranging"`, `"high_vol"`,
        `"low_vol"`).
      - Internally calls `detect_regime_structured` and compresses the result.
    - `add_regime_column(df, cfg=DEFAULT_REGIME_CONFIG)`:
      - Convenience wrapper that adds a `regime` column (legacy label) plus
        the key structured fields (`regime_class`, `regime_type`,
        `regime_confidence`, `vol_regime`).
  - Calibration helper:
    - `calibrate_thresholds(df, ...)` – analyses a few weeks of live features
      and suggests `RegimeConfig` thresholds suitable for the current
      ATR-normalised scale; helpful if you change ATR or MA windows.

## Directories

- `data/features/`
  - Destination for feature parquet files created by `save_features(...)`.
  - Read by `scheduler.job_research_strategies`, `job_execute_signals`, and
    news-aware lockout checks.

## How It’s Used

- `scheduler/job_update_data()`:
  - Calls `compute_features(df, symbol, TIMEFRAME)` after fetching OHLC.
  - Calls `add_regime_column(feat)` to attach both the simple `regime` label and
    structured regime information.
  - Saves the result via `save_features(...)`.

- `scheduler/job_research_strategies()`:
  - Loads features with `load_features(symbol, TIMEFRAME)`.
  - Uses the `regime` column (legacy label) for backtests and evaluation.
  - Uses other feature columns (including news-related ones) indirectly via
    `backtests/engine.py` and `backtests/explain.py`.

- `scheduler/job_execute_signals()`:
  - Loads features to get the latest `regime` label and news context.
  - Uses the latest row’s `regime` label in `execution.signals` to compute
    regime-specific edge when filtering strategies.
  - Uses `in_news_lockout` to **skip signal generation entirely** when a
    high-impact macro event is within the lockout window.

- `notifications/whatsapp_notifier.py` (indirect):
  - News features are built from the same `news_events.parquet` that powers
    WhatsApp alerts about upcoming macro events.

## Gotchas / Notes

- News features are **optional**: if `news_events.parquet` is missing or
  malformed, they are quietly skipped, and only technical features are used
  (with safe default columns to keep downstream code robust).
- Regime detection thresholds are tuned for **ATR-normalised**
  `trend_strength`. If you change ATR or MA parameters in `features.py`, run
  `calibrate_thresholds(...)` on a representative features sample before
  adjusting `RegimeConfig`.
- Structured regimes (`detect_regime_structured`) carry richer information
  (confidence, event-driven flags, hints) and should be preferred for any new
  code; the legacy `regime` label is kept primarily for backwards
  compatibility.

## Changelog (Docs)

- 2026-03-21: Updated for ATR-normalised `trend_strength`, Forex Factory-based
  news features, event-driven regimes, and the news lockout integration in the
  scheduler / execution path.
