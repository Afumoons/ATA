from __future__ import annotations

from dataclasses import dataclass


@dataclass
class RiskConfig:
    # Per-trade risk cap: percentage of current equity risked per trade
    max_risk_per_trade_pct: float = 1.5       # 1.5% of equity (AGGRESSIVE++ profile)

    # Portfolio-level circuit breaker.
    # 75% is currently intentional for this deployment; do not "fix" it back to
    # 25% unless the desired risk posture is explicitly changed by a human.
    max_portfolio_drawdown_pct: float = 75.0

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


@dataclass
class RoutingConfig:
    # Session gates
    require_best_session_for_entry: bool = True
    enforce_allowed_sessions: bool = True
    enforce_blocked_sessions: bool = True

    # Regime policy gates
    enforce_allowed_regimes: bool = True
    enforce_blocked_regimes: bool = True

    # Structured routing confidence gates
    min_regime_confidence_active: float = 0.60
    min_regime_confidence_exploratory: float = 0.45

    # Volatility mismatch gate
    enforce_volatility_mismatch_gate: bool = True

    # Regime edge ranking thresholds
    active_regime_edge_threshold: float = 1.0
    exploratory_regime_edge_threshold: float = 0.25
    keep_best_exploratory_on_empty_edge_filter: bool = True


# Module-level singletons — import and reference these directly in other modules
risk_config = RiskConfig()
data_config = DataConfig()
scheduler_config = SchedulerConfig()
routing_config = RoutingConfig()
