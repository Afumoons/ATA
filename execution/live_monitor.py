from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Optional
import json

import MetaTrader5 as mt5

from ..logging_utils import get_logger
from ..strategies.pool import load_pool, save_pool
from ..config import risk_config
from .live_state_utils import register_trade_pnl
from .strategy_live_stats import register_strategy_pnl

logger = get_logger(__name__)

LIVE_STATE_PATH = Path(__file__).resolve().parent / "equity_history.json"
CLOSED_TRADES_STATE_PATH = Path(__file__).resolve().parent / "closed_trades_state.json"

# Rolling window for equity history and processed deal IDs.
# At 5-min intervals, 2016 points = ~1 week of history retained in memory.
_MAX_EQUITY_HISTORY = 2016
# Keep only the last N deal IDs to prevent unbounded JSON growth.
# At ~5 deals/day, 1000 covers ~6 months.
_MAX_PROCESSED_DEAL_IDS = 1000


@dataclass
class LiveStats:
    equity_history: List[float] = field(default_factory=list)
    times: List[str] = field(default_factory=list)
    peak_equity: float = 0.0

    @classmethod
    def from_dict(cls, data: dict) -> "LiveStats":
        """Safe deserialization — tolerates missing or extra keys."""
        return cls(
            equity_history=data.get("equity_history") or [],
            times=data.get("times") or [],
            peak_equity=float(data.get("peak_equity") or 0.0),
        )

    def to_dict(self) -> dict:
        return {
            "equity_history": self.equity_history,
            "times": self.times,
            "peak_equity": self.peak_equity,
        }


# ---------------------------------------------------------------------------
# Public helpers — used by execution/engine.py
# ---------------------------------------------------------------------------

def _get_account_equity() -> float:
    info = mt5.account_info()
    if info is None:
        raise RuntimeError("MT5 account_info() returned None")
    return float(info.equity)


def get_equity_peak() -> float:
    """Return the all-time equity peak stored in the live state file.

    Used by execution/engine.py to feed the drawdown guard in risk/manager.py.
    Falls back to current equity if no history is available.
    """
    if LIVE_STATE_PATH.exists():
        try:
            with LIVE_STATE_PATH.open("r", encoding="utf-8") as f:
                data = json.load(f)
            peak = float(data.get("peak_equity") or 0.0)
            if peak > 0:
                return peak
        except Exception:
            logger.exception("Failed to read equity peak from live state")
    # Fallback: return current equity (drawdown guard disabled effectively)
    try:
        return _get_account_equity()
    except Exception:
        return 0.0


# ---------------------------------------------------------------------------
# Closed trades state
# ---------------------------------------------------------------------------

def _load_closed_trades_state() -> dict:
    if CLOSED_TRADES_STATE_PATH.exists():
        try:
            with CLOSED_TRADES_STATE_PATH.open("r", encoding="utf-8") as f:
                data = json.load(f)
            processed = data.get("processed_deal_ids") or []
            if not isinstance(processed, list):
                processed = []
            return {
                "last_check_time": data.get("last_check_time"),
                "processed_deal_ids": processed,
            }
        except Exception:
            logger.exception("Failed to load closed_trades_state, resetting")
    return {"last_check_time": None, "processed_deal_ids": []}


def _save_closed_trades_state(state: dict) -> None:
    try:
        with CLOSED_TRADES_STATE_PATH.open("w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)
    except Exception:
        logger.exception("Failed to save closed_trades_state")


def _update_daily_pnl_from_closed_deals() -> None:
    """Pull new closed MT5 deals and register PnL into DailyState and per-strategy stats.

    Bug fixes vs original:
    - _get_account_equity() called ONCE before loop, not per-deal (was N MT5 calls)
    - Strategy name lookup uses full comment with no truncation assumption —
      matches execution/engine.py which stores full name (truncated to 20 chars there,
      so we strip prefix and accept whatever remains)
    - processed_deal_ids capped at _MAX_PROCESSED_DEAL_IDS to prevent unbounded growth
    - datetime.utcnow() replaced with datetime.now(timezone.utc) (utcnow deprecated 3.12+)
    """
    state = _load_closed_trades_state()

    now = datetime.now(timezone.utc)
    last_check_str = state.get("last_check_time")

    if last_check_str:
        try:
            from_time = datetime.fromisoformat(last_check_str)
            if from_time.tzinfo is None:
                from_time = from_time.replace(tzinfo=timezone.utc)
        except Exception:
            logger.exception("Invalid last_check_time, resetting to 7-day window")
            from_time = now - timedelta(days=7)
    else:
        from_time = now - timedelta(days=7)

    try:
        deals = mt5.history_deals_get(from_time, now)
    except Exception:
        logger.exception("Error calling mt5.history_deals_get")
        return

    if deals is None:
        logger.warning(
            "mt5.history_deals_get returned None (from=%s to=%s)", from_time, now
        )
        return

    processed_ids = set(state.get("processed_deal_ids") or [])

    # Fetch equity once — avoids an MT5 round-trip per deal
    try:
        equity_now = _get_account_equity()
    except Exception:
        logger.exception("Could not get equity for PnL registration")
        return

    close_entry_code: Optional[int] = getattr(mt5, "DEAL_ENTRY_OUT", None)
    trades_processed = 0

    for deal in deals:
        ticket = getattr(deal, "ticket", None)
        if ticket is None or ticket in processed_ids:
            continue

        # Only realized close/exit events
        if close_entry_code is not None:
            entry = getattr(deal, "entry", None)
            if entry != close_entry_code:
                continue

        pnl = float(getattr(deal, "profit", 0.0))

        try:
            register_trade_pnl(pnl=pnl, current_equity=equity_now)

            # execution/engine.py sets comment = "clio-auto-{strategy_name[:20]}"
            comment = getattr(deal, "comment", "") or ""
            if comment.startswith("clio-auto-"):
                strategy_name = comment[len("clio-auto-"):]
                if strategy_name:
                    try:
                        register_strategy_pnl(
                            strategy_name=strategy_name, pnl=pnl
                        )
                    except Exception:
                        logger.exception(
                            "Failed to update StrategyLiveStats for %s", strategy_name
                        )

            processed_ids.add(ticket)
            trades_processed += 1

        except Exception:
            logger.exception("Failed to register PnL for deal %s", ticket)

    # Cap processed_deal_ids size — keep most recent N
    if len(processed_ids) > _MAX_PROCESSED_DEAL_IDS:
        # Can't sort by time here so keep largest ticket numbers (most recent)
        processed_ids = set(
            sorted(processed_ids, reverse=True)[:_MAX_PROCESSED_DEAL_IDS]
        )

    state["last_check_time"] = now.isoformat()
    state["processed_deal_ids"] = sorted(processed_ids)
    _save_closed_trades_state(state)

    if trades_processed:
        logger.info(
            "Processed %d new closed deals into DailyState + StrategyLiveStats",
            trades_processed,
        )


# ---------------------------------------------------------------------------
# Main entry point called by scheduler
# ---------------------------------------------------------------------------

def update_live_stats() -> None:
    """Update equity history, enforce portfolio drawdown circuit breaker,
    and wire closed MT5 deals into DailyState + per-strategy stats.
    """
    equity = _get_account_equity()
    now_iso = datetime.now(timezone.utc).isoformat()

    # Load existing state
    if LIVE_STATE_PATH.exists():
        try:
            with LIVE_STATE_PATH.open("r", encoding="utf-8") as f:
                data = json.load(f)
            stats = LiveStats.from_dict(data)
        except Exception:
            logger.exception("Failed to load equity_history, starting fresh")
            stats = LiveStats()
    else:
        stats = LiveStats()

    stats.equity_history.append(equity)
    stats.times.append(now_iso)
    stats.peak_equity = max(stats.peak_equity, equity)

    # Rolling window — prevent unbounded file growth
    if len(stats.equity_history) > _MAX_EQUITY_HISTORY:
        stats.equity_history = stats.equity_history[-_MAX_EQUITY_HISTORY:]
        stats.times = stats.times[-_MAX_EQUITY_HISTORY:]

    with LIVE_STATE_PATH.open("w", encoding="utf-8") as f:
        json.dump(stats.to_dict(), f, indent=2)

    logger.info("Live monitor: equity=%.2f peak=%.2f", equity, stats.peak_equity)

    # Wire closed deals into DailyState + per-strategy stats
    try:
        _update_daily_pnl_from_closed_deals()
    except Exception:
        logger.exception("Error while updating DailyState from closed deals")

    # ------------------------------------------------------------------ #
    # Portfolio-level circuit breaker                                     #
    # Uses risk_config.max_portfolio_drawdown_pct — was hardcoded 30.0   #
    # ------------------------------------------------------------------ #
    if stats.peak_equity > 0:
        dd_pct = (stats.peak_equity - equity) / stats.peak_equity * 100.0
        threshold = risk_config.max_portfolio_drawdown_pct

        if dd_pct > threshold:
            pool = load_pool()
            disabled_names = []
            for rec in pool.strategies.values():
                if rec.status == "active":
                    rec.status = "disabled"
                    disabled_names.append(rec.name)

            if disabled_names:
                save_pool(pool)
                logger.warning(
                    "Circuit breaker triggered: portfolio DD %.2f%% > %.2f%% — "
                    "disabled %d active strategies: %s",
                    dd_pct,
                    threshold,
                    len(disabled_names),
                    disabled_names,
                )