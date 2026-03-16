from __future__ import annotations

from dataclasses import dataclass
from typing import List, Tuple

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

    # Active strategies for this symbol/timeframe
    active_records = [
        rec
        for rec in pool.strategies.values()
        if rec.status == "active" and rec.symbol == symbol and rec.timeframe == timeframe
    ]
    if not active_records:
        return []

    # Need StrategyDefinition instances; for now we reconstruct using minimal fields
    from ..strategies.generator import load_strategy
    from pathlib import Path

    strategies: List[StrategyDefinition] = []
    for rec in active_records:
        path = Path(__file__).resolve().parents[1] / "strategies" / "generated" / f"{rec.name}.json"
        try:
            strategies.append(load_strategy(path))
        except Exception as e:
            logger.exception("Failed to load strategy %s from %s: %s", rec.name, path, e)

    signals = generate_signals_for_row(latest, strategies)
    results: List[Tuple[Signal, str]] = []

    for sig in signals:
        strat = sig.strategy
        try:
            res = execute_trade(
                strategy_name=strat.name,
                symbol=symbol,
                direction=sig.direction,
                risk_perc=risk_perc,
                stop_loss_pips=strat.stop_loss_pips,
                take_profit_pips=strat.take_profit_pips,
                pip_size=0.01 if "XAU" in symbol or "XAG" in symbol else 0.0001,
            )
            results.append((sig, res.reason))
            if res.success:
                logger.info(
                    "Signal executed: strategy=%s symbol=%s dir=%s", strat.name, symbol, sig.direction
                )
            else:
                logger.warning(
                    "Signal not executed: strategy=%s symbol=%s dir=%s reason=%s",
                    strat.name,
                    symbol,
                    sig.direction,
                    res.reason,
                )
        except Exception as e:
            logger.exception("Error executing signal for %s: %s", strat.name, e)
            results.append((sig, f"error: {e}"))

    return results
