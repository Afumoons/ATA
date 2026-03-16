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
    max_risk_per_trade_pct: float = 0.5  # 0.5% of equity
    max_portfolio_drawdown_pct: float = 20.0
    max_open_positions: int = 10
    # Optional daily guardrails (can be disabled via the *_enabled flags)
    max_daily_drawdown_pct: float = 3.0
    max_trades_per_day: int = 5
    daily_limits_enabled: bool = False

risk_config = RiskConfig()
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

- `scheduler/main.py`:
  - Uses `risk_config.max_risk_per_trade_pct` when computing
    `risk_perc = min(0.5, risk_config.max_risk_per_trade_pct)` for live signals.

## Gotchas / Notes

- `equity_peak` is provided by the caller (e.g. from live monitor state). If it
  is `<= 0`, drawdown checks are skipped (`reason="no_peak"`).
- Changes to `RiskConfig` affect both backtest behavior (indirectly, via
  sizing/limits in execution) and live trading. Adjust carefully and keep
  `config.py` under version control.
- Daily risk limits (DD / trade count caps) are enforced **separately** from
  these checks, so both layers can block trades independently.
