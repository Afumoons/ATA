# risk/ – Central Risk Management

## Purpose

This module contains the **account-level trade validation layer**.

It answers a simple question before an order is sent:

**Should this trade be allowed at all?**

It is deliberately narrower than the execution module. It does not decide:

- whether a strategy is good
- whether the current regime is a fit
- whether a signal exists

Instead, it enforces hard account-level constraints such as:

- max risk per trade
- max concurrent open positions
- max drawdown from peak equity

## Key File

### `manager.py`

Defines the core dataclasses and validation pipeline.

Important types:

- `AccountState`
- `TradeRequest`
- `RiskDecision`

Important checks:

- `check_max_risk_per_trade(account, req)`
- `check_max_open_positions(account)`
- `check_drawdown(equity_peak, account)`
- `validate_trade(account, req, equity_peak)`

The validation path runs checks in order and returns the first failing reason.

## Relationship to Other Safety Layers

This module is only **one layer** in the safety stack.

### This module owns

- per-trade risk cap
- account-level open-position cap
- drawdown cap relative to peak equity

### Other modules own

- daily drawdown / daily trade-count caps
  - `execution/live_state_utils.py`
- session/regime/confidence gating
  - `execution/signals.py`
- circuit-breaker state transitions in the pool
  - `execution/live_monitor.py`

That separation is intentional.

## Configuration

Risk thresholds are defined in `config.py` through `RiskConfig`.

Typical fields include:

- `max_risk_per_trade_pct`
- `max_portfolio_drawdown_pct` (current local deployment intentionally uses `75.0`; treat this as deployment-specific policy, not an assumed universal default)
- `max_open_positions`
- `max_daily_drawdown_pct`
- `max_trades_per_day`
- `daily_limits_enabled`

### Used directly by `risk/manager.py`

- `max_risk_per_trade_pct`
- `max_portfolio_drawdown_pct`
- `max_open_positions`

### Used by adjacent daily-guardrail logic

- `max_daily_drawdown_pct`
- `max_trades_per_day`
- `daily_limits_enabled`

## Pass 3 Relevance

Pass 3 makes execution routing more selective, but it does **not** reduce the
need for hard account-level risk controls.

If anything, pass 3 makes this separation more important:

- `execution/signals.py` answers: “should this specialist trade now?”
- `risk/manager.py` answers: “even if yes, is the account allowed to take it?”

This module remains the final account-safety gate before order submission.

## How It’s Used

### `execution/engine.execute_trade(...)`

- builds an `AccountState`
- builds a `TradeRequest`
- calls `validate_trade(...)`
- only submits the MT5 order if the result is allowed

### `scheduler/main.py`

- indirectly relies on `RiskConfig` values when setting effective live
  risk-per-trade caps for signal execution

### `execution/live_monitor.py`

- uses the configured portfolio DD threshold as the basis for the circuit breaker

## Design Notes

### Peak-equity dependency

Drawdown checks depend on caller-supplied `equity_peak`.
If `equity_peak <= 0`, drawdown checks are skipped as a defensive fallback.

### Intentional narrowness

This module should remain boring and deterministic.
It should not absorb strategy logic, regime logic, or execution heuristics.
That keeps hard risk rules auditable.

## Gotchas / Notes

- Daily limits are separate from these checks, so a trade can pass this module
  and still be blocked upstream by day-level limits.
- Changes to `RiskConfig` can materially affect both live behavior and how
  execution is bounded in practice; treat config changes carefully.
- This module is about account protection, not alpha generation.

## Changelog (Docs)

- 2026-03-21: Documented `RiskConfig` usage, daily guardrail relationships,
  and circuit-breaker context.
- 2026-03-27: Refreshed for pass 3 to clarify this module’s narrow role as the
  final hard account-level gate beneath the smarter live-routing stack.