from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, List, Optional

import MetaTrader5 as mt5

from ..logging_utils import get_logger
from ..strategies.pool import load_pool, save_pool
from ..config import risk_config
from .live_state_utils import DailyState, save_daily_state, register_trade_pnl
from .strategy_live_stats import register_strategy_pnl

logger = get_logger(__name__)

LIVE_STATE_PATH = Path(__file__).resolve().parent / "equity_history.json"
CLOSED_TRADES_STATE_PATH = Path(__file__).resolve().parent / "closed_trades_state.json"

_MAX_EQUITY_HISTORY = 2016      # ~1 week at 5-min intervals
_MAX_PROCESSED_DEAL_IDS = 1000  # ~6 months at ~5 deals/day
_BASELINE_WARMUP_CYCLES = 3


@dataclass
class LiveStats:
    equity_history: List[float] = field(default_factory=list)
    times: List[str] = field(default_factory=list)
    peak_equity: float = 0.0
    account_identity: dict[str, Any] = field(default_factory=dict)
    baseline_created_at: Optional[str] = None
    warmup_cycles_remaining: int = 0
    last_baseline_reason: str = "initial"

    @classmethod
    def from_dict(cls, data: dict) -> "LiveStats":
        return cls(
            equity_history=data.get("equity_history") or [],
            times=data.get("times") or [],
            peak_equity=float(data.get("peak_equity") or 0.0),
            account_identity=data.get("account_identity") or {},
            baseline_created_at=data.get("baseline_created_at"),
            warmup_cycles_remaining=int(data.get("warmup_cycles_remaining", 0) or 0),
            last_baseline_reason=str(data.get("last_baseline_reason", "initial") or "initial"),
        )

    def to_dict(self) -> dict:
        return {
            "equity_history": self.equity_history,
            "times": self.times,
            "peak_equity": self.peak_equity,
            "account_identity": self.account_identity,
            "baseline_created_at": self.baseline_created_at,
            "warmup_cycles_remaining": self.warmup_cycles_remaining,
            "last_baseline_reason": self.last_baseline_reason,
        }


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------

def _get_account_info():
    info = mt5.account_info()
    if info is None:
        raise RuntimeError("MT5 account_info() returned None")
    return info


def _get_account_equity() -> float:
    info = _get_account_info()
    return float(info.equity)


def _account_identity_from_info(info) -> dict[str, Any]:
    return {
        "login": int(getattr(info, "login", 0) or 0),
        "server": str(getattr(info, "server", "") or ""),
        "currency": str(getattr(info, "currency", "") or ""),
        "company": str(getattr(info, "company", "") or ""),
    }


def _identity_changed(prev: dict[str, Any], current: dict[str, Any]) -> bool:
    if not prev:
        return False
    return (
        prev.get("login") != current.get("login")
        or prev.get("server") != current.get("server")
    )


def _reset_live_baseline(
    stats: LiveStats,
    *,
    equity: float,
    now_iso: str,
    account_identity: dict[str, Any],
    reason: str,
) -> LiveStats:
    stats.equity_history = [equity]
    stats.times = [now_iso]
    stats.peak_equity = equity
    stats.account_identity = account_identity
    stats.baseline_created_at = now_iso
    stats.warmup_cycles_remaining = _BASELINE_WARMUP_CYCLES
    stats.last_baseline_reason = reason

    today = datetime.now(timezone.utc).date().isoformat()
    save_daily_state(DailyState.new(equity=equity, date=today))
    _save_closed_trades_state({"last_check_time": None, "processed_deal_ids": []})
    return stats


def get_equity_peak() -> float:
    """Return all-time equity peak from live state file.

    Used by execution/engine.py to feed the portfolio drawdown guard.
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
        fd, tmp = tempfile.mkstemp(
            dir=CLOSED_TRADES_STATE_PATH.parent,
            prefix=".closed_trades_",
            suffix=".tmp",
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(state, f, indent=2)
            os.replace(tmp, CLOSED_TRADES_STATE_PATH)
        except Exception:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise
    except Exception:
        logger.exception("Failed to save closed_trades_state")


def _update_daily_pnl_from_closed_deals() -> None:
    """Pull new closed MT5 deals and register PnL into DailyState + per-strategy stats.

    Strategy attribution fix (Exness):
    Exness strips special characters from MT5 order comments, so comment-based
    strategy lookup ("clio-auto-{name}") does not work. We instead read from
    ticket_strategy_map.json which is written by signals.py at trade placement.
    """
    from .signals import get_strategy_for_ticket  # avoid circular import at module level

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
        logger.warning("mt5.history_deals_get returned None (from=%s to=%s)", from_time, now)
        return

    processed_ids = set(state.get("processed_deal_ids") or [])

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

        if close_entry_code is not None:
            if getattr(deal, "entry", None) != close_entry_code:
                continue

        pnl = float(getattr(deal, "profit", 0.0))

        try:
            register_trade_pnl(pnl=pnl, current_equity=equity_now)

            # Look up strategy via ticket map (Exness-safe attribution)
            order_ticket = getattr(deal, "order", ticket)
            strategy_name = get_strategy_for_ticket(int(order_ticket))

            if strategy_name:
                try:
                    register_strategy_pnl(strategy_name=strategy_name, pnl=pnl)
                except Exception:
                    logger.exception(
                        "Failed to update StrategyLiveStats for %s", strategy_name
                    )
            else:
                # Fallback: try comment (works on non-Exness brokers)
                comment = getattr(deal, "comment", "") or ""
                if comment.startswith("clio-auto-"):
                    name_from_comment = comment[len("clio-auto-"):]
                    if name_from_comment:
                        try:
                            register_strategy_pnl(
                                strategy_name=name_from_comment, pnl=pnl
                            )
                        except Exception:
                            logger.exception(
                                "Failed to update StrategyLiveStats from comment for %s",
                                name_from_comment,
                            )

            processed_ids.add(ticket)
            trades_processed += 1

        except Exception:
            logger.exception("Failed to register PnL for deal %s", ticket)

    # Cap processed IDs size
    if len(processed_ids) > _MAX_PROCESSED_DEAL_IDS:
        processed_ids = set(
            sorted(processed_ids, reverse=True)[:_MAX_PROCESSED_DEAL_IDS]
        )

    state["last_check_time"] = now.isoformat()
    state["processed_deal_ids"] = sorted(processed_ids)
    _save_closed_trades_state(state)

    if trades_processed:
        logger.info(
            "Processed %d new closed deals → DailyState + StrategyLiveStats",
            trades_processed,
        )


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def update_live_stats() -> None:
    """Update equity history, enforce portfolio circuit breaker,
    and wire closed deals into DailyState + per-strategy stats.
    """
    info = _get_account_info()
    equity = float(info.equity)
    now_iso = datetime.now(timezone.utc).isoformat()
    account_identity = _account_identity_from_info(info)

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

    if not stats.account_identity:
        stats.account_identity = account_identity
        stats.baseline_created_at = stats.baseline_created_at or now_iso
        stats.last_baseline_reason = stats.last_baseline_reason or "initial"

    if _identity_changed(stats.account_identity, account_identity):
        logger.warning(
            "Live monitor: account switch detected (%s@%s -> %s@%s). Refreshing baseline and skipping circuit breaker warmup.",
            stats.account_identity.get("login"),
            stats.account_identity.get("server"),
            account_identity.get("login"),
            account_identity.get("server"),
        )
        stats = _reset_live_baseline(
            stats,
            equity=equity,
            now_iso=now_iso,
            account_identity=account_identity,
            reason="account_switch",
        )
    else:
        stats.equity_history.append(equity)
        stats.times.append(now_iso)
        stats.peak_equity = max(stats.peak_equity, equity)
        stats.account_identity = account_identity
        if not stats.baseline_created_at:
            stats.baseline_created_at = now_iso

    if len(stats.equity_history) > _MAX_EQUITY_HISTORY:
        stats.equity_history = stats.equity_history[-_MAX_EQUITY_HISTORY:]
        stats.times = stats.times[-_MAX_EQUITY_HISTORY:]

    with LIVE_STATE_PATH.open("w", encoding="utf-8") as f:
        json.dump(stats.to_dict(), f, indent=2)

    logger.info(
        "Live monitor: equity=%.2f peak=%.2f login=%s server=%s warmup_cycles=%d baseline_reason=%s",
        equity,
        stats.peak_equity,
        account_identity.get("login"),
        account_identity.get("server"),
        stats.warmup_cycles_remaining,
        stats.last_baseline_reason,
    )

    try:
        _update_daily_pnl_from_closed_deals()
    except Exception:
        logger.exception("Error while updating DailyState from closed deals")

    if stats.warmup_cycles_remaining > 0:
        stats.warmup_cycles_remaining -= 1
        with LIVE_STATE_PATH.open("w", encoding="utf-8") as f:
            json.dump(stats.to_dict(), f, indent=2)
        logger.warning(
            "Live monitor: baseline warmup active (%d cycles remaining) — skipping circuit breaker",
            stats.warmup_cycles_remaining,
        )
        return

    # Portfolio-level circuit breaker
    if stats.peak_equity > 0:
        dd_pct = (stats.peak_equity - equity) / stats.peak_equity * 100.0
        threshold = risk_config.max_portfolio_drawdown_pct

        if dd_pct > threshold:
            pool = load_pool()
            disabled_entries = []
            for rec in pool.strategies.values():
                if rec.status in {"active", "exploratory"}:
                    disabled_entries.append(f"{rec.name}:{rec.status}")
                    rec.status = "disabled"
            if disabled_entries:
                save_pool(pool)
                logger.warning(
                    "Circuit breaker: portfolio DD %.2f%% > %.2f%% — "
                    "disabled %d live-tier strategies (active/exploratory): %s",
                    dd_pct, threshold, len(disabled_entries), disabled_entries,
                )
