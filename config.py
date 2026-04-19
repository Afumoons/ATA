from __future__ import annotations

"""Centralized runtime configuration for Autonomous Trading AI.

This module groups the main operational knobs by domain so strategy research,
scheduler governance, live execution, decay monitoring, and notifications all
pull from one place.

Guidelines:
- Treat these values as deployment-level defaults.
- Prefer adding human-facing behavior knobs here over scattering literals.
- Keep purely local helper constants close to the code that uses them.
"""

from dataclasses import dataclass, field


@dataclass
class RiskConfig:
    """Portfolio and per-trade risk guardrails.

    These values should reflect the intended account risk posture, not just
    what happens to work in backtests.
    """
    # Per-trade risk cap: percentage of current equity risked per trade
    max_risk_per_trade_pct: float = 2       # 1.5% of equity (AGGRESSIVE++ profile)

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
    """Defaults for MT5 data collection and feature-generation inputs."""

    mt5_timeframe_default: str = "M15"
    history_bars_default: int = 4000


@dataclass
class SchedulerConfig:
    """Research, promotion, and scheduling parameters.

    This is the largest config surface because it controls both recurring job
    cadence and most strategy-selection thresholds used by the engine.
    """
    enable_scheduler: bool = True
    managed_symbols: list[str] = field(default_factory=lambda: ["XAUUSDm", "BTCUSDm", "XAGUSDm"])
    timeframe: str = "M15"
    minimum_edge_for_execution: float = 0.0

    exec_min_wf_sharpe: float = 0.75
    exec_max_dd_pct: float = 12.0
    exec_min_trades: int = 160
    exec_max_consec_loss: int = 15
    max_execution_pool: int = 10
    max_execution_per_best_regime: int = 5
    max_execution_per_family: int = 4

    family_aware_governance_enabled: bool = True
    challenger_families: set[str] = field(default_factory=lambda: {
        "ma_trend",
        "compression_breakout",
        "pullback_trend",
        "session_breakout",
        "vol_breakout",
        "rsi_range",
        "ichifib",
        "mixed:ma_trend+rsi_range",
        "mixed:rsi_range+ma_trend",
    })
    challenger_exploratory_min_slots: int = 2
    challenger_candidate_min_slots: int = 2

    specialist_exec_min_trades: int = 120
    exploratory_specialist_min_trades: int = 100
    btc_exec_min_trades: int = 100
    btc_specialist_exec_min_trades: int = 80
    btc_exploratory_specialist_min_trades: int = 70
    xag_exec_min_trades: int = 80
    xag_specialist_exec_min_trades: int = 60
    xag_exploratory_specialist_min_trades: int = 50
    xag_bootstrap_min_trades: int = 20
    xag_bootstrap_min_pf: float = 1.01
    xag_bootstrap_min_sharpe: float = 0.05
    xag_bootstrap_min_wf_sharpe: float = 0.05

    research_family_summary_symbols: set[str] = field(default_factory=lambda: {"XAUUSDm", "BTCUSDm", "XAGUSDm"})
    research_family_stage_keys: tuple[str, ...] = (
        "generated",
        "cheap_prescreen_pass",
        "cheap_prescreen_fail",
        "backtest_pass",
        "backtest_fail",
        "wf_pass",
        "wf_fail",
        "mc_pass",
        "mc_fail",
        "accepted",
        "candidate",
        "exploratory",
        "active",
    )

    regime_sort_norm: float = 20.0
    session_sort_norm: float = 10.0
    status_sort_bonus: dict[str, float] = field(default_factory=lambda: {
        "active": 1.15,
        "exploratory": 0.95,
        "candidate": 0.75,
        "disabled": 0.50,
    })

    default_backtest_kwargs: dict[str, float | int] = field(default_factory=lambda: {
        "spread": 0.35,
        "commission_per_lot": 7.0,
        "slippage_pips": 2.0,
        "max_positions_total": 1,
        "max_positions_per_strategy": 1,
    })
    cheap_prescreen_backtest_kwargs: dict[str, float | int] = field(default_factory=lambda: {
        "spread": 0.25,
        "commission_per_lot": 0.0,
        "slippage_pips": 0.0,
        "max_positions_total": 1,
        "max_positions_per_strategy": 1,
    })
    cheap_prescreen_min_trades: int = 20
    cheap_prescreen_min_pf: float = 0.95
    cheap_prescreen_min_sharpe: float = -0.10
    cheap_prescreen_max_dd_pct: float = 35.0

    xau_backtest_kwargs: dict[str, float] = field(default_factory=lambda: {
        "spread": 0.60,
        "commission_per_lot": 7.0,
        "slippage_pips": 4.0,
    })
    btc_backtest_kwargs: dict[str, float] = field(default_factory=lambda: {
        "spread": 8.0,
        "commission_per_lot": 0.0,
        "slippage_pips": 12.0,
    })

    update_data_interval_minutes: int = 5
    research_interval_minutes: int = 30
    execute_signals_interval_minutes: int = 5
    live_monitor_interval_minutes: int = 5
    update_news_hour_utc: int = 6
    update_news_minute_utc: int = 0
    news_alert_interval_minutes: int = 5


@dataclass
class ExecutionConfig:
    """Live order-execution defaults and broker-specific constraints."""
    default_pip_value_per_lot: dict[str, float] = field(default_factory=lambda: {
        "XAUUSDm": 1.0,
        "XAGUSDm": 0.5,
        "XAUUSD": 1.0,
        "XAUUSDc": 1.0,
        "XAGUSD": 0.5,
        "EURUSD": 10.0,
        "GBPUSD": 10.0,
        "USDJPY": 10.0,
        "AUDUSD": 10.0,
        "USDCAD": 10.0,
        "USDCHF": 10.0,
        "BTCUSDm": 1.0,
        "BTCUSDT": 1.0,
        "BTCUSD": 1.0,
        "BTCUSDc": 1.0,
        "ETHUSDm": 1.0,
    })
    metals_prefixes: set[str] = field(default_factory=lambda: {"XAU", "XAG"})
    trades_log_filename: str = "trades.log"
    order_deviation: int = 10
    order_magic: int = 987654
    order_comment_max_length: int = 31
    filling_retry_order: list[str] = field(default_factory=lambda: ["IOC", "FOK", "RETURN"])


@dataclass
class LiveDecayConfig:
    """Thresholds for degrading strategies based on recent live results."""
    min_trades_for_decay: int = 8
    min_recent_for_warning: int = 8
    min_recent_for_degrade: int = 10
    warning_loss_streak: int = 4
    degrade_loss_streak: int = 5
    max_recent_trades: int = 30


@dataclass
class NotificationConfig:
    """Notification routing and alert-timing defaults."""
    webhook_token: str = "clio-autotrading-hooks"
    recipient: str = "628170090022"
    min_impact_for_alert: int = 3
    alert_cooldown_minutes: int = 60
    alert_before_minutes: int = 30
    request_timeout: int = 10
    retry_attempts: int = 2
    trading_pause_before_minutes: int = 30
    trading_pause_after_minutes: int = 15


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


# Module-level singletons used across the codebase.
#
# Import these directly from `config` rather than instantiating dataclasses in
# downstream modules. That keeps runtime behavior consistent and makes future
# environment-override wiring much simpler.
risk_config = RiskConfig()
data_config = DataConfig()
scheduler_config = SchedulerConfig()
execution_config = ExecutionConfig()
live_decay_config = LiveDecayConfig()
notification_config = NotificationConfig()
routing_config = RoutingConfig()

# Symbol alias — all keys normalize to the canonical research symbol.
# Execution layer should still use the actual broker symbol known by MT5.
SYMBOL_ALIASES: dict[str, str] = {
    "XAUUSD": "XAUUSDm",
    "XAUUSDC": "XAUUSDm",
    "XAUUSDM": "XAUUSDm",
    "XAGUSD": "XAGUSDm",
    "XAGUSDC": "XAGUSDm",
    "XAGUSDM": "XAGUSDm",
    "BTCUSDT": "BTCUSDm",
    "BTCUSD": "BTCUSDm",
    "BTCUSDC": "BTCUSDm",
    "BTCUSDM": "BTCUSDm",
}

# Reverse map: canonical symbol → broker variants valid for execution.
SYMBOL_EXECUTION_VARIANTS: dict[str, list[str]] = {
    "XAUUSDm": ["XAUUSDm", "XAUUSD", "XAUUSDc"],
    "XAGUSDm": ["XAGUSDm", "XAGUSD", "XAGUSDc"],
    "BTCUSDm": ["BTCUSDm", "BTCUSD", "BTCUSDc", "BTCUSDT"],
}

def normalize_symbol_token(symbol: str | None) -> str:
    """Return a trimmed, upper-normalized symbol token.

    This keeps canonicalization resilient to minor input hygiene issues such as
    stray whitespace or lowercase symbols from configs, legacy artifacts, or
    broker payloads.
    """
    if symbol is None:
        return ""
    return str(symbol).strip().upper()


_SYMBOL_EXECUTION_VARIANTS_NORMALIZED: dict[str, list[str]] = {
    normalize_symbol_token(canon): list(variants)
    for canon, variants in SYMBOL_EXECUTION_VARIANTS.items()
}


def canonical_symbol(symbol: str | None) -> str:
    """Normalize a broker/execution symbol to the canonical research symbol."""
    normalized = normalize_symbol_token(symbol)
    return SYMBOL_ALIASES.get(normalized, normalized)


def is_canonical_symbol(symbol: str | None) -> bool:
    """Return True when the symbol is already one of the canonical research ids."""
    normalized = normalize_symbol_token(symbol)
    return bool(normalized) and normalized in _SYMBOL_EXECUTION_VARIANTS_NORMALIZED


def execution_variants_for(symbol: str | None) -> list[str]:
    """Return broker/execution symbol variants for a canonical market symbol.

    Unknown symbols fall back to their normalized token as a single-item list so
    callers can stay permissive where fail-fast behavior is not desired.
    """
    canon = canonical_symbol(symbol)
    variants = _SYMBOL_EXECUTION_VARIANTS_NORMALIZED.get(normalize_symbol_token(canon))
    if variants:
        return list(variants)
    return [canon] if canon else []


def same_canonical_symbol(left: str | None, right: str | None) -> bool:
    """Return True when two symbol identifiers point at the same canonical market."""
    left_canon = canonical_symbol(left)
    right_canon = canonical_symbol(right)
    return bool(left_canon) and left_canon == right_canon
