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
from .strategy_live_stats import register_manual_bucket_pnl, register_strategy_pnl
from .audit_utils import append_unmatched_closed_deal, append_pool_audit, append_circuit_breaker_event
from .trade_context_journal import register_trade_exit_context

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
    trades_processed = 0

    try:
        equity_now = _get_account_equity()
    except Exception:
        logger.exception("Could not get equity for PnL registration")
        return

    close_entry_code: Optional[int] = getattr(mt5, "DEAL_ENTRY_OUT", None)
    if close_entry_code is None:
        logger.warning("MT5 DEAL_ENTRY_OUT constant not found — using fallback filter")

    for deal in deals:
        # Filter deal type DULU, sebelum cek ticket
        if close_entry_code is not None:
            if getattr(deal, "entry", None) != close_entry_code:
                continue
        else:
            # Fallback: skip deals tanpa profit dan tanpa position context
            if float(getattr(deal, "profit", 0.0)) == 0.0 and getattr(deal, "position_id", None) is None:
                continue

        ticket = getattr(deal, "ticket", None)
        if ticket is None or ticket in processed_ids:
            continue

        pnl = float(getattr(deal, "profit", 0.0))
        symbol_raw = getattr(deal, "symbol", "") or ""
        symbol_canon = symbol_raw
        try:
            from ..config import canonical_symbol
            symbol_canon = canonical_symbol(symbol_raw)
        except Exception:
            symbol_canon = symbol_raw

        try:
            # Pass equity_now hanya untuk update equity_current di state,
            # bukan sebagai "equity saat deal terjadi"
            register_trade_pnl(pnl=pnl, current_equity=equity_now)
            # equity_now di sini berarti: "setelah semua deal diproses, 
            # equity current yang kita tau adalah X" — ini semantiknya benar

            # Look up strategy via ticket map (Exness-safe attribution)
            order_ticket = getattr(deal, "order", None)
            position_id = getattr(deal, "position_id", None)
            strategy_name = None

            for candidate_ticket in (order_ticket, position_id, ticket):
                if candidate_ticket is None:
                    continue
                try:
                    strategy_name = get_strategy_for_ticket(int(candidate_ticket))
                except Exception:
                    strategy_name = None
                if strategy_name:
                    break

            if strategy_name:
                try:
                    register_strategy_pnl(strategy_name=strategy_name, pnl=pnl)
                    try:
                        register_trade_exit_context(
                            ticket=ticket,
                            symbol=symbol_canon,
                            pnl=pnl,
                        )
                    except Exception:
                        logger.exception(
                            "Failed to register trade exit context for %s deal=%s",
                            strategy_name,
                            ticket,
                        )
                    try:
                        from .signals import register_ticket  # type: ignore
                        register_ticket(ticket, strategy_name, order_ticket, position_id)
                    except Exception:
                        logger.exception(
                            "Failed to refresh ticket aliases for closed deal %s -> %s",
                            ticket,
                            strategy_name,
                        )
                except Exception:
                    logger.exception(
                        "Failed to update StrategyLiveStats for %s", strategy_name
                    )
            else:
                comment = getattr(deal, "comment", "") or ""

                resolved_from_candidates = None
                candidate_matches: list[str] = []
                try:
                    from .signals import _load_ticket_map  # type: ignore
                    ticket_map = _load_ticket_map()
                    candidate_suffixes = []
                    if order_ticket is not None:
                        candidate_suffixes.append(str(order_ticket))
                    if position_id is not None:
                        candidate_suffixes.append(str(position_id))
                    candidate_suffixes.append(str(ticket))

                    comment_uid4 = ""
                    if comment:
                        compact_comment = "".join(ch for ch in str(comment) if ch.isalnum())
                        if len(compact_comment) >= 4:
                            comment_uid4 = compact_comment[-4:].lower()

                    for mapped_ticket, mapped_name in ticket_map.items():
                        mapped_name = str(mapped_name)
                        mapped_upper = mapped_name.upper()
                        mapped_uid4 = mapped_name.split("_")[-1][:4].lower() if "_" in mapped_name else mapped_name[-4:].lower()
                        symbol_ok = not symbol_canon or symbol_canon.upper() in mapped_upper or symbol_raw.upper() in mapped_upper
                        suffix_ok = any(sfx and mapped_ticket.endswith(sfx[-6:]) for sfx in candidate_suffixes if sfx)
                        comment_ok = bool(comment_uid4 and mapped_uid4 == comment_uid4)
                        if symbol_ok and (suffix_ok or comment_ok):
                            candidate_matches.append(mapped_name)

                    candidate_matches = list(dict.fromkeys(candidate_matches))
                    if len(candidate_matches) == 1:
                        resolved_from_candidates = candidate_matches[0]
                except Exception:
                    logger.exception("Failed heuristic attribution for closed deal %s", ticket)

                if resolved_from_candidates:
                    strategy_name = resolved_from_candidates
                    try:
                        register_strategy_pnl(strategy_name=strategy_name, pnl=pnl)
                        try:
                            from .signals import register_ticket  # type: ignore
                            register_ticket(ticket, strategy_name, order_ticket, position_id)
                        except Exception:
                            logger.exception(
                                "Failed to persist recovered ticket aliases for closed deal %s -> %s",
                                ticket,
                                strategy_name,
                            )
                        logger.info(
                            "Recovered strategy attribution heuristically for closed deal ticket=%s -> %s",
                            ticket,
                            strategy_name,
                        )
                    except Exception:
                        logger.exception(
                            "Failed to update StrategyLiveStats for heuristic attribution %s",
                            strategy_name,
                        )
                else:
                    manual_bucket = register_manual_bucket_pnl(
                        symbol=symbol_canon,
                        pnl=pnl,
                        unmatched=True,
                    )
                    logger.warning(
                        "No strategy attribution for closed deal ticket=%s order=%s position_id=%s comment=%s profit=%.2f -> bucket=%s",
                        ticket,
                        order_ticket,
                        position_id,
                        comment,
                        pnl,
                        manual_bucket,
                    )
                    append_unmatched_closed_deal({
                        "deal_ticket": ticket,
                        "order_ticket": order_ticket,
                        "position_id": position_id,
                        "comment": comment,
                        "profit": pnl,
                        "symbol": symbol_raw,
                        "symbol_canonical": symbol_canon,
                        "entry": getattr(deal, "entry", None),
                        "reason": "ticket_map_miss",
                        "candidate_matches": candidate_matches[:5],
                        "comment_uid4": ("".join(ch for ch in str(comment) if ch.isalnum())[-4:].lower() if comment else ""),
                        "manual_bucket": manual_bucket,
                    })
                    # Fallback: try comment (works on non-Exness brokers)
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
            disabled_names = []
            now_iso = datetime.now(timezone.utc).isoformat()
            for rec in pool.strategies.values():
                if rec.status in {"active", "exploratory"}:
                    previous_status = rec.status
                    disabled_entries.append(f"{rec.name}:{previous_status}")
                    disabled_names.append(rec.name)
                    rec.status = "disabled"
                    rec.stats = rec.stats or {}
                    rec.stats["circuit_breaker_disabled_at"] = now_iso
                    rec.stats["circuit_breaker_previous_status"] = previous_status
                    rec.stats["circuit_breaker_dd_pct"] = dd_pct
                    rec.stats["circuit_breaker_threshold"] = threshold
            if disabled_entries:
                save_pool(pool)
                audit_payload = {
                    "event": "circuit_breaker_disable",
                    "dd_pct": dd_pct,
                    "threshold": threshold,
                    "disabled_entries": disabled_entries,
                    "disabled_count": len(disabled_entries),
                    "recovery_hint": "restore_to_exploratory_then_re-promote_selectively",
                    "baseline_created_at": stats.baseline_created_at,
                    "account_identity": stats.account_identity,
                }
                append_pool_audit(audit_payload)
                append_circuit_breaker_event(audit_payload)
                logger.warning(
                    "Circuit breaker: portfolio DD %.2f%% > %.2f%% — "
                    "disabled %d live-tier strategies (active/exploratory): %s",
                    dd_pct, threshold, len(disabled_entries), disabled_entries,
                )
