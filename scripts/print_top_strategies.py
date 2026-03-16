from __future__ import annotations

"""Utility script to inspect top strategies in the pool.

Usage (from workspace root):

    .\\autonomous_trading_ai\\.venv\\Scripts\\python.exe -m autonomous_trading_ai.scripts.print_top_strategies

Or from autonomous_trading_ai directory:

    .venv\\Scripts\\python.exe -m scripts.print_top_strategies

This prints a concise summary of the best strategies for a given
symbol/timeframe, including key stats and highlights from
strategy_explain.
"""

import argparse
from typing import Any, Dict

from ..strategies.pool import load_pool


def _fmt_pct(x: float | None) -> str:
    if x is None:
        return "n/a"
    return f"{x:.2f}%"


def _fmt_float(x: float | None) -> str:
    if x is None:
        return "n/a"
    return f"{x:.3f}"


def summarize_strategy(name: str, rec: Any) -> None:
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
    stability = ex.get("stability", {}) or {}
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

    if stability:
        subs = stability.get("subperiod_sharpe", [])
        std = stability.get("sharpe_std", 0.0)
        print("-- Stability --")
        print(f"  sub_sharpe={subs}  sharpe_std={_fmt_float(std)}")

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
    parser = argparse.ArgumentParser(description="Print top strategies from the pool")
    parser.add_argument("--symbol", default="XAUUSDm", help="Symbol filter (default: XAUUSDm)")
    parser.add_argument("--timeframe", default="M15", help="Timeframe filter (default: M15)")
    parser.add_argument("--status", default=None, help="Status filter: active/candidate/disabled (default: any)")
    parser.add_argument("--limit", type=int, default=10, help="Number of strategies to display (default: 10)")
    args = parser.parse_args()

    pool = load_pool()
    recs = [
        rec
        for rec in pool.strategies.values()
        if rec.symbol == args.symbol and rec.timeframe == args.timeframe
    ]

    if args.status:
        recs = [r for r in recs if r.status == args.status]

    recs.sort(key=lambda r: r.score, reverse=True)
    recs = recs[: args.limit]

    if not recs:
        print("No strategies found for given filters.")
        return

    for rec in recs:
        summarize_strategy(rec.name, rec)


if __name__ == "__main__":
    main()
