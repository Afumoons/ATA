# data/ – Market Data & News Ingestion

## Purpose

This module is the project’s **input layer**.

It is responsible for collecting and persisting:

- raw OHLCV market data from MetaTrader 5
- macro calendar data from Forex Factory

Everything downstream depends on this module being clean and consistent:

- research
- backtests
- live execution
- news-aware lockout logic
- alerting

## Scope

This module focuses on:

- connecting to MT5
- fetching OHLC bars for configured symbols/timeframes
- saving raw parquet inputs under `data/raw/`
- refreshing and storing normalized macro news events

It does **not** handle:

- feature engineering
- regime detection
- strategy logic

Those belong to `research/`.

## Key Files

### `collector_mt5.py`

Handles MT5 connectivity and OHLC fetching.

Important functions:

- `initialize_mt5()` / `shutdown_mt5()`
  - open and close the MT5 connection used by the rest of the system
- `fetch_ohlc(symbol, timeframe=None, bars=None)`
  - fetches OHLCV bars from MT5
  - uses config defaults when args are omitted
  - normalizes timestamps to **UTC-aware** datetimes
  - includes fallback logic when the primary MT5 copy call fails
- `save_ohlc(df, symbol, timeframe)`
  - writes OHLC parquet under `data/raw/{symbol}_{timeframe}_ohlc.parquet`

### `news_collector.py`

Handles macro news ingestion from Forex Factory JSON feeds.

Important helpers:

- `fetch_ff_calendar(weeks=2)`
  - fetches one or more weekly FF calendars and normalizes them into a DataFrame
- `load_news_events()` / `save_news_events(df)`
  - reads/writes `data/raw/news_events.parquet`
- `update_news_events()`
  - refreshes and merges FF events into the local store idempotently
- `get_upcoming_high_impact(...)`
  - finds near-term, high-impact events for lockout and alerting flows

### `news_schema.md`

Human-readable schema notes for the normalized news dataset.

This is documentation for the structure expected by the research and
notification layers.

## Data Outputs

### `data/raw/`

This folder stores canonical raw inputs such as:

- `{symbol}_{timeframe}_ohlc.parquet`
- `news_events.parquet`

These files are the upstream source for feature generation.

### `data/features/`

This folder is not written by `data/` directly, but it is the immediate next
stage in the pipeline and is populated by `research/features.py`.

## Pass 3 Relevance

In pass 3, the data module becomes more important because the rest of the
system now depends on **better contextual inputs**, not just price bars.

Key pass 3 implications:

- OHLC timestamps must remain reliably **UTC-aware** to join correctly with
  macro events.
- News data is now part of the practical live-routing stack through:
  - `news_impact_level`
  - `news_time_delta_min`
  - `has_news_window`
  - `in_news_lockout`
- The alerting layer also depends on the same normalized news store for
  pre-event notifications.

## Configuration

### Market data

`collector_mt5.py` relies on `DataConfig` in `config.py`, including defaults like:

- default timeframe
- default history-bar count

### News data

`news_collector.py` is intentionally lightweight and relies on:

- Forex Factory public JSON feeds
- local parquet persistence under `data/raw/`

No complex external service configuration is required beyond network access.

## How It’s Used

### `scheduler.job_update_data()`

For each managed symbol:

1. fetch OHLC from MT5
2. save raw OHLC
3. pass the DataFrame to `research.compute_features(...)`

### `scheduler.job_update_news()`

- refreshes the local FF calendar
- stores/upserts `news_events.parquet`
- supports summary alert generation for upcoming events

### `scheduler.job_news_alert()`

- queries the normalized news store for imminent events
- hands those events to the notifier layer

### `research/features.py`

- loads `news_events.parquet`
- joins macro context into the feature matrix

## Gotchas / Notes

- MT5 must be running and connected to the intended account before
  `initialize_mt5()` succeeds.
- Mixing naive timestamps with UTC-aware timestamps will create subtle,
  damaging join bugs. This module should continue to normalize everything to UTC.
- If FF endpoints fail, downstream code is designed to degrade gracefully and
  continue without news context.
- The data module should remain conservative and boring: correctness and
  timestamp hygiene matter more than cleverness here.

## Changelog (Docs)

- 2026-03-21: Documented MT5 OHLC ingestion, Forex Factory news ingestion,
  and scheduler integration.
- 2026-03-27: Refreshed for pass 3 with stronger emphasis on UTC hygiene,
  normalized news inputs, and the module’s role in news-aware routing + alerts.