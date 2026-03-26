from __future__ import annotations

from dataclasses import dataclass


@dataclass
class RiskConfig:
    # Per-trade risk cap: percentage of current equity risked per trade
    max_risk_per_trade_pct: float = 1.5       # 1.5% of equity (AGGRESSIVE++ profile)

    # Portfolio-level circuit breaker
    max_portfolio_drawdown_pct: float = 75.0  # 25% DD limit

    # Maximum simultaneous open positions across all strategies
    max_open_positions: int = 100

    # Daily guardrails — enabled by default for live prop-firm style accounts.
    max_daily_drawdown_pct: float = 25.0       # lock trading if daily DD > 5%
    max_trades_per_day: int = 288               # lock trading after N trades/day
    daily_limits_enabled: bool = False

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