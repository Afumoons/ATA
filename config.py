from __future__ import annotations

from dataclasses import dataclass


@dataclass
class RiskConfig:
    # Per-trade risk cap: percentage of current equity risked per trade
    max_risk_per_trade_pct: float = 1.5       # 1.5% of equity (AGGRESSIVE++ profile)

    # Portfolio-level circuit breaker.
    # 30% is currently intentional for this deployment; do not "fix" it back to
    # 25% unless the desired risk posture is explicitly changed by a human.
    max_portfolio_drawdown_pct: float = 30.0

    # Maximum simultaneous open positions across all strategies
    max_open_positions: int = 100

    # Daily guardrails — enabled by default for live prop-firm style accounts.
    max_daily_drawdown_pct: float = 30.0       # lock trading if daily DD > 5%
    max_trades_per_day: int = 288               # lock trading after N trades/day
    daily_limits_enabled: bool = False


@dataclass
class DataConfig:
    mt5_timeframe_default: str = "M15"
    history_bars_default: int = 4000


@dataclass
class SchedulerConfig:
    enable_scheduler: bool = True


@dataclass
class RoutingConfig:
    """Controls pass-3 live routing gates.

    These settings decide whether a strategy is allowed to trade in the
    *current* market/session context after it already passed broader pool
    selection.

    Mental model:
    - session filters answer: "is this the right trading session for this strategy?"
    - regime filters answer: "is this the right market regime for this strategy?"
    - confidence filters answer: "how sure are we about the detected regime?"
    - edge thresholds answer: "is this strategy's historical edge strong enough here?"
    """

    # Session gates
    # If True: only allow entry when the current session equals the strategy's
    # recorded `best_session` in strategy_explain.meta. This is the strictest
    # session filter. Set False to allow a strategy to trade outside its single
    # best session, as long as no other session policy blocks it.
    require_best_session_for_entry: bool = False

    # If True: and the strategy declares `allowed_sessions=[...]`, the current
    # session must be inside that allowlist. If False: ignore allowlist-based
    # session restrictions entirely.
    enforce_allowed_sessions: bool = False

    # If True: and the strategy declares `blocked_sessions=[...]`, the current
    # session must NOT be inside that blocklist. If False: ignore blocklist-
    # based session restrictions entirely.
    enforce_blocked_sessions: bool = True

    # Regime policy gates
    # If True: and the strategy declares `allowed_regimes=[...]`, at least one
    # current candidate regime label must be inside that allowlist.
    enforce_allowed_regimes: bool = False

    # If True: and the strategy declares `blocked_regimes=[...]`, none of the
    # current candidate regime labels may be inside that blocklist.
    enforce_blocked_regimes: bool = True

    # Structured routing confidence gates
    # Higher values = stricter routing. `active` should usually remain stricter
    # than `exploratory` because active capital is the main deployment tier.
    min_regime_confidence_active: float = 0.0
    min_regime_confidence_exploratory: float = 0.0

    # Volatility mismatch gate
    # If True: block strategies whose metadata suggests they are a bad fit for
    # the current volatility regime (for example a low-vol/ranging specialist in
    # an event-driven high-vol environment). If False: skip this guard.
    enforce_volatility_mismatch_gate: bool = False

    # Regime edge ranking thresholds
    # Higher values = stricter selection after eligibility gates.
    # A strategy must beat the threshold to survive the edge filter.
    active_regime_edge_threshold: float = 0.5
    exploratory_regime_edge_threshold: float = 0.2

    # If exploratory candidates all fail the edge threshold, keep the single
    # best exploratory candidate anyway. This preserves controlled exploration
    # instead of going fully empty.
    keep_best_exploratory_on_empty_edge_filter: bool = True


# Module-level singletons — import and reference these directly in other modules
risk_config = RiskConfig()
data_config = DataConfig()
scheduler_config = SchedulerConfig()
routing_config = RoutingConfig()

# Symbol alias — all keys normalize to the canonical research symbol.
# Execution layer should still use the actual broker symbol known by MT5.
SYMBOL_ALIASES: dict[str, str] = {
    "XAUUSD": "XAUUSDm",
    "XAUUSDc": "XAUUSDm",
    "XAUUSDm": "XAUUSDm",
    "BTCUSDT": "BTCUSDm",
    "BTCUSD": "BTCUSDm",
    "BTCUSDm": "BTCUSDm",
}

# Reverse map: canonical symbol → broker variants valid for execution.
SYMBOL_EXECUTION_VARIANTS: dict[str, list[str]] = {
    "XAUUSDm": ["XAUUSDm", "XAUUSD", "XAUUSDc"],
    "BTCUSDm": ["BTCUSDm", "BTCUSD", "BTCUSDc", "BTCUSDT"],
}


def canonical_symbol(symbol: str) -> str:
    """Normalize a broker/execution symbol to the canonical research symbol."""
    return SYMBOL_ALIASES.get(symbol, symbol)
