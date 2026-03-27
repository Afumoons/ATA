# execution/ – Live Trade Execution, Daily State & Live Monitoring

## Purpose

This module is the live side of the system.

It is responsible for:

- converting eligible strategy signals into real MT5 orders
- enforcing live routing and risk gates before orders are sent
- tracking daily account state and drawdown
- wiring closed MT5 deals back into account and strategy state
- maintaining open-trade and per-strategy live snapshots

Pass 3 significantly strengthens this module by making it more explicitly
**routing-aware**, **stateful**, and **observable**.

## Key Responsibilities

### 1) Order execution

- validate proposed trades against account-level risk rules
- size and submit MT5 orders
- log executed trades

### 2) Live signal gating

- apply daily limits
- enforce one-open-position-per-strategy slot rules
- apply session and regime routing gates
- apply volatility mismatch and confidence gates
- rank strategies by edge
- run separate exposure tiers for `active` vs `exploratory`

### 3) State tracking

- maintain daily PnL and trade counts
- maintain equity history and peak equity
- process closed MT5 deals exactly once
- aggregate live PnL by strategy
- snapshot open trades and ticket-to-strategy mappings

## Key Files

### `engine.py`

Thin wrapper around MT5 order placement.

Responsibilities:

- compute volume from risk inputs and SL distance
- call `risk.manager.validate_trade(...)`
- place the order through MT5 when allowed
- log successful executions to `trades.log`
- tag trades with strategy-identifying comments for later monitoring

### `signals.py`

This is the core **live routing layer**.

It bridges saved research outputs into real-time execution.

Important behavior includes:

- reading the latest feature row and routing context
- using `can_open_new_trade(...)` to enforce daily limits
- using `strategy_has_open_position(...)` to prevent accidental re-entry/pyramiding
- selecting `active` and `exploratory` strategies for the current symbol/timeframe
- applying session hard gates from `strategy_explain.meta`
- applying regime allow/block policies from `strategy_explain.meta`
- expanding coarse regimes into candidate labels using structured regime context
- applying volatility mismatch guards
- using `regime_confidence` to reject weak-confidence contexts
- loading live routing switches/thresholds from `autonomous_trading_ai.config.routing_config`
- ranking strategies by regime-specific edge
- executing with normal risk for `active` and reduced risk for `exploratory`
- returning structured outcome info so the scheduler can log why trades were or were not taken

This file is where pass 3’s specialist-routing behavior becomes operational.

### `live_state_utils.py`

Maintains day-level risk/account state.

Main roles:

- read/write `live_state.json`
- track:
  - `daily_pnl`
  - `daily_return_pct`
  - `trades_today`
  - `locked_for_day`
- update state when new closed PnL arrives
- enforce daily trade-count and drawdown limits
- check whether a strategy already has an open live slot

### `live_monitor.py`

Monitors the actual account and synchronizes MT5 reality back into the system.

Responsibilities:

- update `equity_history.json`
- maintain `peak_equity`
- query MT5 closed deals
- register newly closed trade PnL into daily state
- update per-strategy live PnL stats
- enforce the portfolio circuit breaker by disabling live-tier strategies
  (`active` and `exploratory`) when drawdown breaches the configured threshold

### `live_observer.py`

Observation/snapshot utilities for the live account.

This file supports lightweight views such as open-trade snapshots so the system
and human operator can inspect current exposure without reconstructing it from
raw MT5 calls each time.

### `strategy_live_stats.py`

Maintains aggregated per-strategy live performance.

Typical fields include:

- total PnL
- number of trades
- average PnL
- last update time
- recent rolling window of trade outcomes

These stats are used downstream by the scheduler’s degradation logic.

## State Files

Pass 3 makes the execution state surface more explicit.

### `execution/trades.log`

Append-only log of executed live orders.

### `execution/live_state.json`

Daily account-state snapshot, including:

- date
- starting/current equity
- daily PnL
- daily return %
- number of closed trades today
- day lock status

### `execution/equity_history.json`

Time-series equity history plus peak-equity tracking.

Used for portfolio drawdown monitoring and circuit-breaker enforcement.

### `execution/closed_trades_state.json`

Internal bookkeeping for closed-deal processing.

Used to prevent double-counting the same MT5 deal.

### `execution/strategy_live_stats.json`

Aggregated live performance by strategy.

Used by degradation logic and operator inspection.

### `execution/open_trades.json`

Snapshot of current open trades for quick inspection and tooling.

### `execution/ticket_strategy_map.json`

Maps MT5 trade identifiers back to strategy identity when needed for later
attribution and monitoring flows.

## Pass 3 Live Routing Model

The live execution path now behaves more like a specialist dispatcher than a
simple “top-score strategy executor.”

It can combine:

- current session context
- current regime context
- volatility regime
- regime confidence
- strategy allow/block metadata
- backtest-derived regime edge
- tiered exposure sizing

So a strategy may be skipped even if it has a high total score, because:

- it is blocked for the current session
- it is blocked for the current regime
- the volatility state is a poor fit
- confidence is too low
- it already has an open live slot
- daily limits are hit
- no current entry trigger exists

That is intentional. Pass 3 favors **controlled specialist deployment** over
looser general execution.

## How It’s Used

### `scheduler.job_execute_signals()`

- loads features and strategy pool
- checks macro-news lockout
- computes live risk tier
- calls `signals.execute_signals_for_symbol(...)`

### `scheduler.job_live_monitor()`

- calls `live_monitor.update_live_stats()`
- updates equity history, daily state, live strategy stats, and circuit-breaker state
- may also refresh open-trade snapshots depending on observer wiring

### `risk/manager.py`

- validates proposed trades before MT5 submission

## Gotchas / Notes

- This module operates on **real account state**; debugging scripts can cause
  real actions if they invoke execution code.
- Daily state is account-level, not strategy-level.
- Per-strategy live stats are intentionally lighter than a full strategy-level
  equity curve model.
- MT5 deal-history availability matters; truncated broker/terminal history can
  affect reconstruction.
- The circuit breaker currently acts by disabling `active` strategies in the
  pool; that is a deliberate safety mechanism, not just a log event.

## Changelog (Docs)

- 2026-03-21: Documented daily guardrails, news lockout, circuit breaker,
  and active/exploratory risk tiers.
- 2026-03-27: Updated for pass 3 with explicit routing behavior, expanded live
  state artifacts (`open_trades.json`, `ticket_strategy_map.json`, observer
  flows), and stronger emphasis on the specialist-dispatch model.