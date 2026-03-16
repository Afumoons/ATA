# execution/ – Live Trade Execution & Daily State

## Purpose

This module is responsible for **turning strategy signals into real MT5 trades**
and for **tracking live account state** used by risk controls:

- Execute trades via the MetaTrader5 Python API with basic sizing & logging.
- Enforce risk decisions from `risk/manager.py` before sending any order.
- Maintain daily state (PnL, return %, trade count, daily lockout).
- Record equity history and wire closed MT5 deals into `DailyState`.
- Track per-strategy live PnL stats (including a recent rolling window) for
  degradation detection.

## Key Files

- `engine.py`
  - Thin wrapper around MT5 order execution.
  - Computes volume from `risk_perc` and `stop_loss_pips`.
  - Calls `validate_trade(...)` from `risk.manager` before sending any order.
  - Logs each executed trade to `trades.log`.

- `signals.py`
  - Bridges **backtested strategies** into **live execution**.
  - For the latest feature row per symbol/timeframe:
    - Generates entry signals by reusing backtest rule evaluation.
    - Checks daily limits via `can_open_new_trade(...)` from `live_state_utils`.
    - Loads `active` strategies from the strategy pool and executes them via `engine.execute_trade()`.

- `live_state_utils.py`
  - Defines `DailyState` structure stored in `live_state.json`.
  - Functions:
    - `load_daily_state(...)` / `save_daily_state(...)` – read/write daily snapshot.
    - `register_trade_pnl(pnl, current_equity)` – update `daily_pnl`, `daily_return_pct`, `trades_today`.
    - `can_open_new_trade(current_equity, max_dd_pct, max_trades, enabled)` – gate for daily DD/trade caps.

- `live_monitor.py`
  - Tracks overall equity history in `equity_history.json`.
  - Maintains `peak_equity` and can **disable all active strategies** in the pool when portfolio DD exceeds a hard threshold.
  - Wires **real closed MT5 deals** into `DailyState` by:
    - Pulling `mt5.history_deals_get(last_check_time, now)`.
    - Filtering for close/exit deals.
    - For each new deal, calling `register_trade_pnl(pnl, equity_now)`.
    - Tracking processed tickets in `closed_trades_state.json` so deals are not double-counted.
  - Additionally updates per-strategy live stats by reading MT5 `deal.comment`
    (set as `"clio-auto-{strategy_name}"` by `engine.execute_trade`).

- `strategy_live_stats.py`
  - Maintains aggregated **live PnL per strategy** in
    `execution/strategy_live_stats.json`.
  - Core pieces:
    - `StrategyLiveStats` dataclass – `name`, `total_pnl`, `num_trades`,
      `last_update`, and `recent_pnls` (rolling window of the last
      `MAX_RECENT_TRADES` PnLs).
    - `load_all_strategy_stats()` / `save_all_strategy_stats(...)` – I/O helpers.
    - `register_strategy_pnl(strategy_name, pnl)` – called from `live_monitor` for
      each closed MT5 deal tagged with that strategy's comment; keeps
      `recent_pnls` capped at `MAX_RECENT_TRADES`.

## Data & State Files

- `execution/trades.log`
  - Append-only log of executed trades (strategy, symbol, direction, volume, price, SL/TP, MT5 ticket).

- `execution/live_state.json`
  - JSON-serialized `DailyState` object:
    - `date` – trading date (UTC ISO string).
    - `equity_start` / `equity_current`.
    - `daily_pnl` – current-equity minus start-equity.
    - `daily_return_pct` – percent return for the day.
    - `trades_today` – number of closed trades that day.
    - `locked_for_day` – when true, no new trades should be opened (enforced by `can_open_new_trade`).

- `execution/equity_history.json`
  - Tracks `equity_history` and `times` arrays over time, plus `peak_equity`.
  - Used for monitoring portfolio drawdown and optionally disabling all live strategies.

- `execution/closed_trades_state.json`
  - Internal state for PnL wiring:
    - `last_check_time` – last time we queried `mt5.history_deals_get`.
    - `processed_deal_ids` – list of MT5 deal tickets already applied to `DailyState`.

- `execution/strategy_live_stats.json`
  - Aggregated live PnL stats per strategy:
    - `total_pnl`, `num_trades`, `avg_pnl`, `last_update`, `recent_pnls`.
  - Intended as an input for **strategy degradation detection** and
    live-aware promotion/demotion logic in the strategy pool.

## How It’s Used

- `scheduler/main.py` calls into this module via jobs such as:
  - `job_execute_signals` →
    - loads latest features,
    - loads `active` strategies from the pool,
    - calls `signals.execute_signals_for_symbol(...)` per symbol/timeframe.
  - `job_live_monitor` →
    - calls `live_monitor.update_live_stats()` periodically to:
      - append to equity history,
      - wire closed MT5 deals into `DailyState`,
      - update per-strategy live stats (including the recent PnL window),
      - enforce portfolio-level DD safety switches.

- Risk interaction:
  - `engine.execute_trade(...)` uses `risk.manager.validate_trade(...)` to decide whether a trade is allowed.
  - `signals.execute_signals_for_symbol(...)` uses `can_open_new_trade(...)` to enforce **daily DD / trade-count limits**.

## Gotchas / Notes

- All PnL & daily state are assumed to be **per account**, not per strategy.
- Per-strategy stats in `strategy_live_stats.json` are **aggregated PnL only**;
  they do not yet reflect exact per-strategy equity curves or volatility.
- `live_monitor` uses MT5 **deal history**; make sure MT5 history is not truncated too aggressively by the broker/terminal.
- On first run, `closed_trades_state.json` may look back a default window (e.g. 7 days) and will then converge as trades are processed once.
- If symbols, pip size conventions, or account precision differ by broker, adjust:
  - `pip_size` logic in `signals.execute_signals_for_symbol(...)` and `engine.execute_trade(...)` as needed.
