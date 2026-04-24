from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

from autonomous_trading_ai.strategies.pool import load_pool, save_pool

ROOT = Path(__file__).resolve().parents[1]
TRADE_JOURNAL_PATH = ROOT / "execution" / "strategy_trade_journal.json"

MIN_TRADES_PER_BUCKET = 3
ALLOWED_RETURN_THRESHOLD = 0.0
BLOCKED_RETURN_THRESHOLD = -20.0


@dataclass
class BucketAgg:
    total_pnl: float = 0.0
    num_trades: int = 0

    @property
    def avg_pnl(self) -> float:
        return self.total_pnl / self.num_trades if self.num_trades else 0.0


def _derive_live_routing_confidence(best_ret: float, worst_ret: float, total_trades: int, num_allowed: int, num_blocked: int) -> float:
    trade_score = min(1.0, max(0.0, total_trades / 30.0))
    spread = max(0.0, best_ret - worst_ret)
    separation_score = min(1.0, spread / 100.0)
    specialization_score = min(1.0, (num_allowed + num_blocked) / 4.0)
    leakage_penalty = 0.2 if worst_ret <= -80.0 else (0.1 if worst_ret <= -40.0 else 0.0)
    raw = 0.45 * trade_score + 0.35 * separation_score + 0.20 * specialization_score
    return round(max(0.0, min(1.0, raw - leakage_penalty)), 4)


def _empty_bucket_map() -> dict[str, BucketAgg]:
    return defaultdict(BucketAgg)


def _to_stats_map(bucket_map: dict[str, BucketAgg]) -> dict[str, dict[str, float | int]]:
    return {
        label: {
            "total_pnl": round(agg.total_pnl, 6),
            "num_trades": int(agg.num_trades),
            "avg_pnl": round(agg.avg_pnl, 6),
        }
        for label, agg in sorted(bucket_map.items())
    }


def _derive_allowed_blocked(stats_map: dict[str, dict[str, float | int]]) -> tuple[list[str], list[str]]:
    allowed: list[str] = []
    blocked: list[str] = []
    for label, stats in stats_map.items():
        num_trades = int(stats.get("num_trades", 0) or 0)
        total_pnl = float(stats.get("total_pnl", 0.0) or 0.0)
        if num_trades < MIN_TRADES_PER_BUCKET:
            continue
        if total_pnl > ALLOWED_RETURN_THRESHOLD:
            allowed.append(label)
        elif total_pnl <= BLOCKED_RETURN_THRESHOLD:
            blocked.append(label)
    return sorted(allowed), sorted(blocked)


def _best_worst(stats_map: dict[str, dict[str, float | int]]) -> tuple[str | None, str | None, float, float]:
    eligible = {k: v for k, v in stats_map.items() if int(v.get("num_trades", 0) or 0) >= MIN_TRADES_PER_BUCKET}
    if not eligible:
        return None, None, 0.0, 0.0
    best = max(eligible, key=lambda k: float(eligible[k].get("total_pnl", 0.0) or 0.0))
    worst = min(eligible, key=lambda k: float(eligible[k].get("total_pnl", 0.0) or 0.0))
    best_ret = float(eligible[best].get("total_pnl", 0.0) or 0.0)
    worst_ret = float(eligible[worst].get("total_pnl", 0.0) or 0.0)
    return best, worst, best_ret, worst_ret


def main() -> None:
    if not TRADE_JOURNAL_PATH.exists():
        raise FileNotFoundError(f"Missing trade journal: {TRADE_JOURNAL_PATH}")

    journal = json.loads(TRADE_JOURNAL_PATH.read_text(encoding="utf-8"))
    pool = load_pool()

    patched = 0
    strategies_seen = 0

    for strategy_name, payload in (journal.get("strategies") or {}).items():
        strategies_seen += 1
        rec = pool.strategies.get(strategy_name)
        if rec is None:
            continue

        regime_pnl = _empty_bucket_map()
        regime_class_pnl = _empty_bucket_map()
        regime_type_pnl = _empty_bucket_map()
        vol_regime_pnl = _empty_bucket_map()
        session_pnl = _empty_bucket_map()
        total_live_trades = 0
        total_live_pnl = 0.0

        for trade in payload.get("trades") or []:
            pnl = trade.get("pnl")
            if pnl is None:
                continue
            try:
                pnl_f = float(pnl)
            except Exception:
                continue
            ctx = (trade.get("entry_context") or {})
            regime = ctx.get("regime")
            regime_class = ctx.get("regime_class")
            regime_type = ctx.get("regime_type")
            vol_regime = ctx.get("vol_regime")
            session = ctx.get("session")

            total_live_trades += 1
            total_live_pnl += pnl_f

            if regime:
                regime_pnl[str(regime)].total_pnl += pnl_f
                regime_pnl[str(regime)].num_trades += 1
            if regime_class:
                regime_class_pnl[str(regime_class)].total_pnl += pnl_f
                regime_class_pnl[str(regime_class)].num_trades += 1
            if regime_type:
                regime_type_pnl[str(regime_type)].total_pnl += pnl_f
                regime_type_pnl[str(regime_type)].num_trades += 1
            if vol_regime:
                vol_regime_pnl[str(vol_regime)].total_pnl += pnl_f
                vol_regime_pnl[str(vol_regime)].num_trades += 1
            if session:
                session_pnl[str(session)].total_pnl += pnl_f
                session_pnl[str(session)].num_trades += 1

        explain = (rec.stats or {}).get("strategy_explain", {}) or {}
        live_regime_map = _to_stats_map(regime_pnl)
        live_session_map = _to_stats_map(session_pnl)
        live_regime_class_map = _to_stats_map(regime_class_pnl)
        live_regime_type_map = _to_stats_map(regime_type_pnl)
        live_vol_regime_map = _to_stats_map(vol_regime_pnl)

        allowed_regimes, blocked_regimes = _derive_allowed_blocked(live_regime_map)
        allowed_sessions, blocked_sessions = _derive_allowed_blocked(live_session_map)
        best_regime, worst_regime, best_ret, worst_ret = _best_worst(live_regime_map)
        best_session, worst_session, best_session_ret, worst_session_ret = _best_worst(live_session_map)
        routing_confidence = _derive_live_routing_confidence(
            best_ret,
            worst_ret,
            total_live_trades,
            len(allowed_regimes) + len(allowed_sessions),
            len(blocked_regimes) + len(blocked_sessions),
        )

        explain["live_regime_pnl"] = live_regime_map
        explain["live_regime_class_pnl"] = live_regime_class_map
        explain["live_regime_type_pnl"] = live_regime_type_map
        explain["live_vol_regime_pnl"] = live_vol_regime_map
        explain["live_session_pnl"] = live_session_map
        explain["live_meta"] = {
            "total_live_trades": total_live_trades,
            "total_live_pnl": round(total_live_pnl, 6),
            "best_regime": best_regime,
            "worst_regime": worst_regime,
            "best_regime_pnl": round(best_ret, 6),
            "worst_regime_pnl": round(worst_ret, 6),
            "best_session": best_session,
            "worst_session": worst_session,
            "best_session_pnl": round(best_session_ret, 6),
            "worst_session_pnl": round(worst_session_ret, 6),
            "allowed_regimes": allowed_regimes,
            "blocked_regimes": blocked_regimes,
            "allowed_sessions": allowed_sessions,
            "blocked_sessions": blocked_sessions,
            "routing_confidence": routing_confidence,
            "min_trades_per_bucket": MIN_TRADES_PER_BUCKET,
        }
        rec.stats = rec.stats or {}
        rec.stats["strategy_explain"] = explain
        patched += 1

    save_pool(pool)
    print(f"Evaluated live trade context for {patched} strategies (journal seen={strategies_seen})")


if __name__ == "__main__":
    main()
