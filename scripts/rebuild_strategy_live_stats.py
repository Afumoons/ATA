from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone

import MetaTrader5 as mt5

from autonomous_trading_ai.execution.signals import get_strategy_for_ticket
from autonomous_trading_ai.execution.strategy_live_stats import StrategyLiveStats, save_all_strategy_stats


def main() -> None:
    now = datetime.now(timezone.utc)
    from_time = now - timedelta(days=14)
    deals = mt5.history_deals_get(from_time, now)
    if deals is None:
        raise RuntimeError(f"mt5.history_deals_get returned None for range {from_time} -> {now}")

    close_entry_code = getattr(mt5, "DEAL_ENTRY_OUT", None)
    stats: dict[str, StrategyLiveStats] = {}
    unmatched = []

    for deal in deals:
        if close_entry_code is not None and getattr(deal, "entry", None) != close_entry_code:
            continue

        pnl = float(getattr(deal, "profit", 0.0) or 0.0)
        order_ticket = getattr(deal, "order", None)
        position_id = getattr(deal, "position_id", None)
        deal_ticket = getattr(deal, "ticket", None)
        comment = str(getattr(deal, "comment", "") or "")

        strategy_name = None
        for candidate in (order_ticket, position_id, deal_ticket):
            if candidate is None:
                continue
            strategy_name = get_strategy_for_ticket(int(candidate))
            if strategy_name:
                break

        if not strategy_name and comment.startswith("clio-auto-"):
            strategy_name = comment[len("clio-auto-"):]

        if not strategy_name:
            unmatched.append({
                "deal": deal_ticket,
                "order": order_ticket,
                "position_id": position_id,
                "comment": comment,
                "profit": pnl,
            })
            continue

        rec = stats.get(strategy_name) or StrategyLiveStats(name=strategy_name)
        rec.total_pnl += pnl
        rec.num_trades += 1
        rec.last_update = now.isoformat()
        rec.recent_pnls.append(pnl)
        rec.recent_pnls = rec.recent_pnls[-30:]
        stats[strategy_name] = rec

    save_all_strategy_stats(stats)

    print(f"rebuilt strategies={len(stats)} unmatched={len(unmatched)}")
    for name in sorted(stats):
        rec = stats[name]
        print(f"{name}: trades={rec.num_trades} total_pnl={rec.total_pnl:.2f} recent_avg={(sum(rec.recent_pnls)/len(rec.recent_pnls) if rec.recent_pnls else 0.0):.2f}")

    if unmatched:
        print("UNMATCHED SAMPLE:")
        for item in unmatched[:10]:
            print(item)


if __name__ == "__main__":
    main()
