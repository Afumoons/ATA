from __future__ import annotations

"""Quick status summary for the autonomous_trading_ai system.

Usage (from workspace root, venv activated):

    python -m autonomous_trading_ai.scripts.print_live_summary

This prints:
- daily equity / PnL from execution/live_state.json
- count of strategies by status (active / candidate / disabled)
- top-N active strategies by backtest score
- (if available) basic per-strategy live PnL stats from strategy_live_stats.json
"""

import json
from pathlib import Path
from typing import Dict


BASE_DIR = Path(__file__).resolve().parents[1]
EXECUTION_DIR = BASE_DIR / "execution"
STRATEGIES_DIR = BASE_DIR / "strategies"


def _load_json(path: Path):
    if not path.exists():
        return None
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def print_live_state() -> None:
    live_path = EXECUTION_DIR / "live_state.json"
    data = _load_json(live_path)
    print("=== Daily Account State ===")
    if not data:
        print("live_state.json not found or invalid")
        print()
        return
    print(f"Date            : {data.get('date')}")
    print(f"Equity start    : {data.get('equity_start'):.2f}")
    print(f"Equity current  : {data.get('equity_current'):.2f}")
    print(f"Daily PnL       : {data.get('daily_pnl'):.2f} ({data.get('daily_return_pct'):.2f}%)")
    print(f"Trades today    : {int(data.get('trades_today', 0))}")
    print(f"Locked for day  : {data.get('locked_for_day')}")
    print()


def print_pool_summary(top_n: int = 5) -> None:
    pool_path = STRATEGIES_DIR / "pool_state.json"
    data = _load_json(pool_path)
    print("=== Strategy Pool ===")
    if not data:
        print("pool_state.json not found or invalid")
        print()
        return

    # counts by status
    status_counts: Dict[str, int] = {}
    for rec in data.values():
        status = rec.get("status", "unknown")
        status_counts[status] = status_counts.get(status, 0) + 1

    for status in sorted(status_counts.keys()):
        print(f"{status:9s}: {status_counts[status]}")

    # top-N active by score
    active = [rec for rec in data.values() if rec.get("status") == "active"]
    active.sort(key=lambda r: float(r.get("score", 0.0) or 0.0), reverse=True)

    if active:
        print()
        print(f"Top {min(top_n, len(active))} active strategies by score:")
        for rec in active[:top_n]:
            name = rec.get("name")
            score = float(rec.get("score", 0.0) or 0.0)
            stats = rec.get("stats", {}) or {}
            ret = float(stats.get("return_pct", 0.0) or 0.0)
            dd = float(stats.get("max_drawdown_pct", 0.0) or 0.0)
            num_trades = int(stats.get("num_trades", 0.0) or 0.0)
            print(
                f"- {name}: score={score:.3f}, bt_ret={ret:.2f}%, bt_maxDD={dd:.2f}%, bt_trades={num_trades}"
            )

    print()


def print_strategy_live_stats() -> None:
    stats_path = EXECUTION_DIR / "strategy_live_stats.json"
    data = _load_json(stats_path)
    print("=== Per-Strategy Live PnL (if available) ===")
    if not data or "strategies" not in data:
        print("strategy_live_stats.json not found or empty")
        print()
        return

    stats = data["strategies"]
    if not stats:
        print("No live stats recorded yet")
        print()
        return

    # sort by total_pnl ascending (worst first)
    recs = []
    for name, rec in stats.items():
        total_pnl = float(rec.get("total_pnl", 0.0) or 0.0)
        num_trades = int(rec.get("num_trades", 0) or 0)
        recent_pnls = rec.get("recent_pnls", []) or []
        recent_avg = sum(recent_pnls) / len(recent_pnls) if recent_pnls else 0.0
        recs.append((name, total_pnl, num_trades, recent_avg, len(recent_pnls)))

    if not recs:
        print("No live stats recorded yet")
        print()
        return

    recs.sort(key=lambda r: r[1])  # by total_pnl

    print("Worst 5 strategies by total live PnL:")
    for name, total_pnl, num_trades, recent_avg, n_recent in recs[:5]:
        print(
            f"- {name}: total_pnl={total_pnl:.2f}, trades={num_trades}, "
            f"recent_avg_pnl={recent_avg:.2f} over {n_recent} trades"
        )

    print()


def main() -> None:
    print_live_state()
    print_pool_summary(top_n=5)
    print_strategy_live_stats()


if __name__ == "__main__":
    main()
