from __future__ import annotations

import re
from pathlib import Path

from autonomous_trading_ai.execution.signals import get_strategy_for_ticket
from autonomous_trading_ai.execution.strategy_live_stats import StrategyLiveStats, save_all_strategy_stats

TRADES_LOG_PATH = Path(__file__).resolve().parents[1] / "execution" / "trades.log"


def main() -> None:
    if not TRADES_LOG_PATH.exists():
        raise SystemExit("trades.log not found")

    ticket_re = re.compile(r"ticket=(\d+)")
    strategy_re = re.compile(r"strategy=([^\s]+)")

    stats: dict[str, StrategyLiveStats] = {}
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

    save_all_strategy_stats(stats)
    print(f"reconciled strategies={len(stats)} unresolved_tickets={len(unresolved)}")
    if unresolved:
        print("unresolved sample:", unresolved[:20])


if __name__ == "__main__":
    main()
