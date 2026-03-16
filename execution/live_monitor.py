from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import List

import MetaTrader5 as mt5

from ..logging_utils import get_logger
from ..strategies.pool import load_pool, save_pool
from .live_state_utils import register_trade_pnl
from .strategy_live_stats import register_strategy_pnl

logger = get_logger(__name__)

# Tracks overall equity history over time
LIVE_STATE_PATH = Path(__file__).resolve().parent / "equity_history.json"

# Tracks which closed MT5 deals have already been accounted for in DailyState
CLOSED_TRADES_STATE_PATH = Path(__file__).resolve().parent / "closed_trades_state.json"


@dataclass
class LiveStats:
    equity_history: List[float] = field(default_factory=list)
    times: List[str] = field(default_factory=list)
    peak_equity: float = 0.0


def _get_account_equity() -> float:
    info = mt5.account_info()
    if info is None:
        raise RuntimeError("MT5 account_info() returned None")
    return float(info.equity)


def _load_closed_trades_state() -> dict:
    """Load state for processed closed trades.

    Structure:
    {
      "last_check_time": ISO-8601 string or None,
      "processed_deal_ids": [int, ...]
    }
    """
    import json

    if CLOSED_TRADES_STATE_PATH.exists():
        try:
            with CLOSED_TRADES_STATE_PATH.open("r", encoding="utf-8") as f:
                data = json.load(f)
            # Basic shape validation with safe fallbacks
            last_check_time = data.get("last_check_time")
            processed = data.get("processed_deal_ids") or []
            if not isinstance(processed, list):
                processed = []
            return {
                "last_check_time": last_check_time,
                "processed_deal_ids": processed,
            }
        except Exception:
            logger.exception("Failed to load closed_trades_state, resetting")
    return {"last_check_time": None, "processed_deal_ids": []}


def _save_closed_trades_state(state: dict) -> None:
    import json

    try:
        with CLOSED_TRADES_STATE_PATH.open("w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)
    except Exception:
        logger.exception("Failed to save closed_trades_state")


def _update_daily_pnl_from_closed_deals() -> None:
    """Pull new closed MT5 deals and wire them into DailyState and per-strategy stats.

    This function:
    - reads the last check time and processed deal ids,
    - calls mt5.history_deals_get(last_check_time, now),
    - filters for close/exit deals,
    - for each new deal, calls register_trade_pnl(pnl, equity_now),
      and updates per-strategy live stats based on deal.comment,
    - updates state so the same deal is not processed twice.

    Any errors are logged but should not crash the live monitor.
    """
    from datetime import datetime, timedelta, timezone

    state = _load_closed_trades_state()

    now = datetime.now(timezone.utc)
    last_check_str = state.get("last_check_time")
    if last_check_str:
        try:
            # fromisoformat supports timezone info; fall back to UTC-naive if needed
            from_time = datetime.fromisoformat(last_check_str)
            if from_time.tzinfo is None:
                from_time = from_time.replace(tzinfo=timezone.utc)
        except Exception:
            logger.exception("Invalid last_check_time in closed_trades_state, resetting window")
            from_time = now - timedelta(days=7)
    else:
        # On first run, look back a reasonable window; old trades will be
        # processed once and then never again.
        from_time = now - timedelta(days=7)

    try:
        deals = mt5.history_deals_get(from_time, now)
    except Exception:
        logger.exception("Error calling mt5.history_deals_get")
        return

    if deals is None:
        # MT5 can return None on error; we log via account/terminal logs separately.
        logger.warning("mt5.history_deals_get returned None (from %s to %s)", from_time, now)
        return

    processed_ids = set(state.get("processed_deal_ids") or [])

    # We will update equity lazily; equity_now may change slightly over time,
    # but for daily stats granularity this is acceptable.
    trades_processed = 0

    for deal in deals:
        ticket = getattr(deal, "ticket", None)
        if ticket is None or ticket in processed_ids:
            continue

        # Only consider exit/close deals as realized PnL events
        entry = getattr(deal, "entry", None)
        try:
            close_entry_code = mt5.DEAL_ENTRY_OUT
        except AttributeError:
            close_entry_code = None

        if close_entry_code is not None and entry != close_entry_code:
            continue

        pnl = float(getattr(deal, "profit", 0.0))

        try:
            equity_now = _get_account_equity()
            register_trade_pnl(pnl=pnl, current_equity=equity_now)

            # Update per-strategy live stats using MT5 comment, which is set
            # by execution.engine.execute_trade as "clio-auto-{strategy_name}".
            comment = getattr(deal, "comment", "") or ""
            if comment.startswith("clio-auto-"):
                strategy_name = comment.replace("clio-auto-", "", 1)
                if strategy_name:
                    try:
                        register_strategy_pnl(strategy_name=strategy_name, pnl=pnl)
                    except Exception:
                        logger.exception("Failed to update StrategyLiveStats for %s", strategy_name)

            processed_ids.add(ticket)
            trades_processed += 1
        except Exception:
            logger.exception("Failed to register trade PnL for deal %s", ticket)

    # Persist updated state
    state["last_check_time"] = now.isoformat()
    state["processed_deal_ids"] = sorted(processed_ids)
    _save_closed_trades_state(state)

    if trades_processed:
        logger.info("Processed %d new closed deals into DailyState and StrategyLiveStats", trades_processed)


def update_live_stats() -> None:
    """Update live equity history and disable strategies far from expectations.

    This now also wires closed MT5 deals into DailyState so that
    daily_pnl / daily_return_pct / trades_today are backed by *real* account
    history, not synthetic updates. In addition, per-strategy live PnL stats
    are updated from deal comments for future degradation detection.
    """
    import json
    from datetime import datetime

    equity = _get_account_equity()
    now_iso = datetime.utcnow().isoformat() + "Z"

    if LIVE_STATE_PATH.exists():
        with LIVE_STATE_PATH.open("r", encoding="utf-8") as f:
            data = json.load(f)
        stats = LiveStats(**data)
    else:
        stats = LiveStats()

    stats.equity_history.append(equity)
    stats.times.append(now_iso)
    stats.peak_equity = max(stats.peak_equity, equity)

    with LIVE_STATE_PATH.open("w", encoding="utf-8") as f:
        json.dump({
            "equity_history": stats.equity_history,
            "times": stats.times,
            "peak_equity": stats.peak_equity,
        }, f, indent=2)

    logger.info("Live monitor: equity=%.2f peak=%.2f", equity, stats.peak_equity)

    # Wire in closed trades to DailyState (PnL, return %, trades_today)
    # and per-strategy live stats.
    try:
        _update_daily_pnl_from_closed_deals()
    except Exception:
        # We don't want PnL wiring issues to break basic live monitoring
        logger.exception("Error while updating DailyState from closed deals")

    # Placeholder: strategy-level disabling could be implemented here by
    # comparing live drawdown vs. per-strategy backtest expectations.
    pool = load_pool()
    # e.g., if overall drawdown breaches a threshold, disable all active
    # strategies until reviewed.
    if stats.peak_equity > 0:
        dd_pct = (stats.peak_equity - equity) / stats.peak_equity * 100.0
        # This threshold is arbitrary here; in practice we would align it with
        # risk_config and per-strategy expectations.
        if dd_pct > 30.0:
            for rec in pool.strategies.values():
                if rec.status == "active":
                    rec.status = "disabled"
                    logger.warning(
                        "Live monitor: disabling strategy %s due to portfolio DD %.2f%%",
                        rec.name,
                        dd_pct,
                    )
            save_pool(pool)
