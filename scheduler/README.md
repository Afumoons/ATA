# scheduler/ – Orchestration, Background Jobs & News/Alerts

## Purpose

This module is the **central orchestrator** for the autonomous trading system. It
runs a set of recurring jobs using `APScheduler` to keep everything in sync:

- Update OHLC data, features, and regimes for managed symbols.
- Research/evolve strategies and maintain the strategy pool.
- Generate and execute live trade signals with regime-aware and news-aware
  guards.
- Monitor live equity and daily state for safety.
- Fetch macro news (Forex Factory), maintain a local news calendar, and send
  WhatsApp alerts before high-impact events.

It is effectively the "brainstem" that wires together `data/`, `research/`,
`strategies/`, `backtests/`, `execution/`, `vector_memory/`, and
`notifications/`.

## Key Files

- `main.py`
  - Defines all scheduled jobs and how often they run.
  - Knows which symbols and timeframe to manage via `MANAGED_SYMBOLS` and `TIMEFRAME`.
  - Exposes `start_scheduler()` / `shutdown_scheduler()` and a simple
    `if __name__ == "__main__":` runner.

## Configuration: Symbols, Timeframe & Risk

- `MANAGED_SYMBOLS` (currently):

  ```python
  MANAGED_SYMBOLS = ["XAUUSDm"]
  TIMEFRAME = "M15"
  ```

  BTC was removed from the default loop for now; add it back here if you want
  to trade it.

- Per-trade risk in live execution is computed as:

  ```python
  risk_perc = min(1.0, risk_config.max_risk_per_trade_pct)
  ```

  With the default `RiskConfig`, this caps risk at **1% per trade**.

## Core Jobs

### `job_update_data()`

**Goal:** Keep OHLC + features + regimes fresh for each managed symbol.

Pipeline per symbol:

1. `fetch_ohlc(symbol, timeframe=TIMEFRAME)` – pull latest price data from MT5.
2. `save_ohlc(df, symbol, TIMEFRAME)` – persist raw OHLC under `data/raw/`.
3. `compute_features(df, symbol, TIMEFRAME)` – compute indicators/features
   (including news context when available).
4. `add_regime_column(feat)` – attach market regime labels and structured
   regime metadata.
5. `save_features(feat, symbol, TIMEFRAME)` – store final feature set under
   `data/features/`.

Errors per symbol are logged but do **not** stop other symbols from updating.

### `job_research_strategies()`

**Goal:** Continuously evolve, backtest, and evaluate strategies, updating both
`StrategyPool` and research memory.

Per symbol:

1. Load features via `load_features(symbol, TIMEFRAME)`.
2. Construct a `ResearchMemory` instance pointing at the configured Chroma
   collection.
3. Select up to 20 best parent strategies from the pool for that symbol/timeframe.
4. For each parent candidate, compute a **memory-based bonus** that nudges the
   GA toward pattern families that have historically worked well on this
   symbol/timeframe:
   - Build a rich query text from the strategy's rules (`long_entry_rule`,
     `short_entry_rule`, `exit_rule`, `sl_atr_mult`, `tp_atr_mult`, regime
     parameters, etc.).
   - Use `ResearchMemory.query_similar_strategies(...)` to fetch neighbors from
     past research runs.
   - Aggregate neighbor stats (Sharpe, profit factor, return %) into a small
     bonus/penalty in the range `[-0.2, +0.2]`.
   - Add this to the parent's base score to form a "hybrid" parent score.
5. Sort parents by hybrid score and keep the top N as the GA breeding pool.
6. Load their `StrategyDefinition` JSONs from `strategies/generated/` and call
   `evolve_population(symbol, TIMEFRAME, existing_strats)` to generate a new
   population.
7. For each strategy in the population:
   - Optionally **skip clearly bad pattern families** via
     `_memory_is_clearly_bad(...)`, which queries similar past strategies in
     `ResearchMemory` and checks if most neighbors have obviously poor stats.
   - Run `run_backtest(...)` using the current features.
   - Evaluate with `evaluate_strategy(result.stats)`.
   - Enforce Phase 3 floors:
     - Minimum trade count (`num_trades >= 50`).
     - Minimum profit factor and Sharpe (e.g. `pf >= 1.05`, `sharpe >= 0.15`).
   - Run robustness checks:
     - Walk-forward test via `walk_forward_test(...)` and attach
       `wf_overall_sharpe` and `wf_overall_max_drawdown_pct`.
     - Monte Carlo PnL via `monte_carlo_pnl(...)` (reduced `n_runs` for speed).
   - Decide pool status using `_should_promote(stats)` and additional heuristics:
     - `active`       → meets stricter performance criteria (PnL > 0, DD <= 20%,
                        PF >= 1.1, good trend performance, not terrible in
                        ranges, sufficient trade count, robust WF Sharpe).
     - `exploratory`  → accepted strategies with enough trades and positive
                        performance in trending regimes, but not yet strong
                        enough for `active`.
     - `candidate`    → accepted but weaker strategies.
     - `disabled`     → otherwise.
   - Persist and log explicit routing metadata from
     `strategy_explain.meta` (best/worst regime/session, allowed/blocked
     regimes/sessions, routing confidence) so later routing stages can use a
     durable specialist policy surface rather than re-inferring everything.
   - Call `pool.upsert_strategy(...)` to update `StrategyPool`.
   - Store evaluation in `ResearchMemory` (Chroma-backed) via
     `memory.store_strategy_result(...)`.

After updating the pool based on backtests, a **live degradation pass** runs
using `execution/strategy_live_stats.json` to conservatively demote clearly
underperforming `active` strategies back to `candidate` based on their
aggregated live PnL and a rolling window of recent trade outcomes. A WhatsApp
alert is sent via `send_strategy_degradation_alert(...)` when a strategy is
explicitly degraded.

Finally, `pool.prune(...)` (invoked from `StrategyPool` usage) keeps the number
of inactive strategies bounded so `pool_state.json` does not grow without
limit, and `save_pool(pool)` persists the updated pool to disk.

### `job_execute_signals()`

**Goal:** Turn the latest features + regime-aware strategy pool into **live MT5 trades**.

Workflow:

1. Load the latest `StrategyPool` via `load_pool()`.
2. Compute per-trade risk percentage as
   `risk_perc = min(1.0, risk_config.max_risk_per_trade_pct)`.
3. For each managed symbol:
   - Load features with `load_features(symbol, TIMEFRAME)`.
   - Check **news lockout**: if the most recent feature row has
     `in_news_lockout=True`, skip signal generation entirely for this symbol to
     avoid trading during the highest-impact macro events.
   - If there are no `active` strategies for this symbol/timeframe, log and
     skip.
   - Warn if any `active` strategies have edge scores below
     `MINIMUM_EDGE_FOR_EXECUTION`.
   - Call `execute_signals_for_symbol(symbol, TIMEFRAME, feat, pool, risk_perc)`
     from `execution.signals`.
   - Log each signal outcome (executed / skipped / rejected by risk / blocked by
     daily limits / blocked by regime filters).

Within `execute_signals_for_symbol` (documented in `execution/README.md`):

- Daily limits are enforced via `can_open_new_trade(...)` from
  `execution.live_state_utils` using `risk_config.max_daily_drawdown_pct`,
  `risk_config.max_trades_per_day`, and `risk_config.daily_limits_enabled`.
- Strategies with status `active` and `exploratory` for the given symbol/timeframe
  are considered.
- The latest feature row’s `regime` label is used to compute regime-specific edge
  from `strategy_explain.regime_pnl`, filter out poor performers in the current
  regime, and cap how many strategies per tier are allowed to fire.
- Before regime ranking, live routing now also applies a **session hard gate**
  using `strategy_explain.meta.allowed_sessions` / `blocked_sessions`.
- `active` strategies trade at the normal risk tier, while `exploratory` strategies
  trade at a significantly reduced per-trade risk.

### `job_live_monitor()`

**Goal:** Track live equity and enforce portfolio-level safety.

- Calls `update_live_stats()` from `execution.live_monitor`:
  - Appends current account equity to `equity_history.json`.
  - Maintains `peak_equity` and computes drawdown.
  - Wires closed MT5 deals into `DailyState` and per-strategy live stats.
  - If drawdown exceeds `risk_config.max_portfolio_drawdown_pct`, automatically
    disables all `active` strategies in the pool (circuit breaker).

Errors are logged but do not stop the scheduler.

### `job_update_news()`

**Goal:** Keep the local macro news calendar fresh and summarise upcoming
high-impact gold events.

- Runs once daily at **06:00 UTC**.
- Uses `data.news_collector.update_news_events()` to refresh
  `data/raw/news_events.parquet`.
- Uses `get_upcoming_high_impact(...)` to find upcoming high-impact,
  gold-relevant events.
- Builds an optional `account_info` snapshot from MT5 (`equity` and
  `peak_equity`).
- Calls `notifications.whatsapp_notifier.send_news_alert(...)` to send a
  WhatsApp summary for upcoming events (if any) via OpenClaw's webhook.

### `job_news_alert()`

**Goal:** Send near-term WhatsApp alerts for imminent high-impact events.

- Runs every **5 minutes**.
- Uses `get_upcoming_high_impact(hours_ahead=1.0, min_impact=3, gold_relevant_only=True)`
  to look for events in the next hour.
- Filters events based on a per-event cooldown (default 60 minutes) in
  `whatsapp_notifier` so the same event is not spammed.
- Sends alerts via `send_news_alert(...)` with optional account snapshot.

## Scheduler Lifecycle

- `start_scheduler()`
  - Respects `scheduler_config.enable_scheduler`; if disabled, returns a dummy
    `BackgroundScheduler` and logs a warning.
  - Calls `initialize_mt5()` **once** at startup.
  - Creates a `BackgroundScheduler(timezone="UTC")`.
  - Registers jobs:
    - `job_update_data`         every 5 minutes.
    - `job_research_strategies` every 30 minutes.
    - `job_execute_signals`     every 5 minutes.
    - `job_live_monitor`        every 5 minutes.
    - `job_update_news`         daily at 06:00 UTC.
    - `job_news_alert`          every 5 minutes.
  - Starts the scheduler and returns the instance.

- `shutdown_scheduler(sched)`
  - Shuts down APScheduler.
  - Calls `shutdown_mt5()` to cleanly close the MT5 connection.

- CLI usage:
  - Running `python -m autonomous_trading_ai.scheduler.main` will:
    - Call `start_scheduler()`.
    - Sleep in a loop until `KeyboardInterrupt`.
    - On Ctrl+C, call `shutdown_scheduler(...)`.

## Gotchas / Notes

- `MANAGED_SYMBOLS` and `TIMEFRAME` are currently hardcoded in `main.py`.
  - Change them here if you want additional symbols or different timeframes.
- All scheduling is in **UTC**; make sure any time-based logic in other modules
  (e.g. session detection) uses consistent timezones.
- If features are missing (`FileNotFoundError`), jobs log a warning and skip
  that symbol gracefully.
- Because `job_research_strategies` can be more expensive, it runs less
  frequently (every 30 minutes) than data updates and signal execution.
- News-related jobs and WhatsApp alerts are best-effort: failures to fetch
  Forex Factory or send alerts are logged but do **not** stop the core
  trading loop.

## Changelog (Docs)

- 2026-03-21: Updated for news-related jobs (`job_update_news`, `job_news_alert`),
  the single-symbol default (`XAUUSDm`), per-trade risk cap at 1%, news lockout
  in `job_execute_signals`, and live strategy degradation with WhatsApp alerts.
