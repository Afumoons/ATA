from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Iterable, Any

import MetaTrader5 as mt5

from ..logging_utils import get_logger

logger = get_logger(__name__)

LIVE_STATE_PATH = Path(__file__).resolve().parent / "live_state.json"


@dataclass
class DailyState:
    date: str
    equity_start: float
    equity_current: float
    daily_pnl: float
    daily_return_pct: float
    trades_today: int
    locked_for_day: bool

    @classmethod
    def new(cls, equity: float, date: Optional[str] = None) -> "DailyState":
        if date is None:
            date = datetime.now(timezone.utc).date().isoformat()
        return cls(
            date=date,
            equity_start=equity,
            equity_current=equity,
            daily_pnl=0.0,
            daily_return_pct=0.0,
            trades_today=0,
            locked_for_day=False,
        )


def load_daily_state(current_equity: float) -> DailyState:
    """Load daily state from disk, resetting when the date changes."""
    today = datetime.now(timezone.utc).date().isoformat()

    if LIVE_STATE_PATH.exists():
        try:
            with LIVE_STATE_PATH.open("r", encoding="utf-8") as f:
                data = json.load(f)
            state = DailyState(**data)
            if state.date != today:
                logger.info(
                    "DailyState: new day detected (%s -> %s), resetting",
                    state.date,
                    today,
                )
                state = DailyState.new(current_equity, date=today)
            return state
        except Exception:
            logger.exception("Failed to load DailyState, resetting")
            return DailyState.new(current_equity, date=today)

    return DailyState.new(current_equity, date=today)


def save_daily_state(state: DailyState) -> None:
    """Persist DailyState atomically — crash-safe via temp file + rename."""
    try:
        data = json.dumps(asdict(state), indent=2)
        fd, tmp_path = tempfile.mkstemp(
            dir=LIVE_STATE_PATH.parent,
            prefix=".live_state_",
            suffix=".tmp",
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(data)
            os.replace(tmp_path, LIVE_STATE_PATH)
        except Exception:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise
    except Exception:
        logger.exception("Failed to save DailyState")


def register_trade_pnl(pnl: float, current_equity: float) -> DailyState:
    """Update daily state after a trade has been closed."""
    state = load_daily_state(current_equity=current_equity)
    state.trades_today += 1
    state.equity_current = current_equity
    state.daily_pnl = state.equity_current - state.equity_start
    if state.equity_start > 0:
        state.daily_return_pct = 100.0 * state.daily_pnl / state.equity_start
    save_daily_state(state)
    logger.info(
        "DailyState: date=%s trades_today=%d daily_pnl=%.2f daily_return_pct=%.2f%%",
        state.date,
        state.trades_today,
        state.daily_pnl,
        state.daily_return_pct,
    )
    return state


def strategy_has_open_position(
    strategy_name: str,
    symbol: str,
    timeframe: str,
    positions: Optional[Iterable[Any]] = None,
) -> bool:
    """Return True when MT5 already has an open position for this strategy slot.

    Slot identity is strategy + symbol + timeframe. We prefer the persisted
    ticket→strategy map (exact match), and fall back to parsing the MT5 comment
    format used by execution.engine (`{timeframe}{symbol}{uid4}`) so the guard
    still works across process restarts when possible.
    """
    if positions is None:
        try:
            positions = mt5.positions_get(symbol=symbol)
        except Exception:
            logger.exception(
                "strategy_has_open_position: mt5.positions_get failed for %s %s %s",
                strategy_name,
                symbol,
                timeframe,
            )
            return False

        if positions is None:
            logger.warning(
                "strategy_has_open_position: positions_get returned None for %s %s",
                symbol,
                timeframe,
            )
            return False

    try:
        from .signals import get_strategy_for_ticket  # avoid circular import
    except Exception:
        logger.exception("strategy_has_open_position: failed to import ticket map helper")
        get_strategy_for_ticket = None

    uid4 = strategy_name.split("_")[-1][:4] if "_" in strategy_name else strategy_name[-4:]
    tf_prefix = "".join(c for c in timeframe if c.isalnum())
    sym_prefix = "".join(c for c in symbol if c.isalnum())
    comment_prefix = f"{tf_prefix}{sym_prefix}{uid4}"

    for pos in positions:
        ticket = getattr(pos, "ticket", None)
        if get_strategy_for_ticket is not None and ticket is not None:
            mapped = get_strategy_for_ticket(int(ticket))
            if mapped == strategy_name:
                return True

        comment = str(getattr(pos, "comment", "") or "")
        pos_symbol = str(getattr(pos, "symbol", "") or "")
        if pos_symbol == symbol and comment.startswith(comment_prefix):
            return True

    return False


def can_open_new_trade(
    current_equity: float,
    max_dd_pct: float,
    max_trades: int,
    enabled: bool,
) -> bool:
    """Check whether new trades are allowed under daily limits.

    If `enabled` is False, always returns True.
    Uses live current_equity for DD check — not stale equity from last closed trade.
    """
    if not enabled:
        return True

    state = load_daily_state(current_equity=current_equity)

    if state.locked_for_day:
        logger.warning("DailyState: trading locked for the day (date=%s)", state.date)
        return False

    state.equity_current = current_equity
    dd_pct = (
        100.0 * (state.equity_start - state.equity_current) / state.equity_start
        if state.equity_start > 0
        else 0.0
    )

    if dd_pct >= max_dd_pct:
        state.locked_for_day = True
        save_daily_state(state)
        logger.warning(
            "DailyState: max daily DD reached (%.2f%% >= %.2f%%), "
            "locking for day %s (start=%.2f now=%.2f)",
            dd_pct, max_dd_pct, state.date,
            state.equity_start, state.equity_current,
        )
        return False

    if state.trades_today >= max_trades:
        state.locked_for_day = True
        save_daily_state(state)
        logger.warning(
            "DailyState: max trades/day reached (%d >= %d), locking for day %s",
            state.trades_today, max_trades, state.date,
        )
        return False

    return True