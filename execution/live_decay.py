from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, List, Optional

from ..logging_utils import get_logger
from ..strategies.pool import StrategyPool
from ..config import live_decay_config
from .audit_utils import append_pool_audit
from .strategy_live_stats import StrategyLiveStats, should_ignore_for_engine_governance

logger = get_logger(__name__)


@dataclass
class LiveDecaySignal:
    """Computed health snapshot for one strategy's recent live performance."""
    strategy_name: str
    current_status: str
    signal_level: str  # healthy | warning | degrade
    reason: str
    recent_count: int
    recent_sum_pnl: float
    recent_avg_pnl: float
    loss_streak: int
    negative_ratio: float
    total_trades: int


@dataclass
class LiveDecayAction:
    """Concrete governance action derived from a live-decay signal."""
    strategy_name: str
    current_status: str
    new_status: Optional[str]
    signal_level: str
    reason: str
    metrics: dict


def _loss_streak(recent_pnls: List[float]) -> int:
    streak = 0
    for pnl in reversed(recent_pnls):
        if float(pnl) < 0:
            streak += 1
        else:
            break
    return streak


def _negative_ratio(recent_pnls: List[float]) -> float:
    if not recent_pnls:
        return 0.0
    negatives = sum(1 for x in recent_pnls if float(x) < 0)
    return negatives / len(recent_pnls)


def compute_live_decay_signal(strategy_name: str, current_status: str, stats: StrategyLiveStats) -> LiveDecaySignal:
    """Classify a strategy as healthy, warning, or degrade from recent PnL."""
    if should_ignore_for_engine_governance(strategy_name):
        return LiveDecaySignal(
            strategy_name=strategy_name,
            current_status=current_status,
            signal_level="healthy",
            reason="manual_bucket_ignored",
            recent_count=0,
            recent_sum_pnl=0.0,
            recent_avg_pnl=0.0,
            loss_streak=0,
            negative_ratio=0.0,
            total_trades=int(stats.num_trades or 0),
        )

    recent = [float(x) for x in (stats.recent_pnls or [])]
    recent_count = len(recent)
    recent_sum = float(sum(recent)) if recent else 0.0
    recent_avg = float(recent_sum / recent_count) if recent_count else 0.0
    loss_streak = _loss_streak(recent)
    negative_ratio = _negative_ratio(recent)
    total_trades = int(stats.num_trades or 0)

    level = "healthy"
    reason = "insufficient_data"

    if total_trades >= live_decay_config.min_trades_for_decay and recent_count >= live_decay_config.min_recent_for_warning:
        level = "warning"
        reason = "recent_avg_negative" if recent_avg < 0 else "monitoring"

        if loss_streak >= live_decay_config.warning_loss_streak:
            level = "warning"
            reason = f"loss_streak>={live_decay_config.warning_loss_streak}"
        elif negative_ratio >= 0.70 and recent_avg < 0:
            level = "warning"
            reason = "negative_ratio_high_and_recent_avg_negative"
        elif recent_avg >= 0:
            level = "healthy"
            reason = "recent_performance_ok"

    if total_trades >= live_decay_config.min_trades_for_decay and recent_count >= live_decay_config.min_recent_for_degrade:
        if recent_avg < 0 and recent_sum < 0 and loss_streak >= live_decay_config.degrade_loss_streak:
            level = "degrade"
            reason = f"recent_avg_negative_and_loss_streak>={live_decay_config.degrade_loss_streak}"

    return LiveDecaySignal(
        strategy_name=strategy_name,
        current_status=current_status,
        signal_level=level,
        reason=reason,
        recent_count=recent_count,
        recent_sum_pnl=recent_sum,
        recent_avg_pnl=recent_avg,
        loss_streak=loss_streak,
        negative_ratio=negative_ratio,
        total_trades=total_trades,
    )


def evaluate_live_decay(pool: StrategyPool, live_stats: Dict[str, StrategyLiveStats]) -> List[LiveDecayAction]:
    """Scan active/exploratory strategies and produce decay actions if needed."""
    actions: List[LiveDecayAction] = []
    for name, rec in pool.strategies.items():
        if rec.status not in {"active", "exploratory"}:
            continue
        stats = live_stats.get(name)
        if stats is None:
            continue

        signal = compute_live_decay_signal(name, rec.status, stats)
        metrics = {
            "recent_count": signal.recent_count,
            "recent_sum_pnl": signal.recent_sum_pnl,
            "recent_avg_pnl": signal.recent_avg_pnl,
            "loss_streak": signal.loss_streak,
            "negative_ratio": signal.negative_ratio,
            "total_trades": signal.total_trades,
        }

        if signal.signal_level == "warning":
            actions.append(
                LiveDecayAction(
                    strategy_name=name,
                    current_status=rec.status,
                    new_status=None,
                    signal_level="warning",
                    reason=signal.reason,
                    metrics=metrics,
                )
            )
        elif signal.signal_level == "degrade":
            new_status = "exploratory" if rec.status == "active" else "disabled"
            actions.append(
                LiveDecayAction(
                    strategy_name=name,
                    current_status=rec.status,
                    new_status=new_status,
                    signal_level="degrade",
                    reason=signal.reason,
                    metrics=metrics,
                )
            )
    return actions


def apply_live_decay_actions(pool: StrategyPool, actions: List[LiveDecayAction]) -> int:
    """Persist live-decay metadata and apply any status demotions to the pool."""
    changed = 0
    now_iso = datetime.now(timezone.utc).isoformat()

    for action in actions:
        rec = pool.strategies.get(action.strategy_name)
        if rec is None:
            continue

        stats = rec.stats or {}
        live_decay_meta = dict(stats.get("live_decay") or {})
        live_decay_meta.update({
            "signal_level": action.signal_level,
            "reason": action.reason,
            "updated_at": now_iso,
            **action.metrics,
        })
        stats["live_decay"] = live_decay_meta
        rec.stats = stats

        if action.new_status and rec.status != action.new_status:
            old_status = rec.status
            rec.status = action.new_status
            changed += 1
            append_pool_audit({
                "event": "live_decay_degrade",
                "strategy_name": action.strategy_name,
                "old_status": old_status,
                "new_status": action.new_status,
                "reason": action.reason,
                "metrics": action.metrics,
            })
            logger.warning(
                "Live decay degrade: %s %s -> %s | reason=%s metrics=%s",
                action.strategy_name,
                old_status,
                action.new_status,
                action.reason,
                action.metrics,
            )
        else:
            append_pool_audit({
                "event": "live_decay_warning",
                "strategy_name": action.strategy_name,
                "status": rec.status,
                "reason": action.reason,
                "metrics": action.metrics,
            })
            logger.info(
                "Live decay warning: %s status=%s reason=%s metrics=%s",
                action.strategy_name,
                rec.status,
                action.reason,
                action.metrics,
            )

    return changed
