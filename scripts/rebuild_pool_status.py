from __future__ import annotations

"""One-off script to fix status inversion in strategies/pool_state.json.

This script:
- Loads the existing StrategyPool
- Recomputes a clean status tier per strategy based on robustness metrics
- Writes back a corrected pool_state.json (with an automatic backup)

Tiers after this script:
- active      : preserved for now (only demoted if clearly terrible)
- exploratory : high quality but still "trial" level
- candidate   : acceptable but not priority
- disabled    : clearly weak or under-specified

Important:
- This is NOT the preferred recovery tool after a portfolio circuit-breaker mass disable.
- For that case, use:

    python -m autonomous_trading_ai.scripts.restore_after_circuit_breaker

Run once from repo root:

    python -m autonomous_trading_ai.scripts.rebuild_pool_status

"""

import json
import shutil
from datetime import datetime
from pathlib import Path

from autonomous_trading_ai.strategies.pool import load_pool, save_pool, POOL_STATE_PATH
from autonomous_trading_ai.logging_utils import get_logger

logger = get_logger(__name__)


# --- Thresholds (can be tuned later) ---------------------------------------

# Hard reject thresholds (go to disabled)
MIN_WF_SHARPE_DISABLED = 0.20   # below this → disabled
MAX_DRAWDOWN_DISABLED = 30.0    # above this → disabled
MIN_TRADES_DISABLED = 50        # below this → disabled (too little data)

# Candidate base thresholds
MIN_WF_SHARPE_CANDIDATE = 0.20
MAX_DRAWDOWN_CANDIDATE = 25.0
MIN_TRADES_CANDIDATE = 50

# Exploratory thresholds (strict subset of candidate)
MIN_WF_SHARPE_EXPLORATORY = 0.50
MAX_DRAWDOWN_EXPLORATORY = 20.0
MIN_TRADES_EXPLORATORY = 100


def _get_stat(rec, key: str, default: float = 0.0) -> float:
    try:
        return float((rec.stats or {}).get(key, default) or default)
    except Exception:
        return default


def _should_be_disabled(rec) -> bool:
    stats = rec.stats or {}
    wf = _get_stat(rec, "wf_overall_sharpe")
    dd = abs(_get_stat(rec, "max_drawdown_pct"))
    ret = _get_stat(rec, "return_pct")
    num_trades = _get_stat(rec, "num_trades")

    if wf < MIN_WF_SHARPE_DISABLED:
        return True
    if ret <= 0.0:
        return True
    if dd > MAX_DRAWDOWN_DISABLED:
        return True
    if num_trades < MIN_TRADES_DISABLED:
        return True

    # If we cannot read stats at all, treat as disabled to avoid
    # accidentally promoting corrupt entries.
    if not stats:
        return True

    return False


def _should_be_exploratory(rec) -> bool:
    """Return True if strategy qualifies for exploratory tier.

    This does NOT decide between exploratory vs active. Active promotion
    remains handled by the main research pipeline's _should_promote().
    """
    if _should_be_disabled(rec):
        return False

    wf = _get_stat(rec, "wf_overall_sharpe")
    dd = abs(_get_stat(rec, "max_drawdown_pct"))
    num_trades = _get_stat(rec, "num_trades")

    if wf < MIN_WF_SHARPE_EXPLORATORY:
        return False
    if dd > MAX_DRAWDOWN_EXPLORATORY:
        return False
    if num_trades < MIN_TRADES_EXPLORATORY:
        return False

    return True


def _should_be_candidate(rec) -> bool:
    if _should_be_disabled(rec):
        return False

    wf = _get_stat(rec, "wf_overall_sharpe")
    dd = abs(_get_stat(rec, "max_drawdown_pct"))
    num_trades = _get_stat(rec, "num_trades")

    if wf < MIN_WF_SHARPE_CANDIDATE:
        return False
    if dd > MAX_DRAWDOWN_CANDIDATE:
        return False
    if num_trades < MIN_TRADES_CANDIDATE:
        return False

    return True


def main() -> None:
    logger.info("Rebuild pool_status: loading pool from %s", POOL_STATE_PATH)
    pool = load_pool()

    if not pool.strategies:
        logger.warning("Pool is empty; nothing to rebuild")
        return

    # Backup existing pool_state.json
    ts = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    backup_path = POOL_STATE_PATH.with_name(f"pool_state.backup-{ts}.json")
    shutil.copy2(POOL_STATE_PATH, backup_path)
    logger.info("Backed up existing pool_state.json to %s", backup_path)

    counts_before = {"active": 0, "exploratory": 0, "candidate": 0, "disabled": 0, "other": 0}
    for rec in pool.strategies.values():
        if rec.status in counts_before:
            counts_before[rec.status] += 1
        else:
            counts_before["other"] += 1

    # Reassign statuses
    changes = 0
    for name, rec in pool.strategies.items():
        old_status = rec.status

        # Keep clearly good active entries active; we only demote if
        # they now fail even candidate-quality rules.
        if old_status == "active":
            if _should_be_disabled(rec):
                rec.status = "disabled"
            elif _should_be_candidate(rec) and not _should_be_exploratory(rec):
                # Strong but not at exploratory threshold
                rec.status = "candidate"
            # else: keep as active or exploratory depending on future logic
        else:
            if _should_be_disabled(rec):
                rec.status = "disabled"
            elif _should_be_exploratory(rec):
                rec.status = "exploratory"
            elif _should_be_candidate(rec):
                rec.status = "candidate"
            else:
                rec.status = "disabled"

        if rec.status != old_status:
            changes += 1
            logger.info(
                "Reclassify %s: %s -> %s (wf=%.3f dd=%.2f ret=%.2f trades=%.0f)",
                name,
                old_status,
                rec.status,
                _get_stat(rec, "wf_overall_sharpe"),
                abs(_get_stat(rec, "max_drawdown_pct")),
                _get_stat(rec, "return_pct"),
                _get_stat(rec, "num_trades"),
            )

    save_pool(pool)

    counts_after = {"active": 0, "exploratory": 0, "candidate": 0, "disabled": 0, "other": 0}
    for rec in pool.strategies.values():
        if rec.status in counts_after:
            counts_after[rec.status] += 1
        else:
            counts_after["other"] += 1

    summary = {
        "before": counts_before,
        "after": counts_after,
        "changed": changes,
        "backup": str(backup_path),
    }
    logger.info("Rebuild pool_status summary: %s", json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
