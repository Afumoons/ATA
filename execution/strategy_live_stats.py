from __future__ import annotations

import json
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List

from autonomous_trading_ai.logging_utils import get_logger

logger = get_logger(__name__)

STATS_PATH = Path(__file__).resolve().parent / "strategy_live_stats.json"
MAX_RECENT_TRADES = 30  # rolling window size for recent PnL


@dataclass
class StrategyLiveStats:
    name: str
    total_pnl: float = 0.0
    num_trades: int = 0
    last_update: str = ""  # ISO-8601 UTC
    recent_pnls: List[float] = field(default_factory=list)

    @property
    def avg_pnl(self) -> float:
        return self.total_pnl / self.num_trades if self.num_trades > 0 else 0.0

    @property
    def recent_avg_pnl(self) -> float:
        if not self.recent_pnls:
            return 0.0
        return sum(self.recent_pnls) / len(self.recent_pnls)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_all_strategy_stats() -> Dict[str, StrategyLiveStats]:
    """Load live stats for all strategies from disk.

    If the file does not exist or is invalid, returns an empty dict.
    """
    if not STATS_PATH.exists():
        return {}
    try:
        with STATS_PATH.open("r", encoding="utf-8") as f:
            raw = json.load(f)
    except Exception as e:
        logger.exception("Failed to load strategy_live_stats: %s", e)
        return {}

    out: Dict[str, StrategyLiveStats] = {}
    for name, data in raw.get("strategies", {}).items():
        try:
            # Backward compatibility: older files may not have recent_pnls
            if "recent_pnls" not in data:
                data["recent_pnls"] = []
            out[name] = StrategyLiveStats(name=name, **{k: v for k, v in data.items() if k != "name"})
        except Exception:
            logger.exception("Failed to parse StrategyLiveStats for %s", name)
    return out


def save_all_strategy_stats(stats: Dict[str, StrategyLiveStats]) -> None:
    try:
        payload = {"strategies": {name: asdict(s) for name, s in stats.items()}}
        with STATS_PATH.open("w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
    except Exception as e:
        logger.exception("Failed to save strategy_live_stats: %s", e)


def register_strategy_pnl(strategy_name: str, pnl: float) -> None:
    """Update live stats for a single strategy after a closed deal.

    This uses the strategy name encoded in the MT5 deal comment
    (see execution.engine.execute_trade).
    """
    stats = load_all_strategy_stats()
    rec = stats.get(strategy_name) or StrategyLiveStats(name=strategy_name)
    rec.total_pnl += float(pnl)
    rec.num_trades += 1
    rec.last_update = _now_iso()

    # Maintain rolling window of recent PnLs
    rec.recent_pnls.append(float(pnl))
    if len(rec.recent_pnls) > MAX_RECENT_TRADES:
        rec.recent_pnls = rec.recent_pnls[-MAX_RECENT_TRADES:]

    stats[strategy_name] = rec
    save_all_strategy_stats(stats)
    logger.info(
        "StrategyLiveStats: %s trades=%d total_pnl=%.2f avg_pnl=%.2f recent_avg_pnl=%.2f (n_recent=%d)",
        strategy_name,
        rec.num_trades,
        rec.total_pnl,
        rec.avg_pnl,
        rec.recent_avg_pnl,
        len(rec.recent_pnls),
    )
