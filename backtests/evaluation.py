from __future__ import annotations

from dataclasses import dataclass
from typing import Dict

from ..logging_utils import get_logger

logger = get_logger(__name__)


@dataclass
class EvaluationConfig:
    # Minimum quality gates for pool admission
    min_trades: int = 30
    min_sharpe: float = 0.2
    max_drawdown_pct: float = 22.0   # positive value, e.g. 22 = 22% max DD
    min_profit_factor: float = 1.12

    # Score weights
    weight_sharpe: float = 0.4
    weight_profit_factor: float = 0.3
    weight_drawdown_penalty: float = 0.3


DEFAULT_EVAL_CONFIG = EvaluationConfig()


def _abs_drawdown(stats: Dict) -> float:
    """Return drawdown as a positive percentage.

    The backtest engine stores max_drawdown_pct as a negative value
    (e.g. -15.0 for a 15% drawdown) because it derives from
    `(equity / running_max - 1).min()`. All comparisons in this module
    need the absolute value to avoid sign-flip errors.
    """
    return abs(float(stats.get("max_drawdown_pct", 0.0) or 0.0))


def compute_score(stats: Dict, cfg: EvaluationConfig = DEFAULT_EVAL_CONFIG) -> float:
    sharpe = float(stats.get("sharpe_ratio", 0.0) or 0.0)
    pf = float(stats.get("profit_factor", 0.0) or 0.0)
    dd = _abs_drawdown(stats)  # positive, e.g. 15.0

    # Drawdown component: 1.0 when dd=0, decays linearly to 0 at max_drawdown_pct
    if dd >= cfg.max_drawdown_pct:
        dd_component = 0.0
    else:
        dd_component = max(0.0, 1.0 - dd / cfg.max_drawdown_pct)

    base_score = (
        cfg.weight_sharpe * sharpe
        + cfg.weight_profit_factor * pf
        + cfg.weight_drawdown_penalty * dd_component
    )

    # ------------------------------------------------------------------ #
    # strategy_explain adjustments                                        #
    # ------------------------------------------------------------------ #
    explain = stats.get("strategy_explain", {}) or {}

    # Regime preference — reward strategies that earn in trending regimes
    regime_pnl = explain.get("regime_pnl", {}) or {}
    trend_ret = float(
        (regime_pnl.get("trending_up", {}) or {}).get("return_pct", 0.0)
        + (regime_pnl.get("trending_down", {}) or {}).get("return_pct", 0.0)
    )
    range_ret = float((regime_pnl.get("ranging", {}) or {}).get("return_pct", 0.0))

    regime_bonus = 0.0
    regime_penalty = 0.0
    if trend_ret > 1.0:
        regime_bonus += 0.15
    if range_ret > -2.0:
        regime_bonus += 0.05
    if min(trend_ret, range_ret) < -6.0:
        regime_penalty += 0.25
    elif min(trend_ret, range_ret) < -3.0:
        regime_penalty += 0.12

    # Stability — penalize highly unstable Sharpe across subperiods
    stability = explain.get("stability", {}) or {}
    sharpe_std = float(stability.get("sharpe_std", 0.0) or 0.0)
    stability_penalty = min(0.2, max(0.0, sharpe_std))

    # News behavior — avoid strategies that consistently lose around high-impact events
    news = explain.get("news_behavior", {}) or {}
    hi = news.get("trades_around_high_impact", {}) or {}
    hi_ret = float(hi.get("return_pct", 0.0) or 0.0)
    hi_count = int(hi.get("num_trades", 0) or 0)
    avoidance_rate = float(news.get("avoidance_rate", 0.0) or 0.0)

    news_bonus = 0.0
    news_penalty = 0.0
    if hi_count >= 5 and hi_ret < -2.0:
        news_penalty = 0.2
    if avoidance_rate > 0.7 and hi_ret >= 0.0:
        news_bonus = 0.1

    meta = explain.get("meta", {}) or {}
    routing_conf = float(meta.get("routing_confidence", 0.0) or 0.0)
    blocked_regimes = list(meta.get("blocked_regimes", []) or [])
    blocked_sessions = list(meta.get("blocked_sessions", []) or [])
    routing_bonus = 0.0
    routing_penalty = 0.0
    if routing_conf >= 0.75:
        routing_bonus += 0.15
    elif routing_conf < 0.45:
        routing_penalty += 0.20
    if blocked_regimes:
        routing_penalty += min(0.15, 0.05 * len(blocked_regimes))
    if blocked_sessions:
        routing_penalty += min(0.10, 0.05 * len(blocked_sessions))

    score = (
        base_score
        + regime_bonus
        + news_bonus
        + routing_bonus
        - regime_penalty
        - stability_penalty
        - news_penalty
        - routing_penalty
    )

    # Clamp to a reasonable range — avoids extreme values confusing memory bonuses
    return float(max(-2.0, min(10.0, score)))


def passes_thresholds(stats: Dict, cfg: EvaluationConfig = DEFAULT_EVAL_CONFIG) -> bool:
    num_trades = float(stats.get("num_trades", 0.0) or 0.0)
    sharpe = float(stats.get("sharpe_ratio", 0.0) or 0.0)
    dd = _abs_drawdown(stats)   # positive
    pf = float(stats.get("profit_factor", 0.0) or 0.0)

    if num_trades < cfg.min_trades:
        logger.info(
            "Rejected: too few trades (%.0f < %d)", num_trades, cfg.min_trades
        )
        return False

    if sharpe < cfg.min_sharpe:
        logger.info(
            "Rejected: sharpe %.3f < %.3f", sharpe, cfg.min_sharpe
        )
        return False

    if dd > cfg.max_drawdown_pct:
        logger.info(
            "Rejected: drawdown %.2f%% > max %.2f%%", dd, cfg.max_drawdown_pct
        )
        return False

    if pf < cfg.min_profit_factor:
        logger.info(
            "Rejected: profit_factor %.3f < %.3f", pf, cfg.min_profit_factor
        )
        return False

    return True


def evaluate_strategy(
    stats: Dict, cfg: EvaluationConfig = DEFAULT_EVAL_CONFIG
) -> Dict:
    score = compute_score(stats, cfg)
    ok = passes_thresholds(stats, cfg)

    result = {
        **stats,
        "score": score,
        "accepted": bool(ok),
    }

    # Log only scalar metrics — skip strategy_explain (can be a large nested dict)
    scalar_stats = {
        k: round(v, 3) if isinstance(v, float) else v
        for k, v in stats.items()
        if isinstance(v, (int, float)) and k != "strategy_explain"
    }
    logger.info(
        "Evaluation: score=%.3f accepted=%s dd_abs=%.2f%% | %s",
        score,
        ok,
        _abs_drawdown(stats),
        scalar_stats,
    )

    return result