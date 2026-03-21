# data/ – Market Data & News Ingestion

## Purpose

This module handles **market data ingestion from MetaTrader 5** and persistence
to disk so that research, backtests, and live trading all share a consistent
source of OHLC data.

It also contains a **macro news collector** that fetches economic calendar data
from Forex Factory and stores it under `data/raw/` for use by
`research/features.py` and the notifications system.

It focuses on:

- Connecting to the MT5 terminal.
- Fetching OHLC bars for configured symbols/timeframes.
- Saving raw OHLC data under `data/raw/`.
- Fetching and maintaining a gold-relevant macro news calendar
  (`news_events.parquet`).

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
    - Anchors at `datetime.now(timezone.utc)` and returns **UTC-aware**
      timestamps – this matches `features.py`, which expects UTC-aware times
      for correct joins with news events.
    - First tries `mt5.copy_rates_from(symbol, tf, now, n_bars)`.
    - If that fails (returns `None`), logs `mt5.last_error()` and falls back to
      `mt5.copy_rates_from_pos(symbol, tf, 0, fallback_bars)` with a reduced
      bar count.
    - Returns a pandas DataFrame with columns:
      - `time` (UTC-aware pandas `datetime`),
      - `open`, `high`, `low`, `close`, `tick_volume`.
  - `save_ohlc(df, symbol, timeframe)` – writes OHLC to
    `data/raw/{symbol}_{timeframe}_ohlc.parquet` and logs the path.

- `news_collector.py`
  - Fetches macro events from **Forex Factory** public JSON feeds:
    - `ff_calendar_thisweek.json`
    - `ff_calendar_nextweek.json`
  - Focused on events that are **gold-relevant** (XAUUSDm) by currency and
    keyword filter.
  - Core helpers:
    - `fetch_ff_calendar(weeks=2)` – pulls the raw calendar and normalises it
      into a DataFrame with columns:
      - `datetime_utc` – event time (UTC-aware),
      - `currency` – e.g. `USD`, `EUR`, ...,
      - `impact` – integer 0–3 (`High` → 3, `Medium` → 2, `Low` → 1,
        `Holiday` → 0),
      - `event_name`, `forecast`, `previous`,
      - `is_gold_relevant` – boolean flag.
    - `load_news_events()` / `save_news_events(df)` – I/O helpers for
      `data/raw/news_events.parquet`.
    - `update_news_events()` – idempotent merge of new calendar data into the
      existing parquet file (deduplicates by `(datetime_utc, event_name)`).
    - `get_upcoming_high_impact(hours_ahead=4.0, min_impact=3, gold_relevant_only=True)` –
      returns a filtered DataFrame of high-impact upcoming events within the
      next N hours, used by the scheduler for WhatsApp alerts and
      pre-event lockouts.

## Directories

- `data/raw/`
  - Parquet files with raw OHLCV data per symbol/timeframe
    (`{symbol}_{timeframe}_ohlc.parquet`).
  - `news_events.parquet` containing macro events from Forex Factory.
  - Used as the input to `research/features.py` (both price and news
    context).

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

`news_collector.py` has no external configuration; it uses Forex Factory's
public JSON API and stores results under `data/raw/news_events.parquet`.

## How It’s Used

- `scheduler/main.py` → `job_update_data()`:
  - For each managed symbol:
    - Calls `fetch_ohlc(symbol, timeframe=TIMEFRAME)`.
    - Calls `save_ohlc(df, symbol, TIMEFRAME)`.
    - Passes the resulting DataFrame on to `research.compute_features(...)`.

- `scheduler/main.py` → `job_update_news()` (daily at 06:00 UTC):
  - Calls `update_news_events()` to refresh `news_events.parquet`.
  - Calls `get_upcoming_high_impact(...)` to detect important upcoming events
    and forwards them to `notifications.whatsapp_notifier.send_news_alert(...)`.

- `scheduler/main.py` → `job_news_alert()` (every 5 minutes):
  - Uses `get_upcoming_high_impact(...)` to look for events within the next
    hour and triggers WhatsApp alerts as needed (with cooldowns).

- `research/features.py`:
  - Calls `_load_news_events()` which reads `news_events.parquet` via
    `news_collector.load_news_events()` and filters to `is_gold_relevant`.
  - Joins news context into features (time deltas, impact level, lockout
    flags) via `_add_news_features(...)`.

## Gotchas / Notes

- **MT5 Terminal must be running and logged into the correct account** before
  `initialize_mt5()` is called, otherwise `mt5.initialize()` will fail.
- All times are handled as **UTC-aware** datetimes; mixing naive and
  timezone-aware timestamps will cause subtle bugs in joins, which is why
  both OHLC and news data are normalised to UTC in this module.
- If both `copy_rates_from` and `copy_rates_from_pos` fail, a `RuntimeError` is
  raised with both MT5 error codes to aid debugging.
- If Forex Factory endpoints are unavailable, `news_collector` logs warnings
  and returns an empty DataFrame; downstream code degrades gracefully and
  simply behaves as if there is "no news".

## Changelog (Docs)

- 2026-03-21: Documented `news_collector.py`, UTC-aware OHLC timestamps, and
  scheduler jobs for news updates / alerts.
