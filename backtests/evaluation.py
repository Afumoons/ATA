from __future__ import annotations

from dataclasses import dataclass
from typing import Dict

from ..logging_utils import get_logger

logger = get_logger(__name__)


@dataclass
class EvaluationConfig:
    # Looser thresholds for discovery; we still compute scores for ranking
    # and can tighten these later for live trading selection.
    min_trades: int = 15
    min_sharpe: float = 0.1
    max_drawdown_pct: float = 30.0
    min_profit_factor: float = 1.05

    weight_sharpe: float = 0.4
    weight_profit_factor: float = 0.3
    weight_drawdown_penalty: float = 0.3


DEFAULT_EVAL_CONFIG = EvaluationConfig()


def compute_score(stats: Dict[str, float], cfg: EvaluationConfig = DEFAULT_EVAL_CONFIG) -> float:
    sharpe = stats.get("sharpe_ratio", 0.0)
    pf = stats.get("profit_factor", 0.0)
    dd = stats.get("max_drawdown_pct", 0.0)

    # Drawdown penalty: 1.0 when dd=0, decays linearly to 0 at cfg.max_drawdown_pct
    if dd >= cfg.max_drawdown_pct:
        dd_penalty = 0.0
    else:
        dd_penalty = max(0.0, 1.0 - dd / cfg.max_drawdown_pct)

    base_score = (
        cfg.weight_sharpe * sharpe +
        cfg.weight_profit_factor * pf +
        cfg.weight_drawdown_penalty * dd_penalty
    )

    # Optional strategy_explain-aware adjustments
    explain = stats.get("strategy_explain", {}) or {}

    # Regime preference: reward strategies that earn in trending regimes
    regime_pnl = explain.get("regime_pnl", {}) or {}
    trend_ret = (
        regime_pnl.get("trending_up", {}).get("return_pct", 0.0) +
        regime_pnl.get("trending_down", {}).get("return_pct", 0.0)
    )
    range_ret = regime_pnl.get("ranging", {}).get("return_pct", 0.0)

    regime_bonus = 0.0
    if trend_ret > 0:
        regime_bonus += 0.2
    if range_ret > -3.0:
        regime_bonus += 0.1

    # Stability: penalize highly unstable Sharpe across subperiods
    stability = explain.get("stability", {}) or {}
    sharpe_std = float(stability.get("sharpe_std", 0.0) or 0.0)
    stability_penalty = min(0.2, max(0.0, sharpe_std))

    # News behavior: avoid strategies that consistently lose around high-impact news
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

    score = base_score + regime_bonus + news_bonus - stability_penalty - news_penalty
    return float(score)


def passes_thresholds(stats: Dict[str, float], cfg: EvaluationConfig = DEFAULT_EVAL_CONFIG) -> bool:
    num_trades = stats.get("num_trades", 0.0)
    sharpe = stats.get("sharpe_ratio", 0.0)
    dd = stats.get("max_drawdown_pct", 0.0)
    pf = stats.get("profit_factor", 0.0)

    if num_trades < cfg.min_trades:
        logger.info("Rejected strategy: too few trades (%.0f < %d)", num_trades, cfg.min_trades)
        return False
    if sharpe < cfg.min_sharpe:
        logger.info("Rejected strategy: sharpe %.2f < %.2f", sharpe, cfg.min_sharpe)
        return False
    if dd > cfg.max_drawdown_pct:
        logger.info("Rejected strategy: drawdown %.2f%% > %.2f%%", dd, cfg.max_drawdown_pct)
        return False
    if pf < cfg.min_profit_factor:
        logger.info("Rejected strategy: profit factor %.2f < %.2f", pf, cfg.min_profit_factor)
        return False

    return True


def evaluate_strategy(stats: Dict[str, float], cfg: EvaluationConfig = DEFAULT_EVAL_CONFIG) -> Dict[str, float]:
    score = compute_score(stats, cfg)
    ok = passes_thresholds(stats, cfg)
    result = {
        **stats,
        "score": score,
        "accepted": bool(ok),
    }
    logger.info(
        "Evaluation result: score=%.3f, accepted=%s, stats=%s",
        score,
        ok,
        {k: round(v, 3) if isinstance(v, float) else v for k, v in stats.items()},
    )
    return result
