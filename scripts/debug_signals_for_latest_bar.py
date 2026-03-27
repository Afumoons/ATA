from __future__ import annotations

from pathlib import Path
from typing import Any

from autonomous_trading_ai.config import risk_config
from autonomous_trading_ai.logging_utils import get_logger
from autonomous_trading_ai.scheduler.main import MANAGED_SYMBOLS, TIMEFRAME
from autonomous_trading_ai.data.collector_mt5 import initialize_mt5, shutdown_mt5
from autonomous_trading_ai.research.features import load_features
from autonomous_trading_ai.strategies.pool import load_pool
from autonomous_trading_ai.execution.signals import (
    execute_signals_for_symbol,
    _regime_edge,  # type: ignore[attr-defined]
)
from autonomous_trading_ai.execution.live_monitor import _get_account_equity
from autonomous_trading_ai.execution.live_state_utils import can_open_new_trade

logger = get_logger(__name__)


def debug_symbol(symbol: str) -> None:
    print("==== DEBUG", symbol, TIMEFRAME, "====")

    # Load features
    try:
        feat = load_features(symbol, TIMEFRAME)
    except FileNotFoundError:
        print("[WARN] No features file found for", symbol, TIMEFRAME)
        return
    except Exception as e:
        print("[ERROR] Failed to load features for", symbol, TIMEFRAME, ":", e)
        return

    if feat.empty:
        print("[WARN] Features DF is empty for", symbol, TIMEFRAME)
        return

    latest = feat.sort_values("time").iloc[-1]
    current_regime = str(latest.get("regime", "unknown"))
    print("Latest bar time:", latest.get("time"))
    print("Current regime:", current_regime)

    # Daily limits
    from autonomous_trading_ai.execution.live_state_utils import load_daily_state

    equity = _get_account_equity()
    daily_state = load_daily_state(current_equity=equity)
    print("Account equity:", equity)
    print(
        "Daily state:",
        {
            "date": daily_state.date,
            "equity_start": daily_state.equity_start,
            "equity_current": daily_state.equity_current,
            "daily_pnl": daily_state.daily_pnl,
            "daily_return_pct": daily_state.daily_return_pct,
            "trades_today": daily_state.trades_today,
            "locked_for_day": daily_state.locked_for_day,
        },
    )

    can_trade = can_open_new_trade(
        current_equity=equity,
        max_dd_pct=risk_config.max_daily_drawdown_pct,
        max_trades=risk_config.max_trades_per_day,
        enabled=risk_config.daily_limits_enabled,
    )
    print("Daily limits allow new trade?", can_trade)
    if not can_trade:
        print("[INFO] Daily limits currently block any new auto trade.")

    # Pool
    pool = load_pool()
    records = [
        rec
        for rec in pool.strategies.values()
        if rec.symbol == symbol and rec.timeframe == TIMEFRAME
    ]
    print("Total strategies for", symbol, TIMEFRAME, ":", len(records))
    for rec in records:
        print(" -", rec.name, "status=", rec.status, "score=", round(rec.score, 3))

    # If daily limits already block, we still continue to show what WOULD happen.

    # Call execute_signals_for_symbol but intercept results only (no special flag needed;
    # it already returns (Signal, reason) tuples).
    risk_perc = min(0.5, risk_config.max_risk_per_trade_pct)
    print("Configured risk_perc: ", risk_perc)

    # Precompute regime edges per strategy
    regime_label = current_regime
    edges: dict[str, float] = {}
    for rec in records:
        try:
            edge, _selected_label = _regime_edge(rec.stats or {}, [regime_label])
        except Exception:
            edge = float("nan")
        edges[rec.name] = edge

    print("Regime edges (", regime_label, "):")
    for rec in records:
        print(
            " -", rec.name,
            "status=", rec.status,
            "edge=", round(edges.get(rec.name, float("nan")), 3),
        )

    print("\nRunning execute_signals_for_symbol (this will attempt execution):")
    results, summary = execute_signals_for_symbol(symbol, TIMEFRAME, feat, pool, risk_perc)

    print("Routing summary:", summary)
    if not results:
        print("No signals executed or all blocked.")
    else:
        for sig, reason in results:
            print(
                "Signal:",
                {
                    "strategy": sig.strategy.name,
                    "direction": sig.direction,
                    "reason": reason,
                },
            )


def main() -> None:
    # Ensure MT5 is initialized so account_info() and history calls work.
    initialize_mt5()
    try:
        for symbol in MANAGED_SYMBOLS:
            debug_symbol(symbol)
            print("\n")
    finally:
        shutdown_mt5()


if __name__ == "__main__":
    main()
