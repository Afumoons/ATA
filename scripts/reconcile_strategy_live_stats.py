from __future__ import annotations

import re
from pathlib import Path

from autonomous_trading_ai.execution.signals import get_strategy_for_ticket
from autonomous_trading_ai.execution.strategy_live_stats import StrategyLiveStats, load_all_strategy_stats, save_all_strategy_stats
from autonomous_trading_ai.execution.audit_utils import UNMATCHED_CLOSED_DEALS_PATH


def _reconcile_unmatched_manual_buckets(stats: dict[str, StrategyLiveStats]) -> int:
    rows = []
    if UNMATCHED_CLOSED_DEALS_PATH.exists():
        try:
            import json

            with UNMATCHED_CLOSED_DEALS_PATH.open("r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                rows = data
        except Exception:
            rows = []

    applied = 0
    for row in rows:
        if not isinstance(row, dict):
            continue
        bucket_name = str(row.get("manual_bucket") or "").strip()
        if not bucket_name:
            continue
        pnl = float(row.get("profit", 0.0) or 0.0)
        rec = stats.get(bucket_name) or StrategyLiveStats(name=bucket_name)
        rec.total_pnl += pnl
        rec.num_trades += 1
        if row.get("recorded_at"):
            rec.last_update = str(row.get("recorded_at"))
        rec.recent_pnls.append(pnl)
        rec.recent_pnls = rec.recent_pnls[-30:]
        stats[bucket_name] = rec
        applied += 1
    return applied

TRADES_LOG_PATH = Path(__file__).resolve().parents[1] / "execution" / "trades.log"


def main() -> None:
    if not TRADES_LOG_PATH.exists():
        raise SystemExit("trades.log not found")

    ticket_re = re.compile(r"ticket=(\d+)")
    strategy_re = re.compile(r"strategy=([^\s]+)")

    stats: dict[str, StrategyLiveStats] = load_all_strategy_stats()
    unresolved = []

    with TRADES_LOG_PATH.open("r", encoding="utf-8") as f:
        for line in f:
            t_match = ticket_re.search(line)
            s_match = strategy_re.search(line)
            if not t_match:
                continue

            ticket = int(t_match.group(1))
            strategy_name = s_match.group(1) if s_match else get_strategy_for_ticket(ticket)
            if not strategy_name:
                unresolved.append(ticket)
                continue

            rec = stats.get(strategy_name) or StrategyLiveStats(name=strategy_name)
            stats[strategy_name] = rec

    manual_rows = _reconcile_unmatched_manual_buckets(stats)
    save_all_strategy_stats(stats)
    print(f"reconciled strategies={len(stats)} unresolved_tickets={len(unresolved)} manual_rows={manual_rows}")
    if unresolved:
        print("unresolved sample:", unresolved[:20])


if __name__ == "__main__":
    main()
