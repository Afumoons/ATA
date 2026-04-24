from autonomous_trading_ai.strategies.pool import load_pool, save_pool


def _derive_routing_confidence(best_ret, worst_ret, total_trades, num_allowed, num_blocked):
    trade_score = min(1.0, max(0.0, total_trades / 80.0))
    spread = max(0.0, best_ret - worst_ret)
    separation_score = min(1.0, spread / 25.0)
    specialization_score = min(1.0, (num_allowed + num_blocked) / 4.0)
    leakage_penalty = 0.2 if worst_ret <= -8.0 else (0.1 if worst_ret <= -4.0 else 0.0)
    raw = 0.45 * trade_score + 0.35 * separation_score + 0.20 * specialization_score
    return round(max(0.0, min(1.0, raw - leakage_penalty)), 4)


def repair_legacy_metadata():
    pool = load_pool()
    repaired = 0

    for name, rec in pool.strategies.items():
        stats = rec.stats or {}
        explain = stats.get("strategy_explain", {}) or {}
        meta = explain.get("meta", {}) or {}

        if "routing_confidence" in meta:
            continue

        regime_pnl = explain.get("regime_pnl", {}) or {}
        session_pnl = explain.get("session_pnl", {}) or {}
        num_trades = int(stats.get("num_trades", 0) or 0)

        if not regime_pnl:
            continue

        allowed_regimes, blocked_regimes = [], []
        for label, rp in regime_pnl.items():
            ret = float((rp or {}).get("return_pct", 0) or 0)
            trades = int((rp or {}).get("num_trades", 0) or 0)
            if trades < 8:
                continue
            if ret >= 1.5:
                allowed_regimes.append(label)
            elif ret <= -4.0:
                blocked_regimes.append(label)

        allowed_sessions, blocked_sessions = [], []
        for label, sp in session_pnl.items():
            ret = float((sp or {}).get("return_pct", 0) or 0)
            trades = int((sp or {}).get("num_trades", 0) or 0)
            if trades < 8:
                continue
            if ret >= 0.75:
                allowed_sessions.append(label)
            elif ret <= -2.0:
                blocked_sessions.append(label)

        regime_rets = {
            k: float((v or {}).get("return_pct", 0) or 0)
            for k, v in regime_pnl.items()
            if int((v or {}).get("num_trades", 0) or 0) >= 8
        }
        session_rets = {
            k: float((v or {}).get("return_pct", 0) or 0)
            for k, v in session_pnl.items()
            if int((v or {}).get("num_trades", 0) or 0) >= 8
        }

        best_regime = max(regime_rets, key=regime_rets.get) if regime_rets else meta.get("best_regime")
        worst_regime = min(regime_rets, key=regime_rets.get) if regime_rets else meta.get("worst_regime")
        best_session = max(session_rets, key=session_rets.get) if session_rets else None
        worst_session = min(session_rets, key=session_rets.get) if session_rets else None

        best_ret = regime_rets.get(best_regime, 0) if best_regime else 0
        worst_ret = regime_rets.get(worst_regime, 0) if worst_regime else 0

        routing_confidence = _derive_routing_confidence(
            best_ret,
            worst_ret,
            num_trades,
            len(allowed_regimes) + len(allowed_sessions),
            len(blocked_regimes) + len(blocked_sessions),
        )
        specialist_score = round(min(1.0, max(0.0, 0.55 * routing_confidence)), 4)

        meta.update({
            "routing_confidence": routing_confidence,
            "specialist_score": specialist_score,
            "avg_regime_confidence": 0.0,
            "allowed_regimes": sorted(allowed_regimes),
            "blocked_regimes": sorted(blocked_regimes),
            "allowed_sessions": sorted(allowed_sessions),
            "blocked_sessions": sorted(blocked_sessions),
            "best_session": best_session,
            "worst_session": worst_session,
            "best_session_return_pct": session_rets.get(best_session, 0) if best_session else 0,
            "worst_session_return_pct": session_rets.get(worst_session, 0) if worst_session else 0,
        })
        explain["meta"] = meta
        stats["strategy_explain"] = explain
        rec.stats = stats
        repaired += 1

    save_pool(pool)
    print(f"Repaired {repaired} legacy records")


if __name__ == "__main__":
    repair_legacy_metadata()
