from __future__ import annotations

from dataclasses import dataclass
from typing import List, Tuple, Any, Dict

import pandas as pd

from ..logging_utils import get_logger
from ..strategies.base import StrategyDefinition
from ..strategies.pool import StrategyPool
from ..execution.engine import execute_trade
from ..execution.live_state_utils import can_open_new_trade

logger = get_logger(__name__)

# Minimum regime edge (return_pct in that regime) for a strategy to be
# allowed to fire signals. Strategies below this threshold are skipped.
# Active tier: 0.0 means "only trade if this regime was historically profitable"
# Exploratory tier: looser, to allow data gathering
ACTIVE_REGIME_EDGE_THRESHOLD = 0.0      # was -5.0 — too loose
EXPLORATORY_REGIME_EDGE_THRESHOLD = -10.0


@dataclass
class Signal:
    strategy: StrategyDefinition
    direction: str  # "long" or "short"


def generate_signals_for_row(
    row: pd.Series,
    strategies: List[StrategyDefinition],
) -> List[Signal]:
    """Generate simple entry signals for a single feature row.

    This does not handle exits; exits are handled by SL/TP and strategy
    exit rules inside the backtest/monitoring logic.
    """
    from ..backtests.engine import _eval_rule  # reuse rule evaluator

    signals: List[Signal] = []
    for strat in strategies:
        long_hit = _eval_rule(row, strat.long_entry_rule)
        short_hit = _eval_rule(row, strat.short_entry_rule)

        logger.debug(
            "Entry eval: strategy=%s long_rule='%s' -> %s | short_rule='%s' -> %s",
            strat.name,
            strat.long_entry_rule,
            long_hit,
            strat.short_entry_rule,
            short_hit,
        )

        if long_hit:
            signals.append(Signal(strategy=strat, direction="long"))
        if short_hit:
            signals.append(Signal(strategy=strat, direction="short"))

    return signals


def _regime_edge(stats: Dict[str, Any], regime_label: str) -> float:
    """Return a regime-specific edge score for a strategy.

    Uses `strategy_explain.regime_pnl[regime_label].return_pct` when
    available. Falls back to a large negative value so the strategy is
    deprioritized when filtering by that regime.
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
    """Map the legacy `regime` label to a key in `regime_pnl`."""
    if current_regime in {"trending_up", "trending_down", "ranging"}:
        return current_regime
    if current_regime in {"high_vol", "low_vol"}:
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
        logger.warning("execute_signals_for_symbol: empty features_df for %s %s", symbol, timeframe)
        return []

    latest = features_df.sort_values("time").iloc[-1]

    current_regime = str(latest.get("regime", "unknown"))
    logger.info("Current regime for %s %s: %s", symbol, timeframe, current_regime)

    # ------------------------------------------------------------------ #
    # Daily limits guard                                                   #
    # ------------------------------------------------------------------ #
    from ..config import risk_config
    from ..execution.live_monitor import _get_account_equity

    current_equity = _get_account_equity()
    logger.debug(
        "Daily limits check: symbol=%s equity=%.2f max_dd_pct=%.2f "
        "max_trades=%d enabled=%s",
        symbol,
        current_equity,
        risk_config.max_daily_drawdown_pct,
        risk_config.max_trades_per_day,
        risk_config.daily_limits_enabled,
    )

    if not can_open_new_trade(
        current_equity=current_equity,
        max_dd_pct=risk_config.max_daily_drawdown_pct,
        max_trades=risk_config.max_trades_per_day,
        enabled=risk_config.daily_limits_enabled,
    ):
        logger.info(
            "Daily limits prevent opening new trades for %s %s "
            "(equity=%.2f, daily_limits_enabled=%s)",
            symbol,
            timeframe,
            current_equity,
            risk_config.daily_limits_enabled,
        )
        return []

    # ------------------------------------------------------------------ #
    # Collect active + exploratory pool records                           #
    # ------------------------------------------------------------------ #
    active_records = [
        rec
        for rec in pool.strategies.values()
        if rec.status == "active"
        and rec.symbol == symbol
        and rec.timeframe == timeframe
    ]

    exploratory_records = [
        rec
        for rec in pool.strategies.values()
        if rec.status == "exploratory"
        and rec.symbol == symbol
        and rec.timeframe == timeframe
    ]

    if not active_records and not exploratory_records:
        logger.info(
            "No active or exploratory strategies in pool for %s %s",
            symbol,
            timeframe,
        )
        return []

    regime_label = _map_current_to_regime_pnl_label(current_regime)

    # ------------------------------------------------------------------ #
    # Regime-based filter + rank                                          #
    # ------------------------------------------------------------------ #
    def _filter_and_rank(records, tier: str) -> List[Any]:
        if not records:
            return []

        if regime_label == "unknown":
            logger.warning(
                "Unknown regime for %s %s — skipping regime filter, "
                "passing all %d %s strategies",
                symbol,
                timeframe,
                len(records),
                tier,
            )
            return records

        threshold = (
            ACTIVE_REGIME_EDGE_THRESHOLD
            if tier == "active"
            else EXPLORATORY_REGIME_EDGE_THRESHOLD
        )

        scored: List[Tuple[float, Any]] = []
        for rec in records:
            edge = _regime_edge(rec.stats or {}, regime_label)
            scored.append((edge, rec))
            logger.info(
                "Regime edge: symbol=%s timeframe=%s regime=%s "
                "strategy=%s tier=%s edge=%.3f threshold=%.1f",
                symbol,
                timeframe,
                regime_label,
                rec.name,
                tier,
                edge,
                threshold,
            )

        kept = [(edge, rec) for edge, rec in scored if edge > threshold]
        kept.sort(key=lambda er: er[0], reverse=True)
        filtered = [rec for _, rec in kept]

        if len(filtered) != len(records):
            blocked_names = [
                rec.name for edge, rec in scored if edge <= threshold
            ]
            logger.info(
                "Regime filter for %s %s (%s) [tier=%s]: "
                "%d -> %d strategies passed (threshold=%.1f) | "
                "blocked: %s",
                symbol,
                timeframe,
                regime_label,
                tier,
                len(records),
                len(filtered),
                threshold,
                blocked_names,
            )

        # Exploratory fallback: keep best even below threshold so system
        # doesn't go fully silent while gathering data
        if not filtered and scored and tier == "exploratory":
            scored.sort(key=lambda er: er[0], reverse=True)
            best_edge, best_rec = scored[0]
            filtered = [best_rec]
            logger.info(
                "Regime fallback for %s %s (%s): no exploratory strategy "
                "passed edge>%.1f; keeping best with edge=%.2f",
                symbol,
                timeframe,
                regime_label,
                threshold,
                best_edge,
            )

        if not filtered:
            logger.info(
                "All %s strategies blocked by regime filter for %s %s "
                "(regime=%s, threshold=%.1f) — no signals will be generated",
                tier,
                symbol,
                timeframe,
                regime_label,
                threshold,
            )

        return filtered

    active_records = _filter_and_rank(active_records, tier="active")
    exploratory_records = _filter_and_rank(exploratory_records, tier="exploratory")

    # ------------------------------------------------------------------ #
    # Cap per tier                                                         #
    # ------------------------------------------------------------------ #
    MAX_ACTIVE_PER_SYMBOL = 5
    MAX_EXPLORATORY_PER_SYMBOL = 3
    active_records = active_records[:MAX_ACTIVE_PER_SYMBOL]
    exploratory_records = exploratory_records[:MAX_EXPLORATORY_PER_SYMBOL]

    if not active_records and not exploratory_records:
        logger.info(
            "No strategies with acceptable regime edge for %s %s "
            "(regime=%s) — skipping signal generation",
            symbol,
            timeframe,
            current_regime,
        )
        return []

    # ------------------------------------------------------------------ #
    # Load StrategyDefinition objects from disk                           #
    # ------------------------------------------------------------------ #
    from ..strategies.generator import load_strategy
    from pathlib import Path

    base_dir = Path(__file__).resolve().parents[1] / "strategies" / "generated"

    active_strategies: List[StrategyDefinition] = []
    for rec in active_records:
        path = base_dir / f"{rec.name}.json"
        try:
            active_strategies.append(load_strategy(path))
        except Exception as e:
            logger.exception(
                "Failed to load active strategy %s from %s: %s", rec.name, path, e
            )

    exploratory_strategies: List[StrategyDefinition] = []
    for rec in exploratory_records:
        path = base_dir / f"{rec.name}.json"
        try:
            exploratory_strategies.append(load_strategy(path))
        except Exception as e:
            logger.exception(
                "Failed to load exploratory strategy %s from %s: %s",
                rec.name,
                path,
                e,
            )

    # ------------------------------------------------------------------ #
    # Log key feature values to aid diagnosis                             #
    # ------------------------------------------------------------------ #
    logger.info(
        "Feature snapshot for %s %s: time=%s regime=%s "
        "ma_short=%.5f ma_long=%.5f trend_strength=%.4f rsi=%.2f",
        symbol,
        timeframe,
        latest.get("time", "?"),
        current_regime,
        float(latest.get("ma_short", float("nan"))),
        float(latest.get("ma_long", float("nan"))),
        float(latest.get("trend_strength", float("nan"))),
        float(latest.get("rsi", float("nan"))),
    )

    results: List[Tuple[Signal, str]] = []

    risk_perc_active = risk_perc
    risk_perc_exploratory = min(risk_perc * 0.25, 0.1)

    # ------------------------------------------------------------------ #
    # Active strategies                                                   #
    # ------------------------------------------------------------------ #
    if active_strategies:
        active_signals = generate_signals_for_row(latest, active_strategies)

        if not active_signals:
            logger.info(
                "No entry conditions met for active strategies on %s %s "
                "(regime=%s, %d strategies evaluated)",
                symbol,
                timeframe,
                current_regime,
                len(active_strategies),
            )
        else:
            logger.info(
                "%d signal(s) generated from active strategies for %s %s",
                len(active_signals),
                symbol,
                timeframe,
            )

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
                    pip_value_per_lot=1.0 if "XAU" in symbol or "XAG" in symbol else 10.0,
                )
                results.append((sig, res.reason))
                if res.success:
                    logger.info(
                        "Trade placed (active): strategy=%s symbol=%s dir=%s",
                        strat.name,
                        symbol,
                        sig.direction,
                    )
                else:
                    logger.warning(
                        "Trade rejected (active): strategy=%s symbol=%s "
                        "dir=%s reason=%s",
                        strat.name,
                        symbol,
                        sig.direction,
                        res.reason,
                    )
            except Exception as e:
                logger.exception(
                    "Error executing active signal for %s: %s", strat.name, e
                )
                results.append((sig, f"error: {e}"))

    # ------------------------------------------------------------------ #
    # Exploratory strategies                                              #
    # ------------------------------------------------------------------ #
    if exploratory_strategies:
        exploratory_signals = generate_signals_for_row(latest, exploratory_strategies)

        if not exploratory_signals:
            logger.info(
                "No entry conditions met for exploratory strategies on %s %s "
                "(regime=%s, %d strategies evaluated)",
                symbol,
                timeframe,
                current_regime,
                len(exploratory_strategies),
            )
        else:
            logger.info(
                "%d signal(s) generated from exploratory strategies for %s %s",
                len(exploratory_signals),
                symbol,
                timeframe,
            )

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
                        "Trade placed (exploratory): strategy=%s symbol=%s dir=%s",
                        strat.name,
                        symbol,
                        sig.direction,
                    )
                else:
                    logger.warning(
                        "Trade rejected (exploratory): strategy=%s symbol=%s "
                        "dir=%s reason=%s",
                        strat.name,
                        symbol,
                        sig.direction,
                        res.reason,
                    )
            except Exception as e:
                logger.exception(
                    "Error executing exploratory signal for %s: %s", strat.name, e
                )
                results.append((sig, f"error: {e}"))

    return results