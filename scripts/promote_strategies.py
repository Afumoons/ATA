from __future__ import annotations

from autonomous_trading_ai.strategies.pool import load_pool, save_pool
from autonomous_trading_ai.logging_utils import get_logger

logger = get_logger(__name__)


def promote_top_strategies(top_n: int = 3) -> None:
    pool = load_pool()
    candidates = pool.top_strategies(status_filter="candidate", limit=top_n)
    if not candidates:
        logger.info("No candidate strategies to promote")
        return

    for rec in candidates:
        pool.set_status(rec.name, "active")
        logger.info("Promoted strategy %s to active (score=%.3f)", rec.name, rec.score)

    save_pool(pool)


def main() -> None:
    promote_top_strategies(top_n=3)


if __name__ == "__main__":
    main()
