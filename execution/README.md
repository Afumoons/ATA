# execution/ – Live Trade Execution, Daily State & Live Stats

## Purpose

This module is responsible for **turning strategy signals into real MT5 trades**
and for **tracking live account state** used by risk controls:

- Execute trades via the MetaTrader5 Python API with basic sizing & logging.
- Enforce risk decisions from `risk/manager.py` before sending any order.
- Enforce **daily loss/trade caps** before opening new trades.
- Maintain daily state (PnL, return %, trade count, daily lockout).
- Record equity history and wire closed MT5 deals into `DailyState`.
- Track per-strategy live PnL stats (including a recent rolling window) for
  degradation detection.
- Enforce a portfolio-level **circuit breaker** based on drawdown from
  peak equity.

## Key Files

- `engine.py`
  - Thin wrapper around MT5 order execution.
  - Computes volume from `risk_perc` and `stop_loss_pips`.
  - Calls `validate_trade(...)` from `risk.manager` before sending any order.
  - Logs each executed trade to `trades.log`.

- `signals.py`
  - Bridges **backtested strategies** into **live execution** with
    regime-aware filtering, session-aware eligibility gating, per-tier risk control, and daily guardrails.
  - For the latest feature row per symbol/timeframe:
    - Reads the current routing context from features and logs it per symbol/timeframe (`regime` + derived `session`).
    - Logs a feature snapshot (time, regime, key indicators like MA short/long,
      trend strength, RSI) to aid post-mortem analysis.
    - Pulls `risk_config` and uses `can_open_new_trade(...)` from
      `live_state_utils` to enforce **daily limits** using
      `risk_config.max_daily_drawdown_pct`, `risk_config.max_trades_per_day`,
      and `risk_config.daily_limits_enabled` (enabled by default for live
      accounts). When these limits are hit, **no new trades are opened** for
      the rest of the day.
    - Uses `strategy_has_open_position(...)` to enforce the current live policy:
      **one open MT5 position per strategy + symbol + timeframe slot**.
      This blocks accidental pyramiding/re-entry while the prior position is
      still open.
    - Loads `active` and `exploratory` strategies from the strategy pool for the
      given symbol/timeframe.
    - Applies a **session hard gate** using explicit routing metadata from
      `strategy_explain.meta`:
      - if `blocked_sessions` contains the current session → reject,
      - if `allowed_sessions` exists and the current session is not included → reject.
    - Applies a **regime policy gate** using explicit routing metadata from
      `strategy_explain.meta`:
      - if `blocked_regimes` contains the current legacy regime label → reject,
      - if `allowed_regimes` exists and the current legacy regime label is not included → reject.
    - Uses structured regime context already present in features (`regime_class`,
      `regime_type`, `regime_confidence`, `vol_regime`) for logging and
      conservative confidence gating.
    - Computes a regime-specific edge for each strategy using
      `strategy_explain.regime_pnl[regime_label].return_pct` (via `_regime_edge`).
    - Applies regime-based thresholds:
      - `ACTIVE_REGIME_EDGE_THRESHOLD = 0.0` → active strategies only trade in
        regimes that were historically profitable (edge > 0) for that strategy.
      - `EXPLORATORY_REGIME_EDGE_THRESHOLD = -10.0` → exploratory tier is looser
        to allow data gathering, with a fallback that keeps the best strategy
        even if none pass the threshold.
    - Uses confidence-aware routing gates before edge ranking:
      - `MIN_REGIME_CONFIDENCE_ACTIVE = 0.35`
      - `MIN_REGIME_CONFIDENCE_EXPLORATORY = 0.20`
      Low-confidence contexts are treated as ineligible for the relevant tier.
    - Ranks strategies by edge and caps how many are allowed to fire per run
      (e.g. top 5 active, top 3 exploratory).
    - Distinguishes:
      - no eligible specialists after routing gates,
      - no strategies with acceptable edge,
      - no entry trigger on otherwise eligible strategies.
    - Uses **two risk tiers** when executing via `engine.execute_trade()`:
      - `active` strategies trade at the normal configured per-trade risk
        (`risk_perc`, typically up to 1% of equity based on
        `risk_config.max_risk_per_trade_pct`).
      - `exploratory` strategies trade at a significantly reduced per-trade
        risk (`min(risk_perc * 0.25, 0.1)`), keeping exploratory exposure small.
    - Returns a list of `(Signal, reason)` tuples plus a summary dict so
      callers (e.g. `scheduler.job_execute_signals`) can log exactly why each
      trade was accepted, rejected, or blocked by guards (daily limits, session
      gate, regime filter, no entries).

- `live_state_utils.py`
  - Defines `DailyState` structure stored in `live_state.json`.
  - Functions:
    - `load_daily_state(...)` / `save_daily_state(...)` – read/write daily snapshot.
    - `register_trade_pnl(pnl, current_equity)` – update `daily_pnl`, `daily_return_pct`, `trades_today`.
    - `strategy_has_open_position(strategy_name, symbol, timeframe)` – MT5 open-position guard for the current single-position mode.
    - `can_open_new_trade(current_equity, max_dd_pct, max_trades, enabled)` – gate for daily DD/trade caps.

- `live_monitor.py`
  - Tracks overall equity history in `equity_history.json`.
  - Maintains `peak_equity` and can **disable all active strategies** in the
    pool when portfolio DD exceeds `risk_config.max_portfolio_drawdown_pct`.
  - Wires **real closed MT5 deals** into `DailyState` by:
    - Pulling `mt5.history_deals_get(last_check_time, now)`.
    - Filtering for close/exit deals.
    - Fetching current account equity once per update.
    - For each new deal, calling `register_trade_pnl(pnl, equity_now)`.
    - Tracking processed tickets in `closed_trades_state.json` so deals are not double-counted.
  - Additionally updates per-strategy live stats by reading MT5 `deal.comment`
    (set as `"clio-auto-{strategy_name}"` by `engine.execute_trade`).
  - Uses `risk_config.max_portfolio_drawdown_pct` as the **circuit breaker
    threshold**; once exceeded, all `active` strategies in the pool are
    demoted to `disabled` and the updated pool is saved.

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
  - Used for monitoring portfolio drawdown and triggering the circuit breaker.

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
    - enforces **news lockout** using `in_news_lockout` (no signal generation
      when a high-impact macro event is within ±15 minutes),
    - loads `active` strategies from the pool,
    - computes risk-per-trade as `min(1.0, risk_config.max_risk_per_trade_pct)`,
    - calls `signals.execute_signals_for_symbol(...)` per symbol/timeframe.
  - `job_live_monitor` →
    - calls `live_monitor.update_live_stats()` periodically to:
      - append to equity history,
      - wire closed MT5 deals into `DailyState`,
      - update per-strategy live stats (including the recent PnL window),
      - enforce portfolio-level DD safety and disable active strategies when
        drawdown exceeds `risk_config.max_portfolio_drawdown_pct`.

- Risk interaction:
  - `engine.execute_trade(...)` uses `risk.manager.validate_trade(...)` to decide whether a trade is allowed.
  - `signals.execute_signals_for_symbol(...)` uses `can_open_new_trade(...)` to enforce **daily DD / trade-count limits** when `risk_config.daily_limits_enabled` is `True`.

## Gotchas / Notes

- All PnL & daily state are assumed to be **per account**, not per strategy.
- Per-strategy stats in `strategy_live_stats.json` are **aggregated PnL only**;
  they do not yet reflect exact per-strategy equity curves or volatility.
- `live_monitor` uses MT5 **deal history**; make sure MT5 history is not truncated too aggressively by the broker/terminal.
- On first run, `closed_trades_state.json` may look back a default window (e.g. 7 days) and will then converge as trades are processed once.
- Daily guardrails in `signals.py` are **enabled by default** via
  `risk_config.daily_limits_enabled = True`. Set this to `False` in `config.py`
  if you want to disable daily DD / trade-count caps (e.g. for backtesting).

## Changelog (Docs)

- 2026-03-21: Documented daily-guardrails integration, news lockout behaviour,
  circuit breaker tied to `risk_config.max_portfolio_drawdown_pct`, and the
  two-tier risk structure for active vs exploratory strategies.
