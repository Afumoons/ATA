from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
import re
from typing import Dict, List, Optional

from logging_utils import get_logger

logger = get_logger(__name__)

STATS_PATH = Path(__file__).resolve().parent / "strategy_live_stats.json"

# Rolling window size — exported so scheduler/main.py can import it directly
MAX_RECENT_TRADES = 30

# MT5 comment prefix set by execution/engine.py
_COMMENT_PREFIX = "clio-auto-"
_MANUAL_PREFIX = "manual_"
_SYMBOL_SANITIZE_RE = re.compile(r"[^A-Z0-9]+")

# Cache: truncated_name (20 chars) → full strategy name
# Rebuilt from disk on every load_all_strategy_stats() call.
_NAME_MAP: Dict[str, str] = {}


@dataclass
class StrategyLiveStats:
    name: str
    total_pnl: float = 0.0
    num_trades: int = 0
    last_update: str = ""
    recent_pnls: List[float] = field(default_factory=list)

    @property
    def avg_pnl(self) -> float:
        return self.total_pnl / self.num_trades if self.num_trades > 0 else 0.0

    @property
    def recent_avg_pnl(self) -> float:
        return sum(self.recent_pnls) / len(self.recent_pnls) if self.recent_pnls else 0.0


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _truncated_name(full_name: str) -> str:
    """20-char truncated name as stored in MT5 deal comment."""
    return full_name[:20]


def is_manual_strategy_bucket(strategy_name: Optional[str]) -> bool:
    return bool(strategy_name) and str(strategy_name).startswith(_MANUAL_PREFIX)


def should_ignore_for_engine_governance(strategy_name: Optional[str]) -> bool:
    return is_manual_strategy_bucket(strategy_name)


def manual_bucket_name(symbol: Optional[str], *, unmatched: bool = True) -> str:
    raw_symbol = str(symbol or "unknown").upper().strip()
    clean_symbol = _SYMBOL_SANITIZE_RE.sub("", raw_symbol) or "UNKNOWN"
    prefix = "manual_unmatched" if unmatched else "manual"
    return f"{prefix}_{clean_symbol}"


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

def load_all_strategy_stats() -> Dict[str, StrategyLiveStats]:
    """Load per-strategy live stats from disk.

    Keys are full strategy names. Returns empty dict on missing/corrupt file.
    Also rebuilds the truncated-to-full name map used by register_strategy_pnl.

    Supports both storage formats:
    - Old: {"strategies": {name: {...}}}
    - Flat: {name: {...}}
    - Old key alias: "realized_pnl" treated as "total_pnl"
    """
    global _NAME_MAP

    if not STATS_PATH.exists():
        _NAME_MAP = {}
        try:
            save_all_strategy_stats({})
            logger.info("Bootstrapped missing strategy_live_stats.json at %s", STATS_PATH)
        except Exception:
            logger.exception("Failed to bootstrap strategy_live_stats.json")
        return {}

    try:
        with STATS_PATH.open("r", encoding="utf-8") as f:
            raw = json.load(f)
    except Exception:
        logger.exception("Failed to load strategy_live_stats")
        _NAME_MAP = {}
        return {}

    # Support both {"strategies": {...}} wrapper and flat {name: {...}}
    if isinstance(raw, dict) and "strategies" in raw:
        strategies_data = raw["strategies"]
    else:
        strategies_data = raw

    out: Dict[str, StrategyLiveStats] = {}
    for name, data in strategies_data.items():
        if not isinstance(data, dict):
            continue
        try:
            # Backward compat: old key "realized_pnl" → "total_pnl"
            total_pnl = float(
                data.get("total_pnl", data.get("realized_pnl", 0.0)) or 0.0
            )
            recent = data.get("recent_pnls") or []
            if not isinstance(recent, list):
                recent = []
            out[name] = StrategyLiveStats(
                name=name,
                total_pnl=total_pnl,
                num_trades=int(data.get("num_trades", 0) or 0),
                last_update=str(data.get("last_update", "") or ""),
                recent_pnls=[float(x) for x in recent],
            )
        except Exception:
            logger.exception("Failed to parse StrategyLiveStats for %s", name)

    _NAME_MAP = {_truncated_name(n): n for n in out}
    return out


def save_all_strategy_stats(stats: Dict[str, StrategyLiveStats]) -> None:
    """Persist stats atomically — crash-safe via temp file + rename."""
    try:
        payload = {
            "strategies": {
                name: {
                    "total_pnl": s.total_pnl,
                    "num_trades": s.num_trades,
                    "last_update": s.last_update,
                    "recent_pnls": s.recent_pnls,
                }
                for name, s in stats.items()
            }
        }
        data = json.dumps(payload, indent=2)
        fd, tmp_path = tempfile.mkstemp(
            dir=STATS_PATH.parent,
            prefix=".strategy_stats_",
            suffix=".tmp",
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(data)
            os.replace(tmp_path, STATS_PATH)
        except Exception:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise
    except Exception:
        logger.exception("Failed to save strategy_live_stats")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def register_strategy_pnl(
    strategy_name: str,
    pnl: float,
    full_name: Optional[str] = None,
) -> None:
    """Update live stats for a strategy after a closed MT5 deal.

    Parameters
    ----------
    strategy_name : str
        Name as extracted from MT5 deal comment — may be truncated to 20 chars
        (execution/engine.py sets comment = "clio-auto-{name[:20]}").
    pnl : float
        Realized PnL of the closed deal.
    full_name : str, optional
        Canonical full name. If None, resolved via _NAME_MAP cache.
        Falls back to strategy_name if unresolvable.
    """
    stats = load_all_strategy_stats()  # rebuilds _NAME_MAP as side effect

    if full_name is None:
        full_name = _NAME_MAP.get(strategy_name, strategy_name)

    rec = stats.get(full_name) or StrategyLiveStats(name=full_name)
    rec.total_pnl += float(pnl)
    rec.num_trades += 1
    rec.last_update = _now_iso()

    rec.recent_pnls.append(float(pnl))
    if len(rec.recent_pnls) > MAX_RECENT_TRADES:
        rec.recent_pnls = rec.recent_pnls[-MAX_RECENT_TRADES:]

    stats[full_name] = rec
    _NAME_MAP[_truncated_name(full_name)] = full_name  # keep map in sync

    save_all_strategy_stats(stats)
    logger.info(
        "StrategyLiveStats: %s trades=%d total_pnl=%.2f "
        "avg_pnl=%.2f recent_avg_pnl=%.2f (n_recent=%d)",
        full_name,
        rec.num_trades,
        rec.total_pnl,
        rec.avg_pnl,
        rec.recent_avg_pnl,
        len(rec.recent_pnls),
    )


def register_manual_bucket_pnl(
    *,
    symbol: Optional[str],
    pnl: float,
    unmatched: bool = True,
    full_name: Optional[str] = None,
) -> str:
    bucket_name = full_name or manual_bucket_name(symbol, unmatched=unmatched)
    register_strategy_pnl(strategy_name=bucket_name, pnl=pnl, full_name=bucket_name)
    return bucket_name
