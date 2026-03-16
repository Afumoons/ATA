from __future__ import annotations

"""Pre-session check script for autonomous_trading_ai.

This is the automated analogue of the manual pre-session routine:

- Refresh data, features, and regimes.
- Run one research/evolution cycle.
- Print a concise summary of risk config and top XAUUSDm M15 strategies,
  including highlights from strategy_explain.

Usage (from workspace root):

    .\\autonomous_trading_ai\\.venv\\Scripts\\python.exe -m autonomous_trading_ai.scripts.pre_session_check
"""

from typing import Any, Dict

from autonomous_trading_ai.config import risk_config
from autonomous_trading_ai.scheduler.main import job_update_data, job_research_strategies
from autonomous_trading_ai.strategies.pool import load_pool


def _fmt_pct(x: float | None) -> str:
    if x is None:
        return "n/a"
    return f"{x:.2f}%"


def _fmt_float(x: float | None) -> str:
    if x is None:
        return "n/a"
    return f"{x:.3f}"


def _summarize_strategy(name: str, rec: Any) -> None:
    stats: Dict[str, Any] = rec.stats or {}
    ex: Dict[str, Any] = stats.get("strategy_explain", {}) or {}

    print("=" * 80)
    print(f"Strategy: {name}  [{rec.symbol} {rec.timeframe}]  status={rec.status}  score={rec.score:.3f}")

    print("-- Core stats --")
    print(
        f"  return={_fmt_pct(stats.get('return_pct'))}  "
        f"sharpe={_fmt_float(stats.get('sharpe_ratio'))}  "
        f"max_dd={_fmt_pct(stats.get('max_drawdown_pct'))}  "
        f"pf={_fmt_float(stats.get('profit_factor'))}  "
        f"trades={int(stats.get('num_trades', 0))}"
    )

    regime = ex.get("regime_pnl", {}) or {}
    news = ex.get("news_behavior", {}) or {}
    meta = ex.get("meta", {}) or {}

    if regime:
        print("-- Regime PnL --")
        for key in sorted(regime.keys()):
            r = regime[key]
            print(
                f"  {key:15s}: ret={_fmt_pct(r.get('return_pct'))}  "
                f"trades={int(r.get('num_trades', 0))}  "
                f"win={_fmt_float(r.get('win_rate'))}"
            )

    if news:
        hi = news.get("trades_around_high_impact", {}) or {}
        print("-- News behavior --")
        print(
            f"  hi_trades={int(hi.get('num_trades', 0))}  "
            f"hi_ret={_fmt_pct(hi.get('return_pct'))}  "
            f"avoidance={_fmt_float(news.get('avoidance_rate'))}  "
            f"pre_news={_fmt_pct(news.get('pre_news_return_pct'))}  "
            f"post_news={_fmt_pct(news.get('post_news_return_pct'))}"
        )

    if meta:
        print("-- Meta --")
        print(
            f"  best_regime={meta.get('best_regime')}  "
            f"worst_regime={meta.get('worst_regime')}  "
            f"is_trend_follower={meta.get('is_trend_follower')}  "
            f"is_range_trader={meta.get('is_range_trader')}"
        )

    print()


def main() -> None:
    print("[Pre-Session] Running job_update_data()...")
    job_update_data()

    print("[Pre-Session] Running job_research_strategies()...")
    job_research_strategies()

    print("\n[Pre-Session] Risk configuration:")
    print(
        f"  max_risk_per_trade_pct={risk_config.max_risk_per_trade_pct:.2f}%\n"
        f"  max_portfolio_drawdown_pct={risk_config.max_portfolio_drawdown_pct:.2f}%\n"
        f"  max_open_positions={risk_config.max_open_positions}\n"
        f"  max_daily_drawdown_pct={risk_config.max_daily_drawdown_pct:.2f}% (enabled={risk_config.daily_limits_enabled})\n"
        f"  max_trades_per_day={risk_config.max_trades_per_day} (enabled={risk_config.daily_limits_enabled})"
    )

    print("\n[Pre-Session] Top active XAUUSDm M15 strategies:")
    pool = load_pool()
    recs = [
        rec
        for rec in pool.strategies.values()
        if rec.symbol == "XAUUSDm" and rec.timeframe == "M15" and rec.status == "active"
    ]
    recs.sort(key=lambda r: r.score, reverse=True)
    recs = recs[:5]

    if not recs:
        print("  (No active strategies yet for XAUUSDm M15)")
        return

    for rec in recs:
        _summarize_strategy(rec.name, rec)


if __name__ == "__main__":
    main()
