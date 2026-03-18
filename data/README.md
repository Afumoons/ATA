# data/ – Market Data Ingestion

## Purpose

This module handles **market data ingestion from MetaTrader 5** and persistence
to disk so that research, backtests, and live trading all share a consistent
source of OHLC data.

It focuses on:

- Connecting to the MT5 terminal.
- Fetching OHLC bars for configured symbols/timeframes.
- Saving raw OHLC data under `data/raw/`.

Feature engineering and regime detection are handled separately under
`research/`.

## Key Files

- `collector_mt5.py`
  - `initialize_mt5()` / `shutdown_mt5()` – open/close the MetaTrader 5
    connection used by the rest of the system.
  - `fetch_ohlc(symbol, timeframe=None, bars=None)` – fetch OHLCV data from MT5
    with a robust fallback strategy:
    - Uses `data_config.mt5_timeframe_default` and
      `data_config.history_bars_default` when args are not provided.
    - Maps higher-level timeframe strings (`"M15"`, `"H1"`, etc.) to MT5
      constants via `TIMEFRAME_MAP`.
    - First tries `mt5.copy_rates_from(symbol, tf, now, n_bars)`.
    - If that fails (returns `None`), logs `mt5.last_error()` and falls back to
      `mt5.copy_rates_from_pos(symbol, tf, 0, fallback_bars)`.
    - Returns a pandas DataFrame with columns:
      - `time` (converted to pandas `datetime`),
      - `open`, `high`, `low`, `close`, `tick_volume`.
  - `save_ohlc(df, symbol, timeframe)` – writes OHLC to
    `data/raw/{symbol}_{timeframe}_ohlc.parquet` and logs the path.

## Directories

- `data/raw/`
  - Parquet files with raw OHLCV data per symbol/timeframe.
  - Used as the input to `research/features.py`.

- `data/features/`
  - Not written directly by this module, but closely related. See
    `research/README.md` for details on feature files.

## Configuration

`collector_mt5.py` relies on `DataConfig` in `config.py`:

```python
@dataclass
class DataConfig:
    mt5_timeframe_default: str = "M15"
    history_bars_default: int = 2000

data_config = DataConfig()
```

These defaults are used when `timeframe` or `bars` are not provided explicitly
in `fetch_ohlc(...)`.

## How It’s Used

- `scheduler/main.py` → `job_update_data()`:
  - For each managed symbol:
    - Calls `fetch_ohlc(symbol, timeframe=TIMEFRAME)`.
    - Calls `save_ohlc(df, symbol, TIMEFRAME)`.
    - Passes the resulting DataFrame on to `research.compute_features(...)`.

- Setup scripts / manual diagnostics can also call `initialize_mt5()` and
  `fetch_ohlc(...)` directly to verify connectivity and data availability.

## Gotchas / Notes

- **MT5 Terminal must be running and logged into the correct account** before
  `initialize_mt5()` is called, otherwise `mt5.initialize()` will fail.
- Time is handled in UTC when anchoring `copy_rates_from` at `datetime.utcnow()`.
- If both `copy_rates_from` and `copy_rates_from_pos` fail, a `RuntimeError` is
  raised with both MT5 error codes to aid debugging.
- The `NEWS`-related files (e.g. `news_events.parquet`) referenced in
  `research/features.py` live under `data/raw/` but are **optional** for this
  module; `collector_mt5.py` itself does not depend on them.
