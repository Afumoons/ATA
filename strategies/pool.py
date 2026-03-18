from __future__ import annotations

import json
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Dict, List, Optional, Any

from ..logging_utils import get_logger
from .base import StrategyDefinition

logger = get_logger(__name__)

POOL_DIR = Path(__file__).resolve().parent
POOL_STATE_PATH = POOL_DIR / "pool_state.json"

# Statuses that are never pruned regardless of pool size
_LIVE_STATUSES = {"active", "exploratory"}

# Maximum number of non-live strategies (candidate/disabled/retired) kept
# in the pool. Oldest by score are pruned first when this limit is exceeded.
# Without pruning, pool_state.json grows unboundedly: 20 strategies/cycle ×
# research every 30 min = 1000 strategies in ~25 hours.
_MAX_INACTIVE_STRATEGIES = 200


@dataclass
class StrategyRecord:
    name: str
    symbol: str
    timeframe: str
    status: str  # "candidate", "active", "exploratory", "disabled", "retired"
    score: float
    # Dict[str, Any] — stats contains nested structures (strategy_explain,
    # regime_pnl, etc.) not just floats. The previous Dict[str, float] hint
    # was incorrect and caused type checker false positives.
    stats: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "StrategyRecord":
        """Construct from dict with graceful handling of missing/extra fields.

        Using StrategyRecord(**rec) directly in from_dict() will raise
        TypeError if pool_state.json has missing or extra fields — e.g. after
        adding a new field to the dataclass. This method is defensive.
        """
        return cls(
            name=data["name"],
            symbol=data["symbol"],
            timeframe=data["timeframe"],
            status=data.get("status", "candidate"),
            score=float(data.get("score", 0.0)),
            stats=data.get("stats", {}),
        )


@dataclass
class StrategyPool:
    strategies: Dict[str, StrategyRecord] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Dict[str, Any]]:
        return {name: rec.to_dict() for name, rec in self.strategies.items()}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "StrategyPool":
        """Deserialize pool with per-record error isolation.

        A single corrupt record no longer crashes the entire scheduler —
        it is skipped with a warning, allowing the rest of the pool to load.
        """
        strategies: Dict[str, StrategyRecord] = {}
        for name, rec in data.items():
            try:
                strategies[name] = StrategyRecord.from_dict(rec)
            except Exception as e:
                logger.warning(
                    "Pool: skipping corrupt record '%s': %s", name, e
                )
        return cls(strategies=strategies)

    def upsert_strategy(
        self,
        strategy: StrategyDefinition,
        stats: Dict[str, Any],
        score: float,
        status: str = "candidate",
    ) -> None:
        rec = StrategyRecord(
            name=strategy.name,
            symbol=strategy.symbol,
            timeframe=strategy.timeframe,
            status=status,
            score=score,
            stats=stats,
        )
        self.strategies[strategy.name] = rec
        logger.info(
            "Pool upsert: %s status=%s score=%.3f", strategy.name, status, score
        )

    def set_status(self, name: str, status: str) -> None:
        rec = self.strategies.get(name)
        if not rec:
            logger.warning("Pool set_status: strategy %s not found", name)
            return
        rec.status = status
        logger.info("Pool set_status: %s -> %s", name, status)

    def top_strategies(
        self,
        status_filter: Optional[str] = "candidate",
        limit: int = 10,
    ) -> List[StrategyRecord]:
        recs = list(self.strategies.values())
        if status_filter:
            recs = [r for r in recs if r.status == status_filter]
        recs.sort(key=lambda r: r.score, reverse=True)
        return recs[:limit]

    def prune(self, max_inactive: int = _MAX_INACTIVE_STRATEGIES) -> int:
        """Remove lowest-scoring inactive strategies beyond the size cap.

        Active and exploratory strategies are never pruned. Returns the
        number of records removed.

        Call this at the end of each research cycle (before save_pool) to
        keep pool_state.json from growing without bound.
        """
        live = {n: r for n, r in self.strategies.items() if r.status in _LIVE_STATUSES}
        inactive = {n: r for n, r in self.strategies.items() if r.status not in _LIVE_STATUSES}

        if len(inactive) <= max_inactive:
            return 0

        # Sort inactive by score descending — keep the best, prune the rest
        sorted_inactive = sorted(inactive.items(), key=lambda kv: kv[1].score, reverse=True)
        keep = dict(sorted_inactive[:max_inactive])
        pruned_names = set(inactive.keys()) - set(keep.keys())

        self.strategies = {**live, **keep}

        logger.info(
            "Pool pruned %d inactive strategies (kept %d inactive + %d live = %d total)",
            len(pruned_names),
            len(keep),
            len(live),
            len(self.strategies),
        )
        return len(pruned_names)


def load_pool() -> StrategyPool:
    if not POOL_STATE_PATH.exists():
        logger.info("Pool: starting new empty pool")
        return StrategyPool(strategies={})
    try:
        with POOL_STATE_PATH.open("r", encoding="utf-8") as f:
            data = json.load(f)
        pool = StrategyPool.from_dict(data)
        logger.info("Pool loaded: %d strategies", len(pool.strategies))
        return pool
    except json.JSONDecodeError as e:
        logger.error(
            "Pool: pool_state.json is corrupt (%s) — starting fresh empty pool", e
        )
        return StrategyPool(strategies={})
    except Exception as e:
        logger.exception("Pool: unexpected error loading pool — starting fresh: %s", e)
        return StrategyPool(strategies={})


def save_pool(pool: StrategyPool) -> None:
    with POOL_STATE_PATH.open("w", encoding="utf-8") as f:
        json.dump(pool.to_dict(), f, indent=2)
    logger.info("Pool saved: %d strategies", len(pool.strategies))