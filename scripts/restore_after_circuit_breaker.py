from __future__ import annotations

"""Restore disabled live-tier strategies after a circuit-breaker event.

Intent:
- do NOT blindly restore everything to active
- restore previously live strategies to exploratory first
- keep clearly weak entries disabled
- preserve auditability with a backup + summary log

Run from repo root:

    python -m autonomous_trading_ai.scripts.restore_after_circuit_breaker
"""

import json
import shutil
from datetime import datetime

from autonomous_trading_ai.logging_utils import get_logger
from autonomous_trading_ai.strategies.pool import load_pool, save_pool, POOL_STATE_PATH, summarize_status_counts

logger = get_logger(__name__)

MIN_WF_SHARPE_RESTORE = 0.18
MAX_DD_RESTORE = 25.0
MIN_TRADES_RESTORE = 30
MIN_MC_P5_RESTORE = 0.0


def _get_stat(rec, key: str, default: float = 0.0) -> float:
    try:
        return float((rec.stats or {}).get(key, default) or default)
    except Exception:
        return default


def _eligible_for_exploratory_restore(rec) -> bool:
    stats = rec.stats or {}
    if not stats:
        return False
    if not stats.get("circuit_breaker_previous_status"):
        return False

    wf = _get_stat(rec, "wf_overall_sharpe")
    dd = abs(_get_stat(rec, "max_drawdown_pct"))
    num_trades = _get_stat(rec, "num_trades")
    mc_p5 = _get_stat(rec, "mc_final_pnl_p5")

    return (
        wf >= MIN_WF_SHARPE_RESTORE
        and dd <= MAX_DD_RESTORE
        and num_trades >= MIN_TRADES_RESTORE
        and mc_p5 > MIN_MC_P5_RESTORE
    )


def main() -> None:
    pool = load_pool()
    if not pool.strategies:
        logger.warning("Pool is empty; nothing to restore")
        return

    ts = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    backup_path = POOL_STATE_PATH.with_name(f"pool_state.pre_restore-{ts}.json")
    shutil.copy2(POOL_STATE_PATH, backup_path)

    counts_before = summarize_status_counts(pool.strategies)
    restored = []
    downgraded_to_candidate = []

    for rec in pool.strategies.values():
        stats = rec.stats or {}
        prev_status = str(stats.get("circuit_breaker_previous_status") or "")
        if rec.status != "disabled" or prev_status not in {"active", "exploratory"}:
            continue

        if _eligible_for_exploratory_restore(rec):
            rec.status = "exploratory"
            stats["recovered_after_circuit_breaker_at"] = datetime.utcnow().isoformat() + "Z"
            stats["recovery_path"] = "restore_to_exploratory"
            restored.append(rec.name)
        else:
            rec.status = "candidate"
            stats["recovered_after_circuit_breaker_at"] = datetime.utcnow().isoformat() + "Z"
            stats["recovery_path"] = "restore_to_candidate"
            downgraded_to_candidate.append(rec.name)

    save_pool(pool)
    counts_after = summarize_status_counts(pool.strategies)
    summary = {
        "backup": str(backup_path),
        "before": counts_before,
        "after": counts_after,
        "restored_to_exploratory": restored[:50],
        "restored_to_candidate": downgraded_to_candidate[:50],
        "restored_count": len(restored),
        "candidate_count": len(downgraded_to_candidate),
    }
    logger.info("Restore-after-circuit-breaker summary: %s", json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
