# risk/ – Central Risk Management

## Purpose

This module centralizes **risk rules for live trading**. It is called from
`execution/engine.py` (before any MT5 order is sent) and from the scheduler via
`risk_config`.

It does **not** compute exact SL/TP or pip sizing; it only decides whether a
proposed trade is allowed, based on:

- max risk per trade (percentage of equity),
- max number of open positions,
- max portfolio drawdown from `equity_peak`.

Daily loss / trade caps are implemented separately in
`execution/live_state_utils.py` and wired via `execute_signals_for_symbol(...)`.

## Key Files

- `manager.py`
  - Defines core dataclasses:
    - `AccountState` – snapshot of account risk state (equity, balance, open positions).
    - `TradeRequest` – proposed trade (strategy, symbol, direction, volume, requested risk%).
    - `RiskDecision` – result (allowed / reason).
  - Core checks:
    - `check_max_risk_per_trade(account, req)` – ensure `req.risk_perc` does not
      exceed `risk_config.max_risk_per_trade_pct`.
    - `check_max_open_positions(account)` – enforce `risk_config.max_open_positions`.
    - `check_drawdown(equity_peak, account)` – compare current equity vs
      `equity_peak`, blocking trades if drawdown exceeds
      `risk_config.max_portfolio_drawdown_pct`.
  - `validate_trade(account, req, equity_peak)`:
    - Runs all checks in order.
    - Logs a warning and returns the first failing `RiskDecision`.
    - On success, logs an "accept" with basic trade details.

## Configuration

Risk thresholds are defined in `config.py` via `RiskConfig`:

```python
@dataclass
class RiskConfig:
    # Per-trade risk cap: percentage of current equity risked per trade
    max_risk_per_trade_pct: float = 1.0       # 1.0% of equity (AGGRESSIVE++ profile)

    # Portfolio-level circuit breaker: disable all active strategies if
    # drawdown from peak exceeds this threshold
    max_portfolio_drawdown_pct: float = 20.0  # 20%

    # Maximum simultaneous open positions across all strategies
    max_open_positions: int = 10

    # Daily guardrails — enabled by default for live prop-firm style accounts.
    # Set daily_limits_enabled = False to disable entirely (e.g. for backtesting
    # or paper trading where daily limits are not meaningful).
    max_daily_drawdown_pct: float = 3.0       # lock trading if daily DD > 3%
    max_trades_per_day: int = 5               # lock trading after N trades/day
    daily_limits_enabled: bool = True         # guard active by default
```

Fields used by `risk/manager.py`:

- `max_risk_per_trade_pct` → bound for `TradeRequest.risk_perc`.
- `max_portfolio_drawdown_pct` → account-level DD cutoff vs `equity_peak`.
- `max_open_positions` → limit on concurrent open trades.

Fields used by **daily guardrails** (in `execution/live_state_utils.py`):

- `max_daily_drawdown_pct`
- `max_trades_per_day`
- `daily_limits_enabled`

## How It’s Used

- `execution/engine.execute_trade(...)`:
  - Builds an `AccountState` from MT5 account info and current open positions.
  - Builds a `TradeRequest` from strategy parameters (symbol, direction, volume,
    requested `risk_perc`).
  - Calls `validate_trade(account, req, equity_peak)`.
  - Only if `allowed=True` does it send the MT5 order.

- `execution/signals.execute_signals_for_symbol(...)`:
  - Uses `risk_config.max_daily_drawdown_pct`, `risk_config.max_trades_per_day`,
    and `risk_config.daily_limits_enabled` via `can_open_new_trade(...)` to
    enforce **daily DD / trade-count caps** before any new trade is opened.

- `scheduler/main.py`:
  - Uses `risk_config.max_risk_per_trade_pct` when computing
    `risk_perc = min(1.0, risk_config.max_risk_per_trade_pct)` for live signals.

- `execution/live_monitor.update_live_stats(...)`:
  - Uses `risk_config.max_portfolio_drawdown_pct` as the **circuit breaker
    threshold**: when drawdown from `peak_equity` exceeds this level, all
    `active` strategies in the pool are automatically disabled.

## Gotchas / Notes

- `equity_peak` is provided by the caller (e.g. from live monitor state). If it
  is `<= 0`, drawdown checks are skipped (`reason="no_peak"`).
- Changes to `RiskConfig` affect both backtest behaviour (indirectly, via
  sizing/limits in execution) and live trading. Adjust carefully and keep
  `config.py` under version control.
- Daily risk limits (DD / trade-count caps) are enforced **separately** from
  these checks, so both layers can block trades independently.

## Changelog (Docs)

- 2026-03-21: Updated for new `RiskConfig` defaults (1% per trade, 20% portfolio DD,
  daily guardrails enabled by default) and clarified circuit-breaker usage.
