from __future__ import annotations

from dataclasses import dataclass


@dataclass
class RiskConfig:
    # Per-trade risk cap: percentage of current equity risked per trade
    max_risk_per_trade_pct: float = 1.0       # 1.0% of equity (AGGRESSIVE profile)
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
    daily_limits_enabled: bool = True         # was False — guard now active by default


@dataclass
class DataConfig:
    mt5_timeframe_default: str = "M15"
    history_bars_default: int = 2000


@dataclass
class SchedulerConfig:
    enable_scheduler: bool = True


# Module-level singletons — import and reference these directly in other modules
risk_config = RiskConfig()
data_config = DataConfig()
scheduler_config = SchedulerConfig()