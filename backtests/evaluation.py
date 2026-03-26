from __future__ import annotations

from dataclasses import dataclass
from typing import Dict

from ..logging_utils import get_logger

logger = get_logger(__name__)


@dataclass
class EvaluationConfig:
    min_trades: int = 20
    min_sharpe: float = 0.15
    max_drawdown_pct: float = 25.0
    min_profit_factor: float = 1.08

    weight_sharpe: float = 0.35
    weight_profit_factor: float = 0.25
    weight_drawdown_penalty: float = 0.20
    weight_expectancy: float = 0.20


DEFAULT_EVAL_CONFIG = EvaluationConfig()


def _abs_drawdown(stats: Dict) -> float:
    return abs(float(stats.get("max_drawdown_pct", 0.0) or 0.0))


def compute_score(stats: Dict, cfg: EvaluationConfig = DEFAULT_EVAL_CONFIG) -> float:
    sharpe = float(stats.get("sharpe_ratio", 0.0) or 0.0)
    pf = float(stats.get("profit_factor", 0.0) or 0.0)
    dd = _abs_drawdown(stats)
    expectancy = float(stats.get("expectancy", 0.0) or 0.0)

    if dd >= cfg.max_drawdown_pct:
        dd_component = 0.0
    else:
        dd_component = max(0.0, 1.0 - dd / cfg.max_drawdown_pct)

    expectancy_component = max(-1.0, min(1.0, expectancy / 100.0))

    base_score = (
        cfg.weight_sharpe * sharpe
        + cfg.weight_profit_factor * pf
        + cfg.weight_drawdown_penalty * dd_component
        + cfg.weight_expectancy * expectancy_component
    )

    explain = stats.get("strategy_explain", {}) or {}
    regime_pnl = explain.get("regime_pnl", {}) or {}
    session_pnl = explain.get("session_pnl", {}) or {}
    risk_behavior = explain.get("risk_behavior", {}) or {}
    stability = explain.get("stability", {}) or {}
    news = explain.get("news_behavior", {}) or {}
    meta = explain.get("meta", {}) or {}

    trend_ret = float(
        (regime_pnl.get("trending_up", {}) or {}).get("return_pct", 0.0)
        + (regime_pnl.get("trending_down", {}) or {}).get("return_pct", 0.0)
    )
    range_ret = float((regime_pnl.get("ranging", {}) or {}).get("return_pct", 0.0))

    regime_bonus = 0.0
    if trend_ret > 1.0:
        regime_bonus += 0.15
    if range_ret > 0.5:
        regime_bonus += 0.10

    sharpe_std = float(stability.get("sharpe_std", 0.0) or 0.0)
    stability_penalty = min(0.35, max(0.0, sharpe_std * 0.5))

    hi = news.get("trades_around_high_impact", {}) or {}
    hi_ret = float(hi.get("return_pct", 0.0) or 0.0)
    hi_count = int(hi.get("num_trades", 0) or 0)
    avoidance_rate = float(news.get("avoidance_rate", 0.0) or 0.0)

    news_bonus = 0.0
    news_penalty = 0.0
    if hi_count >= 5 and hi_ret < -1.0:
        news_penalty = 0.15
    if avoidance_rate > 0.7 and hi_ret >= 0.0:
        news_bonus = 0.05

    session_penalty = 0.0
    session_returns = [float((v or {}).get("return_pct", 0.0) or 0.0) for v in session_pnl.values() if int((v or {}).get("num_trades", 0) or 0) >= 8]
    if session_returns and min(session_returns) < -2.5:
        session_penalty += 0.10

    specialist_bonus = 0.10 * float(meta.get("specialist_score", 0.0) or 0.0)
    routing_bonus = 0.10 * float(meta.get("routing_confidence", 0.0) or 0.0)

    exit_rule_ratio = float(risk_behavior.get("exit_rule_ratio", 0.0) or 0.0)
    avg_holding_bars = float(risk_behavior.get("avg_holding_bars", 0.0) or 0.0)
    fragility_penalty = 0.0
    if exit_rule_ratio > 0.80:
        fragility_penalty += 0.12
    if avg_holding_bars < 1.0:
        fragility_penalty += 0.08

    score = (
        base_score
        + regime_bonus
        + news_bonus
        + specialist_bonus
        + routing_bonus
        - stability_penalty
        - news_penalty
        - session_penalty
        - fragility_penalty
    )

    return float(max(-2.0, min(10.0, score)))


def passes_thresholds(stats: Dict, cfg: EvaluationConfig = DEFAULT_EVAL_CONFIG) -> bool:
    num_trades = float(stats.get("num_trades", 0.0) or 0.0)
    sharpe = float(stats.get("sharpe_ratio", 0.0) or 0.0)
    dd = _abs_drawdown(stats)
    pf = float(stats.get("profit_factor", 0.0) or 0.0)

    if num_trades < cfg.min_trades:
        logger.info("Rejected: too few trades (%.0f < %d)", num_trades, cfg.min_trades)
        return False
    if sharpe < cfg.min_sharpe:
        logger.info("Rejected: sharpe %.3f < %.3f", sharpe, cfg.min_sharpe)
        return False
    if dd > cfg.max_drawdown_pct:
        logger.info("Rejected: drawdown %.2f%% > max %.2f%%", dd, cfg.max_drawdown_pct)
        return False
    if pf < cfg.min_profit_factor:
        logger.info("Rejected: profit_factor %.3f < %.3f", pf, cfg.min_profit_factor)
        return False
    return True


def evaluate_strategy(stats: Dict, cfg: EvaluationConfig = DEFAULT_EVAL_CONFIG) -> Dict:
    score = compute_score(stats, cfg)
    ok = passes_thresholds(stats, cfg)

    result = {
        **stats,
        "score": score,
        "accepted": bool(ok),
    }

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
