from __future__ import annotations

from dataclasses import dataclass
from typing import List, Tuple, Any, Dict

import pandas as pd

from ..logging_utils import get_logger
from ..strategies.base import StrategyDefinition
from ..strategies.pool import StrategyPool
from ..execution.engine import execute_trade
from autonomous_trading_ai.execution.live_state_utils import can_open_new_trade
logger = get_logger(__name__)


@dataclass
class Signal:
    strategy: StrategyDefinition
    direction: str  # "long" or "short"


def generate_signals_for_row(
    row: pd.Series,
    strategies: List[StrategyDefinition],
) -> List[Signal]:
    """Generate simple entry signals for a single feature row.

    This does not handle exits; exits are handled by SL/TP and strategy exit rules
    inside the backtest/monitoring logic.
    """
    from ..backtests.engine import _eval_rule  # reuse rule evaluator

    signals: List[Signal] = []
    for strat in strategies:
        if _eval_rule(row, strat.long_entry_rule):
            signals.append(Signal(strategy=strat, direction="long"))
        if _eval_rule(row, strat.short_entry_rule):
            signals.append(Signal(strategy=strat, direction="short"))
    return signals


def _regime_edge(stats: Dict[str, Any], regime_label: str) -> float:
    """Return a regime-specific edge score for a strategy.

    Uses `strategy_explain.regime_pnl[regime_label].return_pct` when
    available. If the information is missing, falls back to a large
    negative value so the strategy is deprioritized when filtering by
    that regime.
    """
    if not stats:
        return -999.0

    ex = stats.get("strategy_explain", {}) or {}
    rp = ex.get("regime_pnl", {}) or {}
    regime_stats = rp.get(regime_label, {}) or {}
    try:
        return float(regime_stats.get("return_pct", -999.0) or -999.0)
    except Exception:
        return -999.0


def _map_current_to_regime_pnl_label(current_regime: str) -> str:
    """Map the legacy `regime` label to a key in `regime_pnl`.

    This keeps the mapping explicit and easy to adjust.
    """
    if current_regime in {"trending_up", "trending_down", "ranging"}:
        return current_regime

    # High volatility but not clearly trending: treat as high_vol / fallback
    if current_regime in {"high_vol", "low_vol"}:
        # For now, use "ranging" as a conservative default
        return "ranging"

    return "unknown"


def execute_signals_for_symbol(
    symbol: str,
    timeframe: str,
    features_df: pd.DataFrame,
    pool: StrategyPool,
    risk_perc: float,
) -> List[Tuple[Signal, str]]:
    """Generate and execute signals for the latest row of a symbol.

    Returns list of (Signal, result_reason).
    """
    if features_df.empty:
        return []

    latest = features_df.sort_values("time").iloc[-1]

    # Legacy regime label (e.g. "trending_up", "trending_down", "ranging", "high_vol", "low_vol")
    current_regime = str(latest.get("regime", "unknown"))
    logger.info("Current regime for %s %s: %s", symbol, timeframe, current_regime)

    # Daily limits: optionally block new trades after daily DD / trade cap
    from autonomous_trading_ai.config import risk_config
    from autonomous_trading_ai.execution.live_monitor import _get_account_equity

    if not can_open_new_trade(
        current_equity=_get_account_equity(),
        max_dd_pct=risk_config.max_daily_drawdown_pct,
        max_trades=risk_config.max_trades_per_day,
        enabled=risk_config.daily_limits_enabled,
    ):
        logger.info("Daily limits prevent opening new trades for %s %s", symbol, timeframe)
        return []

    # Strategies for this symbol/timeframe
    active_records = [
        rec
        for rec in pool.strategies.values()
        if rec.status == "active" and rec.symbol == symbol and rec.timeframe == timeframe
    ]

    exploratory_records = [
        rec
        for rec in pool.strategies.values()
        if rec.status == "exploratory" and rec.symbol == symbol and rec.timeframe == timeframe
    ]

    if not active_records and not exploratory_records:
        return []

    regime_label = _map_current_to_regime_pnl_label(current_regime)

    def _filter_and_rank(records):
        if not records or regime_label == "unknown":
            return records

        scored: List[Tuple[float, Any]] = []
        for rec in records:
            edge = _regime_edge(rec.stats or {}, regime_label)
            scored.append((edge, rec))

        # Filter out strategies with very poor historical performance
        # in this regime (e.g. worse than -5% return).
        kept = [(edge, rec) for edge, rec in scored if edge > -5.0]

        # Sort by edge descending (best first)
        kept.sort(key=lambda er: er[0], reverse=True)

        filtered = [rec for edge, rec in kept]
        if filtered != records:
            logger.info(
                "Regime filter for %s %s (%s): %d -> %d strategies",
                symbol,
                timeframe,
                regime_label,
                len(records),
                len(filtered),
            )
        return filtered

    active_records = _filter_and_rank(active_records)
    exploratory_records = _filter_and_rank(exploratory_records)

    # Optionally cap the number of strategies considered per tier
    MAX_ACTIVE_PER_SYMBOL = 5
    MAX_EXPLORATORY_PER_SYMBOL = 3

    if len(active_records) > MAX_ACTIVE_PER_SYMBOL:
        active_records = active_records[:MAX_ACTIVE_PER_SYMBOL]

    if len(exploratory_records) > MAX_EXPLORATORY_PER_SYMBOL:
        exploratory_records = exploratory_records[:MAX_EXPLORATORY_PER_SYMBOL]

    if not active_records and not exploratory_records:
        logger.info(
            "No strategies with acceptable regime edge for %s %s in regime=%s",
            symbol,
            timeframe,
            current_regime,
        )
        return []

    # Need StrategyDefinition instances; for now we reconstruct using minimal fields
    from ..strategies.generator import load_strategy
    from pathlib import Path

    active_strategies: List[StrategyDefinition] = []
    exploratory_strategies: List[StrategyDefinition] = []

    base_dir = Path(__file__).resolve().parents[1] / "strategies" / "generated"

    # Load active strategies
    for rec in active_records:
        path = base_dir / f"{rec.name}.json"
        try:
            active_strategies.append(load_strategy(path))
        except Exception as e:
            logger.exception("Failed to load active strategy %s from %s: %s", rec.name, path, e)

    # Load exploratory strategies
    for rec in exploratory_records:
        path = base_dir / f"{rec.name}.json"
        try:
            exploratory_strategies.append(load_strategy(path))
        except Exception as e:
            logger.exception("Failed to load exploratory strategy %s from %s: %s", rec.name, path, e)

    results: List[Tuple[Signal, str]] = []

    # Risk tiers
    risk_perc_active = risk_perc
    # Exploratory strategies trade at significantly reduced risk
    risk_perc_exploratory = min(risk_perc * 0.25, 0.1)

    # Generate and execute signals for active strategies
    if active_strategies:
        active_signals = generate_signals_for_row(latest, active_strategies)
        for sig in active_signals:
            strat = sig.strategy
            try:
                res = execute_trade(
                    strategy_name=strat.name,
                    symbol=symbol,
                    direction=sig.direction,
                    risk_perc=risk_perc_active,
                    stop_loss_pips=strat.stop_loss_pips,
                    take_profit_pips=strat.take_profit_pips,
                    pip_size=0.01 if "XAU" in symbol or "XAG" in symbol else 0.0001,
                )
                results.append((sig, res.reason))
                if res.success:
                    logger.info(
                        "Signal executed (active): strategy=%s symbol=%s dir=%s",
                        strat.name,
                        symbol,
                        sig.direction,
                    )
                else:
                    logger.warning(
                        "Signal not executed (active): strategy=%s symbol=%s dir=%s reason=%s",
                        strat.name,
                        symbol,
                        sig.direction,
                        res.reason,
                    )
            except Exception as e:
                logger.exception("Error executing active signal for %s: %s", strat.name, e)
                results.append((sig, f"error: {e}"))

    # Generate and execute signals for exploratory strategies (reduced risk)
    if exploratory_strategies:
        exploratory_signals = generate_signals_for_row(latest, exploratory_strategies)
        for sig in exploratory_signals:
            strat = sig.strategy
            try:
                res = execute_trade(
                    strategy_name=strat.name,
                    symbol=symbol,
                    direction=sig.direction,
                    risk_perc=risk_perc_exploratory,
                    stop_loss_pips=strat.stop_loss_pips,
                    take_profit_pips=strat.take_profit_pips,
                    pip_size=0.01 if "XAU" in symbol or "XAG" in symbol else 0.0001,
                )
                results.append((sig, res.reason))
                if res.success:
                    logger.info(
                        "Signal executed (exploratory): strategy=%s symbol=%s dir=%s",
                        strat.name,
                        symbol,
                        sig.direction,
                    )
                else:
                    logger.warning(
                        "Signal not executed (exploratory): strategy=%s symbol=%s dir=%s reason=%s",
                        strat.name,
                        symbol,
                        sig.direction,
                        res.reason,
                    )
            except Exception as e:
                logger.exception("Error executing exploratory signal for %s: %s", strat.name, e)
                results.append((sig, f"error: {e}"))

    return results
