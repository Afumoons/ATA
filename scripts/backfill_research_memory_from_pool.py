from __future__ import annotations

from pathlib import Path

from autonomous_trading_ai.vector_memory.research_memory import ResearchMemory
from autonomous_trading_ai.strategies.pool import load_pool
from autonomous_trading_ai.logging_utils import get_logger

logger = get_logger(__name__)


def main() -> None:
    pool = load_pool()
    memory = ResearchMemory()

    count = 0
    for rec in pool.strategies.values():
        stats = rec.stats or {}
        if not stats:
            continue
        try:
            memory.store_strategy_result(
                strategy_name=rec.name,
                symbol=rec.symbol,
                timeframe=rec.timeframe,
                stats=stats,
            )
            count += 1
        except Exception as e:
            logger.exception("Backfill failed for %s: %s", rec.name, e)

    logger.info("Backfill complete: wrote %d strategies into ResearchMemory", count)
    print("BACKFILL_WRITTEN", count)


if __name__ == "__main__":
    main()
