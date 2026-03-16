# scheduler/ – Orchestration & Background Jobs

## Purpose

This module is the **central orchestrator** for the autonomous trading system. It
runs a set of recurring jobs using `APScheduler` to keep everything in sync:

- Update OHLC data, features, and regimes for managed symbols.
- Research/evolve strategies and maintain the strategy pool.
- Generate and execute live trade signals.
- Monitor live equity and daily state for safety.

It is effectively the "brainstem" that wires together `data/`, `research/`,
`strategies/`, `backtests/`, `execution/`, and `vector_memory/`.

## Key Files

- `main.py`
  - Defines all scheduled jobs and how often they run.
  - Knows which symbols and timeframe to manage via `MANAGED_SYMBOLS` and `TIMEFRAME`.
  - Exposes `start_scheduler()` / `shutdown_scheduler()` and a simple
    `if __name__ == "__main__":` runner.

## Core Jobs

### `job_update_data()`

**Goal:** Keep OHLC + features + regimes fresh for each managed symbol.

Pipeline per symbol:

1. `fetch_ohlc(symbol, timeframe=TIMEFRAME)` – pull latest price data from MT5.
2. `save_ohlc(df, symbol, TIMEFRAME)` – persist raw OHLC under `data/raw/`.
3. `compute_features(df, symbol, TIMEFRAME)` – compute indicators/features.
4. `add_regime_column(feat)` – attach market regime labels.
5. `save_features(feat, symbol, TIMEFRAME)` – store final feature set under
   `data/features/`.

Errors per symbol are logged but do **not** stop other symbols from updating.

### `job_research_strategies()`

**Goal:** Continuously evolve, backtest, and evaluate strategies, updating both
`StrategyPool` and research memory.

Per symbol:

1. Load features via `load_features(symbol, TIMEFRAME)`.
2. Select up to 20 best parent strategies from the pool for that symbol/timeframe.
3. Load their `StrategyDefinition` JSONs from `strategies/generated/`.
4. Call `evolve_population(symbol, TIMEFRAME, existing_strats)` to generate a new
   population.
5. For each strategy in the population:
   - Run `run_backtest(...)` using the current features.
   - Evaluate with `evaluate_strategy(result.stats)`.
   - Skip strategies with too few trades (`num_trades < 5`).
   - Run robustness checks:
     - Walk-forward test via `walk_forward_test(...)`.
     - Monte Carlo PnL via `monte_carlo_pnl(...)`.
   - Merge robustness stats into `eval_result`.
   - Decide pool status using `_should_promote(stats)`:
     - `active`   → meets stricter performance criteria (PnL > 0, DD <= 20%,
                   PF >= 1.1, good trend performance, not terrible in ranges,
                   sufficient trade count).
     - `candidate` → meets base acceptance criteria.
     - `disabled` → otherwise.
   - Call `pool.upsert_strategy(...)` to update `StrategyPool`.
   - Store evaluation in `ResearchMemory` (Chroma-backed) via
     `memory.store_strategy_result(...)`.

Finally, `save_pool(pool)` persists the updated pool to disk.

### `job_execute_signals()`

**Goal:** Turn the latest features + active strategies into **live MT5 trades**.

Workflow:

1. Load the latest `StrategyPool` via `load_pool()`.
2. Compute per-trade risk percentage as `min(0.5, risk_config.max_risk_per_trade_pct)`.
3. For each managed symbol:
   - Load features with `load_features(symbol, TIMEFRAME)`.
   - Call `execute_signals_for_symbol(symbol, TIMEFRAME, feat, pool, risk_perc)` from
     `execution.signals`.
   - Log each signal outcome (executed / skipped / rejected by risk).

Within `execute_signals_for_symbol`:

- Daily limits are enforced via `can_open_new_trade(...)` from
  `execution.live_state_utils` using `risk_config.max_daily_drawdown_pct`,
  `risk_config.max_trades_per_day`, and `risk_config.daily_limits_enabled`.
- Only `active` strategies for the given symbol/timeframe are considered.

### `job_live_monitor()`

**Goal:** Track live equity and enforce portfolio-level safety.

- Calls `update_live_stats()` from `execution.live_monitor`:
  - Appends current account equity to `equity_history.json`.
  - Maintains `peak_equity` and computes drawdown.
  - Wires closed MT5 deals into `DailyState` (PnL, return %, trades_today).
  - Can disable all active strategies in the pool if portfolio DD exceeds a
    hardcoded safety threshold.

Errors are logged but do not stop the scheduler.

## Scheduler Lifecycle

- `start_scheduler()`
  - Respects `scheduler_config.enable_scheduler`; if disabled, returns a dummy
    `BackgroundScheduler` and logs a warning.
  - Calls `initialize_mt5()` **once** at startup.
  - Creates a `BackgroundScheduler(timezone="UTC")`.
  - Registers jobs:
    - `job_update_data`      every 5 minutes.
    - `job_research_strategies` every 30 minutes.
    - `job_execute_signals`  every 5 minutes.
    - `job_live_monitor`     every 5 minutes.
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
