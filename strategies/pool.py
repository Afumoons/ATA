from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, List, Optional

from ..logging_utils import get_logger
from .base import StrategyDefinition

logger = get_logger(__name__)

POOL_DIR = Path(__file__).resolve().parent
POOL_STATE_PATH = POOL_DIR / "pool_state.json"


@dataclass
class StrategyRecord:
    name: str
    symbol: str
    timeframe: str
    status: str  # "candidate", "active", "disabled", "retired"
    score: float
    stats: Dict[str, float]

    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class StrategyPool:
    strategies: Dict[str, StrategyRecord]

    def to_dict(self) -> Dict[str, Dict]:
        return {name: rec.to_dict() for name, rec in self.strategies.items()}

    @classmethod
    def from_dict(cls, data: Dict[str, Dict]) -> "StrategyPool":
        strategies = {
            name: StrategyRecord(**rec) for name, rec in data.items()
        }
        return cls(strategies=strategies)

    def upsert_strategy(
        self,
        strategy: StrategyDefinition,
        stats: Dict[str, float],
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


def load_pool() -> StrategyPool:
    if not POOL_STATE_PATH.exists():
        logger.info("Pool: starting new empty pool")
        return StrategyPool(strategies={})
    with POOL_STATE_PATH.open("r", encoding="utf-8") as f:
        data = json.load(f)
    pool = StrategyPool.from_dict(data)
    logger.info("Pool loaded: %d strategies", len(pool.strategies))
    return pool


def save_pool(pool: StrategyPool) -> None:
    with POOL_STATE_PATH.open("w", encoding="utf-8") as f:
        json.dump(pool.to_dict(), f, indent=2)
    logger.info("Pool saved: %d strategies", len(pool.strategies))
