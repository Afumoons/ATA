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

ACTIVE_REGIME_EDGE_THRESHOLD = 0.0
EXPLORATORY_REGIME_EDGE_THRESHOLD = -10.0


@dataclass
class Signal:
    strategy: StrategyDefinition
    direction: str  # "long" or "short"


def _pip_params(symbol: str) -> tuple[float, float]:
    """Return (pip_size, pip_value_per_lot) for a given symbol.

    Pip size is the price distance of 1 pip.
    Pip value per lot is the $ value of 1 pip movement per standard lot.

    Metals  (XAU/XAG): pip_size=0.01,  pip_value=1.0  ($1/pip/lot)
    Crypto  (BTC/ETH):  pip_size=1.0,   pip_value=1.0  ($1/pip/lot, 1 lot=1 coin)
    Forex   (default):  pip_size=0.0001, pip_value=10.0 ($10/pip/lot)

    Without this, BTC SL of 150 pips × 0.0001 = $0.015 — rejected as
    'Invalid stops' by broker (retcode 10016).
    """
    sym = symbol.upper()
    if "XAU" in sym or "XAG" in sym:
        return 0.01, 1.0
    if "BTC" in sym or "ETH" in sym or "LTC" in sym or "XRP" in sym:
        return 1.0, 1.0
    return 0.0001, 10.0


def generate_signals_for_row(
    row: pd.Series,
    strategies: List[StrategyDefinition],
) -> List[Signal]:
    from ..backtests.engine import _eval_rule

    signals: List[Signal] = []
    for strat in strategies:
        long_hit = _eval_rule(row, strat.long_entry_rule)
        short_hit = _eval_rule(row, strat.short_entry_rule)

        logger.debug(
            "Entry eval: strategy=%s long_rule='%s' -> %s | short_rule='%s' -> %s",
            strat.name, strat.long_entry_rule, long_hit,
            strat.short_entry_rule, short_hit,
        )

        if long_hit:
            signals.append(Signal(strategy=strat, direction="long"))
        if short_hit:
            signals.append(Signal(strategy=strat, direction="short"))

    return signals


def _regime_edge(stats: Dict[str, Any], regime_label: str) -> float:
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
) -> Tuple[List[Tuple[Signal, str]], Dict[str, bool]]:
    summary: Dict[str, bool] = {
        "blocked_daily_limits": False,
        "no_strategies_in_pool": False,
        "no_strategies_with_edge": False,
        "no_entry_active": False,
        "no_entry_exploratory": False,
    }

    if features_df.empty:
        logger.warning("execute_signals_for_symbol: empty features_df for %s %s", symbol, timeframe)
        summary["no_strategies_with_edge"] = True
        return [], summary

    latest = features_df.sort_values("time").iloc[-1]
    current_regime = str(latest.get("regime", "unknown"))
    logger.info("Current regime for %s %s: %s", symbol, timeframe, current_regime)

    from ..config import risk_config
    from ..execution.live_monitor import _get_account_equity

    current_equity = _get_account_equity()
    logger.debug(
        "Daily limits check: symbol=%s equity=%.2f max_dd_pct=%.2f max_trades=%d enabled=%s",
        symbol, current_equity, risk_config.max_daily_drawdown_pct,
        risk_config.max_trades_per_day, risk_config.daily_limits_enabled,
    )

    if not can_open_new_trade(
        current_equity=current_equity,
        max_dd_pct=risk_config.max_daily_drawdown_pct,
        max_trades=risk_config.max_trades_per_day,
        enabled=risk_config.daily_limits_enabled,
    ):
        logger.info(
            "Daily limits prevent opening new trades for %s %s (equity=%.2f)",
            symbol, timeframe, current_equity,
        )
        summary["blocked_daily_limits"] = True
        return [], summary

    active_records = [
        rec for rec in pool.strategies.values()
        if rec.status == "active" and rec.symbol == symbol and rec.timeframe == timeframe
    ]
    exploratory_records = [
        rec for rec in pool.strategies.values()
        if rec.status == "exploratory" and rec.symbol == symbol and rec.timeframe == timeframe
    ]

    if not active_records and not exploratory_records:
        logger.info("No active or exploratory strategies in pool for %s %s", symbol, timeframe)
        summary["no_strategies_in_pool"] = True
        return [], summary

    regime_label = _map_current_to_regime_pnl_label(current_regime)

    def _filter_and_rank(records, tier: str) -> List[Any]:
        if not records:
            return []

        if regime_label == "unknown":
            logger.warning(
                "Unknown regime for %s %s — skipping regime filter, passing all %d %s strategies",
                symbol, timeframe, len(records), tier,
            )
            return records

        threshold = ACTIVE_REGIME_EDGE_THRESHOLD if tier == "active" else EXPLORATORY_REGIME_EDGE_THRESHOLD

        scored: List[Tuple[float, Any]] = []
        for rec in records:
            edge = _regime_edge(rec.stats or {}, regime_label)
            scored.append((edge, rec))
            logger.info(
                "Regime edge: symbol=%s timeframe=%s regime=%s strategy=%s tier=%s edge=%.3f threshold=%.1f",
                symbol, timeframe, regime_label, rec.name, tier, edge, threshold,
            )

        kept = [(edge, rec) for edge, rec in scored if edge > threshold]
        kept.sort(key=lambda er: er[0], reverse=True)
        filtered = [rec for _, rec in kept]

        if len(filtered) != len(records):
            blocked_names = [rec.name for edge, rec in scored if edge <= threshold]
            logger.info(
                "Regime filter for %s %s (%s) [tier=%s]: %d -> %d strategies passed "
                "(threshold=%.1f) | blocked: %s",
                symbol, timeframe, regime_label, tier,
                len(records), len(filtered), threshold, blocked_names,
            )

        if not filtered and scored and tier == "exploratory":
            scored.sort(key=lambda er: er[0], reverse=True)
            best_edge, best_rec = scored[0]
            filtered = [best_rec]
            logger.info(
                "Regime fallback for %s %s (%s): keeping best exploratory edge=%.2f",
                symbol, timeframe, regime_label, best_edge,
            )

        if not filtered:
            logger.info(
                "All %s strategies blocked by regime filter for %s %s (regime=%s, threshold=%.1f)",
                tier, symbol, timeframe, regime_label, threshold,
            )

        return filtered

    active_records = _filter_and_rank(active_records, tier="active")
    exploratory_records = _filter_and_rank(exploratory_records, tier="exploratory")

    MAX_ACTIVE_PER_SYMBOL = 5
    MAX_EXPLORATORY_PER_SYMBOL = 3
    active_records = active_records[:MAX_ACTIVE_PER_SYMBOL]
    exploratory_records = exploratory_records[:MAX_EXPLORATORY_PER_SYMBOL]

    if not active_records and not exploratory_records:
        logger.info(
            "No strategies with acceptable regime edge for %s %s (regime=%s)",
            symbol, timeframe, current_regime,
        )
        summary["no_strategies_with_edge"] = True
        return [], summary

    from ..strategies.generator import load_strategy
    from pathlib import Path

    base_dir = Path(__file__).resolve().parents[1] / "strategies" / "generated"

    active_strategies: List[StrategyDefinition] = []
    for rec in active_records:
        path = base_dir / f"{rec.name}.json"
        try:
            active_strategies.append(load_strategy(path))
        except Exception as e:
            logger.exception("Failed to load active strategy %s: %s", rec.name, e)

    exploratory_strategies: List[StrategyDefinition] = []
    for rec in exploratory_records:
        path = base_dir / f"{rec.name}.json"
        try:
            exploratory_strategies.append(load_strategy(path))
        except Exception as e:
            logger.exception("Failed to load exploratory strategy %s: %s", rec.name, e)

    logger.info(
        "Feature snapshot for %s %s: time=%s regime=%s "
        "ma_short=%.5f ma_long=%.5f trend_strength=%.4f rsi=%.2f",
        symbol, timeframe, latest.get("time", "?"), current_regime,
        float(latest.get("ma_short", float("nan"))),
        float(latest.get("ma_long", float("nan"))),
        float(latest.get("trend_strength", float("nan"))),
        float(latest.get("rsi", float("nan"))),
    )

    results: List[Tuple[Signal, str]] = []
    risk_perc_active = risk_perc
    risk_perc_exploratory = min(risk_perc * 0.25, 0.1)

    # Resolve pip params once per symbol
    pip_size, pip_value_per_lot = _pip_params(symbol)
    logger.debug(
        "Pip params for %s: pip_size=%s pip_value_per_lot=%s",
        symbol, pip_size, pip_value_per_lot,
    )

    # ------------------------------------------------------------------ #
    # Active strategies                                                   #
    # ------------------------------------------------------------------ #
    if active_strategies:
        active_signals = generate_signals_for_row(latest, active_strategies)

        if not active_signals:
            logger.info(
                "No entry conditions met for active strategies on %s %s "
                "(regime=%s, %d strategies evaluated)",
                symbol, timeframe, current_regime, len(active_strategies),
            )
            summary["no_entry_active"] = True
        else:
            logger.info(
                "%d signal(s) generated from active strategies for %s %s",
                len(active_signals), symbol, timeframe,
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
                    pip_size=pip_size,
                    pip_value_per_lot=pip_value_per_lot,
                )
                results.append((sig, res.reason))
                if res.success:
                    logger.info(
                        "Trade placed (active): strategy=%s symbol=%s dir=%s vol=%s ticket=%s",
                        strat.name, symbol, sig.direction,
                        getattr(res, "volume", "?"), getattr(res, "ticket", "?"),
                    )
                else:
                    logger.warning(
                        "Trade rejected (active): strategy=%s symbol=%s dir=%s reason=%s",
                        strat.name, symbol, sig.direction, res.reason,
                    )
            except Exception as e:
                logger.exception("Error executing active signal for %s: %s", strat.name, e)
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
                symbol, timeframe, current_regime, len(exploratory_strategies),
            )
            summary["no_entry_exploratory"] = True
        else:
            logger.info(
                "%d signal(s) generated from exploratory strategies for %s %s",
                len(exploratory_signals), symbol, timeframe,
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
                    pip_size=pip_size,
                    pip_value_per_lot=pip_value_per_lot,
                )
                results.append((sig, res.reason))
                if res.success:
                    logger.info(
                        "Trade placed (exploratory): strategy=%s symbol=%s dir=%s",
                        strat.name, symbol, sig.direction,
                    )
                else:
                    logger.warning(
                        "Trade rejected (exploratory): strategy=%s symbol=%s dir=%s reason=%s",
                        strat.name, symbol, sig.direction, res.reason,
                    )
            except Exception as e:
                logger.exception("Error executing exploratory signal for %s: %s", strat.name, e)
                results.append((sig, f"error: {e}"))

    return results, summary