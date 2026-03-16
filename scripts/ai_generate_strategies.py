from __future__ import annotations

"""AI-assisted strategy generation helper (Level 1).

This script does **not** call any AI APIs by itself. Instead, it prepares a
compact summary of the current strategy pool and writes it to a file that
Clio (the research agent) can read and use as context to design new
strategies.

Usage (from workspace root):

    .\\autonomous_trading_ai\\.venv\\Scripts\\python.exe -m autonomous_trading_ai.scripts.ai_generate_strategies \
        --symbol XAUUSDm --timeframe M15 --limit 20

What it does:
- Load the current StrategyPool from `strategies/pool_state.json`.
- Filter strategies by symbol/timeframe.
- Select top-N by score and (optionally) bottom-M for contrast.
- Extract core stats + `strategy_explain` for each.
- Dump everything into a JSON file under `backtests/results/ai_research_input.json`.

Clio can then:
- Read that JSON, analyse patterns (what works / fails, in which regimes).
- Propose new StrategyDefinition configs.
- Write them as JSON files into `strategies/generated/`.

Live trading remains purely deterministic; AI is only used offline to
propose new configs.
"""

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List

from autonomous_trading_ai.backtests.engine import RESULTS_DIR
from autonomous_trading_ai.strategies.pool import load_pool


def _extract_summary(rec: Any) -> Dict[str, Any]:
    stats: Dict[str, Any] = rec.stats or {}
    explain: Dict[str, Any] = stats.get("strategy_explain", {}) or {}

    # Only keep light-weight parts of explain to keep file compact
    regime = explain.get("regime_pnl", {}) or {}
    stability = explain.get("stability", {}) or {}
    news = explain.get("news_behavior", {}) or {}
    meta = explain.get("meta", {}) or {}

    return {
        "name": rec.name,
        "symbol": rec.symbol,
        "timeframe": rec.timeframe,
        "status": rec.status,
        "score": rec.score,
        "stats": {
            "return_pct": stats.get("return_pct"),
            "sharpe_ratio": stats.get("sharpe_ratio"),
            "max_drawdown_pct": stats.get("max_drawdown_pct"),
            "profit_factor": stats.get("profit_factor"),
            "win_rate": stats.get("win_rate"),
            "num_trades": stats.get("num_trades"),
        },
        "strategy_explain": {
            "regime_pnl": regime,
            "stability": stability,
            "news_behavior": news,
            "meta": meta,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare AI research input from strategy pool")
    parser.add_argument("--symbol", default="XAUUSDm", help="Symbol filter (default: XAUUSDm)")
    parser.add_argument("--timeframe", default="M15", help="Timeframe filter (default: M15)")
    parser.add_argument("--limit", type=int, default=20, help="Number of top strategies to include (default: 20)")
    parser.add_argument("--include_bottom", type=int, default=5, help="Number of worst strategies to include for contrast (default: 5)")
    args = parser.parse_args()

    pool = load_pool()
    all_recs: List[Any] = [
        rec
        for rec in pool.strategies.values()
        if rec.symbol == args.symbol and rec.timeframe == args.timeframe
    ]

    if not all_recs:
        print("No strategies found for given filters.")
        return

    # Top N by score
    sorted_recs = sorted(all_recs, key=lambda r: r.score, reverse=True)
    top_recs = sorted_recs[: args.limit]

    # Bottom M by score for contrast (different set from top)
    bottom_recs = list(reversed(sorted_recs))[: args.include_bottom]

    # Deduplicate if overlap
    seen = set()
    selected: List[Any] = []
    for rec in top_recs + bottom_recs:
        if rec.name in seen:
            continue
        seen.add(rec.name)
        selected.append(rec)

    summary = {
        "symbol": args.symbol,
        "timeframe": args.timeframe,
        "total_strategies": len(all_recs),
        "selected_count": len(selected),
        "strategies": [_extract_summary(rec) for rec in selected],
    }

    out_path = Path(RESULTS_DIR) / "ai_research_input.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    print(f"AI research input written to {out_path}")
    print(f"  symbol={args.symbol} timeframe={args.timeframe}")
    print(f"  total_in_pool={len(all_recs)} selected={len(selected)}")


if __name__ == "__main__":
    main()
