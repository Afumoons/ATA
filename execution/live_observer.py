from __future__ import annotations

"""Live observability helpers for autonomous_trading_ai.

This module is **read-only** with respect to trading logic:
- It does NOT place or close any orders.
- It only reads from MT5 and writes summarized JSON artifacts under
  `autonomous_trading_ai/execution/` for monitoring and scripts.

Artifacts produced:

- `open_trades.json`
    Snapshot of all currently open MT5 positions in a normalized format.

- `strategy_live_stats.json`
    Aggregated realized PnL statistics per strategy, suitable for
    `scripts/print_live_summary.py` and other monitoring tools.

Both writers are crash-safe via temp file + atomic rename, following the
pattern used in `live_state_utils.py`.
"""

import json
import os
import tempfile
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .live_state_utils import logger  # reuse execution logger

BASE_DIR = Path(__file__).resolve().parent
OPEN_TRADES_PATH = BASE_DIR / "open_trades.json"
STRATEGY_LIVE_STATS_PATH = BASE_DIR / "strategy_live_stats.json"


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------


def _safe_write_json(path: Path, data: Any) -> None:
    """Crash-safe JSON writer (temp file + atomic rename).

    Mirrors the approach used in `live_state_utils.save_daily_state`.
    """

    try:
        payload = json.dumps(data, indent=2, ensure_ascii=False)
        fd, tmp_path = tempfile.mkstemp(
            dir=path.parent,
            prefix=f".{path.stem}_",
            suffix=".tmp",
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(payload)
            os.replace(tmp_path, path)
        except Exception:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise
    except Exception:
        logger.exception("Failed to write JSON to %s", path)


def _load_json(path: Path) -> Any:
    if not path.exists():
        return None
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        logger.exception("Failed to load JSON from %s", path)
        return None


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Open trades snapshot
# ---------------------------------------------------------------------------


@dataclass
class OpenTradeSnapshot:
    ticket: int
    symbol: str
    strategy_name: Optional[str]
    direction: str  # "buy" or "sell"
    volume: float
    open_time: str
    open_price: float
    sl: float
    tp: float
    magic: int
    comment: str
    floating_pnl: float
    swap: float
    commission: float
    last_update: str


def _infer_strategy_from_comment(comment: str) -> Optional[str]:
    """Best-effort mapping from MT5 comment back to a strategy key.

    `engine.execute_trade` currently uses a truncated, alnum-only strategy
    name for the MT5 comment:

        comment = "".join(c for c in strategy_name[:15] if c.isalnum())

    We preserve this value as `strategy_name` in the snapshot.
    If you later introduce a more structured comment format
    (e.g. `"strat=xyz;..."`), this function is the place to decode it.
    """

    if not comment:
        return None
    return comment.strip() or None


def snapshot_open_trades() -> None:
    """Snapshot all open MT5 positions into `open_trades.json`.

    This function is **non-invasive**:
    - It only reads `mt5.positions_get()` and `mt5.account_info()`.
    - On MT5/API error, it logs a warning and leaves the previous
      `open_trades.json` untouched.

    Safe to call frequently (e.g. from a scheduler loop or a dedicated
    monitoring cron/script).
    """

    try:
        import MetaTrader5 as mt5  # type: ignore
    except ImportError:
        logger.warning("snapshot_open_trades: MetaTrader5 not installed — skipping")
        return

    try:
        positions = mt5.positions_get()
    except Exception:
        logger.exception("snapshot_open_trades: mt5.positions_get() failed")
        return

    if positions is None:
        logger.warning("snapshot_open_trades: positions_get() returned None")
        return

    now_iso = _now_utc().isoformat()
    snapshots: List[Dict[str, Any]] = []

    for pos in positions:
        try:
            direction = (
                "buy" if pos.type == mt5.POSITION_TYPE_BUY else "sell"
            )
            open_time = datetime.fromtimestamp(pos.time, tz=timezone.utc)
            snap = OpenTradeSnapshot(
                ticket=int(pos.ticket),
                symbol=str(pos.symbol),
                strategy_name=_infer_strategy_from_comment(str(pos.comment)),
                direction=direction,
                volume=float(pos.volume),
                open_time=open_time.isoformat(),
                open_price=float(pos.price_open),
                sl=float(pos.sl),
                tp=float(pos.tp),
                magic=int(pos.magic),
                comment=str(pos.comment),
                floating_pnl=float(pos.profit),
                swap=float(getattr(pos, "swap", 0.0) or 0.0),
                commission=float(getattr(pos, "commission", 0.0) or 0.0),
                last_update=now_iso,
            )
            snapshots.append(asdict(snap))
        except Exception:
            logger.exception("snapshot_open_trades: failed to serialize position")

    _safe_write_json(OPEN_TRADES_PATH, snapshots)
    logger.info("snapshot_open_trades: wrote %d open positions", len(snapshots))


# ---------------------------------------------------------------------------
# Strategy live stats (realized PnL)
# ---------------------------------------------------------------------------


@dataclass
class StrategyLiveStats:
    symbol: str
    timeframe: Optional[str]
    total_pnl: float = 0.0
    num_trades: int = 0
    recent_pnls: Optional[List[float]] = None
    last_updated: Optional[str] = None

    def record_trade(self, pnl: float, max_recent: int = 20) -> None:
        self.total_pnl += pnl
        self.num_trades += 1
        if self.recent_pnls is None:
            self.recent_pnls = []
        self.recent_pnls.append(pnl)
        if len(self.recent_pnls) > max_recent:
            self.recent_pnls = self.recent_pnls[-max_recent:]
        self.last_updated = _now_utc().isoformat()


def _load_strategy_live_stats() -> Dict[str, Any]:
    data = _load_json(STRATEGY_LIVE_STATS_PATH)
    if not data or not isinstance(data, dict):
        return {"strategies": {}}
    if "strategies" not in data or not isinstance(data["strategies"], dict):
        data["strategies"] = {}
    return data


def _save_strategy_live_stats(data: Dict[str, Any]) -> None:
    if "strategies" not in data:
        data["strategies"] = {}
    _safe_write_json(STRATEGY_LIVE_STATS_PATH, data)


def record_closed_trade(
    strategy_key: str,
    symbol: str,
    timeframe: Optional[str],
    pnl: float,
    max_recent: int = 20,
) -> None:
    """Update `strategy_live_stats.json` after a **single closed trade**.

    This is the lowest-level API you can call from execution/bridge code
    whenever a trade result is known.

    Schema is aligned with `scripts/print_live_summary.py` which expects:

        {
          "strategies": {
             "name": {
                "total_pnl": float,
                "num_trades": int,
                "recent_pnls": [float, ...],
                ...
             }
          }
        }
    """

    data = _load_strategy_live_stats()
    strategies: Dict[str, Any] = data["strategies"]

    rec_dict = strategies.get(strategy_key)
    if rec_dict is None:
        rec = StrategyLiveStats(symbol=symbol, timeframe=timeframe)
    else:
        rec = StrategyLiveStats(
            symbol=rec_dict.get("symbol", symbol),
            timeframe=rec_dict.get("timeframe", timeframe),
            total_pnl=float(rec_dict.get("total_pnl", 0.0) or 0.0),
            num_trades=int(rec_dict.get("num_trades", 0) or 0),
            recent_pnls=list(rec_dict.get("recent_pnls", []) or []),
            last_updated=rec_dict.get("last_updated"),
        )

    rec.record_trade(pnl=pnl, max_recent=max_recent)
    strategies[strategy_key] = asdict(rec)
    data["strategies"] = strategies
    _save_strategy_live_stats(data)


def rebuild_stats_from_history(
    days: int = 7,
    comment_prefix: Optional[str] = None,
) -> None:
    """Rebuild `strategy_live_stats.json` from MT5 deal history.

    This is an **offline** operation that:

    - Queries MT5 deals over the last `days` days.
    - Groups realized PnL by `strategy_key` inferred from `deal.comment`.
    - Overwrites `strategy_live_stats.json` with aggregated results.

    `comment_prefix` can be used if you only want to include trades with
    comments starting with e.g. "clio" to avoid mixing manual trades.
    """

    try:
        import MetaTrader5 as mt5  # type: ignore
    except ImportError:
        logger.warning("rebuild_stats_from_history: MetaTrader5 not installed — skipping")
        return

    now = _now_utc()
    frm = now - timedelta(days=days)

    try:
        deals = mt5.history_deals_get(frm, now)
    except Exception:
        logger.exception("rebuild_stats_from_history: mt5.history_deals_get failed")
        return

    if deals is None:
        logger.warning("rebuild_stats_from_history: history_deals_get returned None")
        return

    logger.info("rebuild_stats_from_history: processing %d deals", len(deals))

    # In this first pass we simply aggregate by comment (strategy key).
    aggregation: Dict[str, StrategyLiveStats] = {}

    for d in deals:
        try:
            comment = str(d.comment or "").strip()
            if comment_prefix and not comment.startswith(comment_prefix):
                continue

            strategy_key = comment or "_unknown_"
            pnl = float(d.profit or 0.0)
            symbol = str(d.symbol or "")

            # We don't have timeframe from MT5 deal directly; set None for now.
            current = aggregation.get(strategy_key)
            if current is None:
                current = StrategyLiveStats(symbol=symbol, timeframe=None)
                aggregation[strategy_key] = current

            current.record_trade(pnl=pnl)
        except Exception:
            logger.exception("rebuild_stats_from_history: failed to process deal")

    # Serialize to JSON structure expected by print_live_summary
    payload = {
        "generated_at": now.isoformat(),
        "window_days": days,
        "strategies": {k: asdict(v) for k, v in aggregation.items()},
    }

    _safe_write_json(STRATEGY_LIVE_STATS_PATH, payload)
    logger.info(
        "rebuild_stats_from_history: wrote stats for %d strategies to %s",
        len(aggregation),
        STRATEGY_LIVE_STATS_PATH,
    )
