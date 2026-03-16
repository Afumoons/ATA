from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from autonomous_trading_ai.logging_utils import get_logger

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
    """Load daily state from disk, resetting when the date changes.

    If the file does not exist or is invalid, a new state is created with
    the provided `current_equity` as the starting equity.
    """
    today = datetime.now(timezone.utc).date().isoformat()
    if LIVE_STATE_PATH.exists():
        try:
            with LIVE_STATE_PATH.open("r", encoding="utf-8") as f:
                data = json.load(f)
            state = DailyState(**data)
            if state.date != today:
                logger.info("DailyState: new day detected (%s -> %s), resetting", state.date, today)
                state = DailyState.new(current_equity, date=today)
            return state
        except Exception as e:
            logger.exception("Failed to load DailyState, resetting: %s", e)
            return DailyState.new(current_equity, date=today)
    return DailyState.new(current_equity, date=today)


def save_daily_state(state: DailyState) -> None:
    try:
        with LIVE_STATE_PATH.open("w", encoding="utf-8") as f:
            json.dump(asdict(state), f, indent=2)
    except Exception as e:
        logger.exception("Failed to save DailyState: %s", e)


def register_trade_pnl(pnl: float, current_equity: float) -> DailyState:
    """Update daily state after a trade has been closed.

    This increments trades_today and recomputes daily PnL / return.
    """
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


def can_open_new_trade(current_equity: float, max_dd_pct: float, max_trades: int, enabled: bool) -> bool:
    """Check whether new trades are allowed under daily limits.

    If `enabled` is False, always returns True.
    """
    if not enabled:
        return True

    state = load_daily_state(current_equity=current_equity)
    if state.locked_for_day:
        logger.warning("DailyState: trading locked for the day (date=%s)", state.date)
        return False

    if state.equity_start > 0:
        dd_pct = 100.0 * (state.equity_start - state.equity_current) / state.equity_start
    else:
        dd_pct = 0.0

    if dd_pct >= max_dd_pct:
        state.locked_for_day = True
        save_daily_state(state)
        logger.warning(
            "DailyState: max daily DD reached (%.2f%% >= %.2f%%), locking for day %s",
            dd_pct,
            max_dd_pct,
            state.date,
        )
        return False

    if state.trades_today >= max_trades:
        state.locked_for_day = True
        save_daily_state(state)
        logger.warning(
            "DailyState: max trades per day reached (%d >= %d), locking for day %s",
            state.trades_today,
            max_trades,
            state.date,
        )
        return False

    return True
