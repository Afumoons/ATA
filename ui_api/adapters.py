from __future__ import annotations

import json
import re
from collections import Counter, defaultdict, deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

try:
    from ..execution.audit_utils import POOL_AUDIT_TRAIL_PATH, UNMATCHED_CLOSED_DEALS_PATH
    from ..execution.live_state_utils import LIVE_STATE_PATH
    from ..execution.strategy_live_stats import STATS_PATH
    from ..strategies.live_manifest import LIVE_MANIFEST_PATH, STRATEGY_INDEX_PATH, load_live_manifest, load_strategy_index
    from ..strategies.pool import POOL_STATE_PATH, load_pool, summarize_status_counts
except ImportError:
    from execution.audit_utils import POOL_AUDIT_TRAIL_PATH, UNMATCHED_CLOSED_DEALS_PATH
    from execution.live_state_utils import LIVE_STATE_PATH
    from execution.strategy_live_stats import STATS_PATH
    from strategies.live_manifest import LIVE_MANIFEST_PATH, STRATEGY_INDEX_PATH, load_live_manifest, load_strategy_index
    from strategies.pool import POOL_STATE_PATH, load_pool, summarize_status_counts

BASE_DIR = Path(__file__).resolve().parent.parent
EXECUTION_DIR = BASE_DIR / "execution"
OPEN_TRADES_PATH = EXECUTION_DIR / "open_trades.json"
TRADES_LOG_PATH = EXECUTION_DIR / "trades.log"
RESEARCH_SUMMARY_DIR = BASE_DIR / "research" / "family_stage"

TRADE_LOG_PATTERN = re.compile(r"(\w+)=([^\s]+)")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def read_json_file(path: Path, *, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def load_live_state_snapshot() -> Dict[str, Any]:
    data = read_json_file(LIVE_STATE_PATH, default={})
    return data if isinstance(data, dict) else {}


def load_pool_summary() -> Dict[str, Any]:
    pool = load_pool()
    return {
        "path": str(POOL_STATE_PATH),
        "total": len(pool.strategies),
        "status_counts": summarize_status_counts(pool.strategies),
    }


def load_manifest_summary() -> Dict[str, Any]:
    manifest = load_live_manifest(LIVE_MANIFEST_PATH)
    entries = manifest.get("entries") or []
    slot_counts: Counter[Tuple[str, str]] = Counter(
        (str(entry.get("symbol") or ""), str(entry.get("timeframe") or ""))
        for entry in entries
    )
    slots = [
        {"symbol": symbol, "timeframe": timeframe, "count": count}
        for (symbol, timeframe), count in sorted(slot_counts.items())
    ]
    return {
        "entry_count": int(manifest.get("entry_count", 0) or 0),
        "generated_at": manifest.get("generated_at"),
        "slots": slots,
    }


def load_strategy_index_summary() -> Dict[str, Any]:
    index = load_strategy_index(STRATEGY_INDEX_PATH)
    entries = index.get("entries") or []
    tier_counts = Counter(str(entry.get("tier") or "unknown") for entry in entries)
    return {
        "entry_count": int(index.get("entry_count", 0) or 0),
        "generated_at": index.get("generated_at"),
        "tier_counts": dict(sorted(tier_counts.items())),
    }


def build_overview_payload() -> Dict[str, Any]:
    live_state = load_live_state_snapshot()
    pool_summary = load_pool_summary()
    manifest_summary = load_manifest_summary()
    index_summary = load_strategy_index_summary()
    execution_summary = load_execution_summary()

    attention_queue: List[Dict[str, Any]] = []
    unmatched = int(((execution_summary.get("unmatched_closed_deals") or {}).get("count", 0)) or 0)
    if unmatched > 0:
        attention_queue.append({
            "label": "Unmatched closed deals",
            "tone": "critical" if unmatched >= 5 else "warning",
            "value": unmatched,
            "detail": "Closed-deal reconciliation needs operator review.",
        })

    open_trades = int(((execution_summary.get("open_trades") or {}).get("count", 0)) or 0)
    if not bool(live_state.get("locked_for_day")) and open_trades == 0:
        attention_queue.append({
            "label": "No open trades",
            "tone": "warning",
            "value": 0,
            "detail": "Trading day is active but the execution snapshot shows no open positions.",
        })

    manifest_generated_at = manifest_summary.get("generated_at")
    index_generated_at = index_summary.get("generated_at")
    if manifest_generated_at != index_generated_at:
        attention_queue.append({
            "label": "Artifact freshness mismatch",
            "tone": "warning",
            "value": 2,
            "detail": "Manifest and strategy index were not generated at the same timestamp.",
        })

    return {
        "generated_at": utc_now_iso(),
        "live_state_date": live_state.get("date"),
        "equity_current": live_state.get("equity_current"),
        "daily_pnl": live_state.get("daily_pnl"),
        "trades_today": live_state.get("trades_today"),
        "locked_for_day": live_state.get("locked_for_day"),
        "pool_total": pool_summary["total"],
        "pool_status_counts": pool_summary["status_counts"],
        "manifest_entry_count": manifest_summary["entry_count"],
        "strategy_index_entry_count": index_summary["entry_count"],
        "live_slots": manifest_summary["slots"],
        "diagnostics": {
            "pool_path": pool_summary["path"],
            "manifest_generated_at": manifest_generated_at,
            "index_generated_at": index_generated_at,
            "index_tier_counts": index_summary["tier_counts"],
        },
        "attention_queue": attention_queue,
    }


def load_manifest_payload() -> Dict[str, Any]:
    manifest = load_live_manifest(LIVE_MANIFEST_PATH)
    entries = manifest.get("entries") or []
    manifest["entries"] = [dict(entry) for entry in entries if isinstance(entry, dict)]
    manifest["entry_count"] = int(manifest.get("entry_count", len(manifest["entries"])) or 0)
    return manifest


def load_manifest_entries() -> List[Dict[str, Any]]:
    return load_manifest_payload()["entries"]


def load_strategy_index_payload() -> Dict[str, Any]:
    index = load_strategy_index(STRATEGY_INDEX_PATH)
    entries = index.get("entries") or []
    index["entries"] = [dict(entry) for entry in entries if isinstance(entry, dict)]
    index["entry_count"] = int(index.get("entry_count", len(index["entries"])) or 0)
    return index


def load_strategy_index_entries() -> List[Dict[str, Any]]:
    return load_strategy_index_payload()["entries"]


def load_strategy_live_stats_snapshot() -> Dict[str, Any]:
    data = read_json_file(STATS_PATH, default={})
    strategies = data.get("strategies") if isinstance(data, dict) else {}
    if not isinstance(strategies, dict):
        strategies = {}
    total_pnl = sum(float((row or {}).get("total_pnl", 0.0) or 0.0) for row in strategies.values())
    total_trades = sum(int((row or {}).get("num_trades", 0) or 0) for row in strategies.values())
    ranked = sorted(
        (
            {
                "name": name,
                "total_pnl": float((row or {}).get("total_pnl", 0.0) or 0.0),
                "num_trades": int((row or {}).get("num_trades", 0) or 0),
                "last_update": (row or {}).get("last_update"),
                "recent_pnls": list((row or {}).get("recent_pnls") or []),
            }
            for name, row in strategies.items()
        ),
        key=lambda row: (row["num_trades"], row["total_pnl"]),
        reverse=True,
    )
    return {
        "strategy_count": len(strategies),
        "total_realized_pnl": total_pnl,
        "total_trades": total_trades,
        "top_active": ranked[:10],
        "strategies": strategies,
    }


def load_open_trades_snapshot() -> Dict[str, Any]:
    data = read_json_file(OPEN_TRADES_PATH, default=[])
    trades: List[Dict[str, Any]]
    if isinstance(data, list):
        trades = [dict(row) for row in data if isinstance(row, dict)]
    elif isinstance(data, dict):
        raw = data.get("trades") or []
        trades = [dict(row) for row in raw if isinstance(row, dict)]
    else:
        trades = []
    return {"count": len(trades), "trades": trades}


def _iter_recent_lines(path: Path, limit: int) -> Iterable[str]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", errors="replace") as f:
        return list(deque((line.rstrip("\n") for line in f), maxlen=limit))


def load_recent_trade_log(limit: int = 30) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for line in _iter_recent_lines(TRADES_LOG_PATH, limit):
        parsed = {match.group(1): match.group(2) for match in TRADE_LOG_PATTERN.finditer(line)}
        parsed["raw"] = line
        rows.append(parsed)
    return rows


def load_execution_summary() -> Dict[str, Any]:
    live_state = load_live_state_snapshot()
    live_stats = load_strategy_live_stats_snapshot()
    open_trades = load_open_trades_snapshot()
    unmatched_rows = read_json_file(UNMATCHED_CLOSED_DEALS_PATH, default=[])
    if not isinstance(unmatched_rows, list):
        unmatched_rows = []
    return {
        "generated_at": utc_now_iso(),
        "live_state": live_state,
        "strategy_live_stats": {
            "strategy_count": live_stats["strategy_count"],
            "total_realized_pnl": live_stats["total_realized_pnl"],
            "total_trades": live_stats["total_trades"],
            "top_active": live_stats["top_active"],
        },
        "open_trades": open_trades,
        "unmatched_closed_deals": {
            "count": len(unmatched_rows),
            "recent": unmatched_rows[-20:],
        },
        "recent_trade_log": load_recent_trade_log(),
    }


def load_pool_summary_payload() -> Dict[str, Any]:
    pool = load_pool()
    by_slot: Dict[Tuple[str, str], int] = defaultdict(int)
    family_counts: Counter[str] = Counter()
    symbol_counts: Counter[str] = Counter()
    top_strategies = sorted(pool.strategies.values(), key=lambda rec: float(rec.score or 0.0), reverse=True)[:15]
    for rec in pool.strategies.values():
        by_slot[(rec.symbol, rec.timeframe)] += 1
        symbol_counts[str(rec.symbol or "unknown")] += 1
        family = str((((rec.stats or {}).get("strategy") or {}).get("family") or ((rec.stats or {}).get("family")) or "unknown"))
        family_counts[family] += 1
    return {
        "generated_at": utc_now_iso(),
        "total": len(pool.strategies),
        "status_counts": summarize_status_counts(pool.strategies),
        "by_slot": [
            {"symbol": symbol, "timeframe": timeframe, "count": count}
            for (symbol, timeframe), count in sorted(by_slot.items())
        ],
        "top_strategies": [
            {
                "name": rec.name,
                "symbol": rec.symbol,
                "timeframe": rec.timeframe,
                "status": rec.status,
                "score": rec.score,
            }
            for rec in top_strategies
        ],
        "family_counts": dict(sorted(family_counts.items())),
        "symbol_counts": dict(sorted(symbol_counts.items())),
    }


def load_strategies_summary() -> List[Dict[str, Any]]:
    manifest_by_name = {entry.get("name"): entry for entry in load_manifest_entries()}
    pool = load_pool()
    rows: List[Dict[str, Any]] = []
    for entry in load_strategy_index_entries():
        name = str(entry.get("name") or "")
        pool_rec = pool.strategies.get(name)
        rows.append({
            **entry,
            "in_manifest": name in manifest_by_name,
            "pool_score": float(pool_rec.score) if pool_rec else None,
        })
    return rows


def load_strategy_detail(name: str) -> Dict[str, Any] | None:
    manifest_entry = next((entry for entry in load_manifest_entries() if entry.get("name") == name), None)
    index_entry = next((entry for entry in load_strategy_index_entries() if entry.get("name") == name), None)
    pool = load_pool()
    pool_rec = pool.strategies.get(name)
    stats = load_strategy_live_stats_snapshot().get("strategies", {}).get(name)
    if not any([manifest_entry, index_entry, pool_rec, stats]):
        return None

    pool_dict = pool_rec.to_dict() if pool_rec else None
    stats_block = ((pool_dict or {}).get("stats") or {}) if isinstance(pool_dict, dict) else {}
    explain = ((stats_block.get("strategy_explain") or {}) if isinstance(stats_block, dict) else {})
    regime_pnl = explain.get("regime_pnl") or {}
    session_pnl = explain.get("session_pnl") or {}
    meta = explain.get("meta") or {}
    stability = explain.get("stability") or {}
    live_total_pnl = float(((stats or {}).get("total_pnl", 0.0)) or 0.0) if isinstance(stats, dict) else 0.0
    research_return_pct = float((stats_block.get("return_pct", 0.0)) or 0.0) if isinstance(stats_block, dict) else 0.0

    derived = {
        "best_regime": meta.get("best_regime"),
        "worst_regime": meta.get("worst_regime"),
        "best_session": meta.get("best_session"),
        "worst_session": meta.get("worst_session"),
        "routing_confidence": meta.get("routing_confidence"),
        "specialist_score": meta.get("specialist_score"),
        "regime_pnl": regime_pnl,
        "session_pnl": session_pnl,
        "stability": stability,
        "live_vs_research_delta": live_total_pnl - research_return_pct,
        "live_total_pnl": live_total_pnl,
        "research_return_pct": research_return_pct,
    }

    return {
        "name": name,
        "manifest_entry": manifest_entry,
        "index_entry": index_entry,
        "pool_record": pool_dict,
        "live_stats": stats,
        "derived": derived,
    }


def load_research_summary(symbol: str = "XAUUSDm", timeframe: str = "M15") -> Dict[str, Any] | None:
    path = RESEARCH_SUMMARY_DIR / f"{symbol}_{timeframe}.json"
    payload = read_json_file(path, default=None)
    if not isinstance(payload, dict):
        return None

    families = payload.get("families") or {}
    funnel_totals: Counter[str] = Counter()
    rejection_totals: Counter[str] = Counter()
    top_rejection_samples: Dict[str, List[str]] = {}

    for family_name, family_payload in families.items():
        if not isinstance(family_payload, dict):
            continue
        stages = family_payload.get("stages") or {}
        skips = family_payload.get("skip_reasons") or {}
        samples = family_payload.get("skip_samples") or {}
        for key, value in stages.items():
            try:
                funnel_totals[key] += int(value or 0)
            except Exception:
                pass
        for key, value in skips.items():
            try:
                rejection_totals[key] += int(value or 0)
            except Exception:
                pass
        for key, value in samples.items():
            if key not in top_rejection_samples and isinstance(value, list):
                top_rejection_samples[key] = value[:3]

    return {
        "generated_at": payload.get("generated_at") or utc_now_iso(),
        "symbol": payload.get("symbol") or symbol,
        "timeframe": payload.get("timeframe") or timeframe,
        "families": families,
        "funnel_totals": dict(sorted(funnel_totals.items())),
        "rejection_totals": dict(sorted(rejection_totals.items(), key=lambda item: item[1], reverse=True)),
        "top_rejection_samples": top_rejection_samples,
    }


def load_drift_summary() -> Dict[str, Any]:
    pool = load_pool()
    live_stats = load_strategy_live_stats_snapshot().get("strategies", {})
    rows: List[Dict[str, Any]] = []
    symbols: Counter[str] = Counter()
    families: Counter[str] = Counter()
    statuses: Counter[str] = Counter()
    severities: Counter[str] = Counter()

    for name, rec in pool.strategies.items():
        stats = rec.stats or {}
        explain = (stats.get("strategy_explain") or {}) if isinstance(stats, dict) else {}
        meta = (explain.get("meta") or {}) if isinstance(explain, dict) else {}
        live = live_stats.get(name) or {}

        research_return_pct = float(stats.get("return_pct", 0.0) or 0.0)
        research_sharpe = float(stats.get("sharpe_ratio", 0.0) or 0.0)
        live_total_pnl = float((live.get("total_pnl", 0.0) or 0.0)) if isinstance(live, dict) else 0.0
        live_trades = int((live.get("num_trades", 0) or 0)) if isinstance(live, dict) else 0
        recent_pnls_raw = list((live.get("recent_pnls") or [])) if isinstance(live, dict) else []
        recent_pnls = [float(x or 0.0) for x in recent_pnls_raw]
        recent_avg = (sum(recent_pnls) / len(recent_pnls)) if recent_pnls else 0.0
        drift_score = abs(live_total_pnl - research_return_pct)
        decay_warning = live_trades >= 3 and recent_avg < 0

        severity = "healthy"
        if decay_warning or drift_score >= 20 or recent_avg <= -5:
            severity = "broken"
        elif drift_score >= 10 or recent_avg < 0:
            severity = "drifting"
        elif drift_score >= 3 or live_trades == 0:
            severity = "watch"

        family = ((stats.get("strategy") or {}).get("family") if isinstance(stats, dict) else None) or stats.get("family") or "unknown"
        symbol = str(rec.symbol or "unknown")
        status = str(rec.status or "unknown")

        symbols[symbol] += 1
        families[str(family)] += 1
        statuses[status] += 1
        severities[severity] += 1

        rows.append({
            "name": name,
            "symbol": rec.symbol,
            "timeframe": rec.timeframe,
            "status": rec.status,
            "family": family,
            "research_return_pct": research_return_pct,
            "research_sharpe": research_sharpe,
            "live_total_pnl": live_total_pnl,
            "live_trades": live_trades,
            "recent_avg_pnl": recent_avg,
            "recent_pnls": recent_pnls,
            "best_regime": meta.get("best_regime"),
            "worst_regime": meta.get("worst_regime"),
            "drift_score": drift_score,
            "decay_warning": decay_warning,
            "severity": severity,
            "last_update": live.get("last_update") if isinstance(live, dict) else None,
        })

    rows.sort(key=lambda row: (float({"healthy": 0, "watch": 1, "drifting": 2, "broken": 3}.get(str(row.get("severity")), 0)), bool(row.get("decay_warning")), float(row.get("drift_score", 0.0))), reverse=True)
    attention = [row for row in rows if row.get("severity") in {"drifting", "broken"} or row.get("decay_warning") or abs(float(row.get("recent_avg_pnl", 0.0))) > 0]

    return {
        "generated_at": utc_now_iso(),
        "rows": rows[:50],
        "summary": {
            "strategy_count": len(rows),
            "attention_count": len(attention),
            "decay_warning_count": sum(1 for row in rows if row.get("decay_warning")),
            "negative_recent_avg_count": sum(1 for row in rows if float(row.get("recent_avg_pnl", 0.0)) < 0),
            "severity_counts": dict(sorted(severities.items())),
            "available_filters": {
                "symbols": sorted(symbols.keys()),
                "families": sorted(families.keys()),
                "statuses": sorted(statuses.keys()),
                "severities": ["healthy", "watch", "drifting", "broken"],
            },
        },
    }


def load_audit_timeline(limit: int = 100) -> Dict[str, Any]:
    pool_rows = read_json_file(POOL_AUDIT_TRAIL_PATH, default=[])
    unmatched_rows = read_json_file(UNMATCHED_CLOSED_DEALS_PATH, default=[])
    if not isinstance(pool_rows, list):
        pool_rows = []
    if not isinstance(unmatched_rows, list):
        unmatched_rows = []

    events: List[Dict[str, Any]] = []
    for row in pool_rows[-limit:]:
        if isinstance(row, dict):
            events.append({"source": "pool_audit", **row})
    for row in unmatched_rows[-limit:]:
        if isinstance(row, dict):
            events.append({"source": "unmatched_closed_deal", **row})
    for row in load_recent_trade_log(limit=limit):
        events.append({"source": "trades_log", **row})

    events.sort(key=lambda row: str(row.get("recorded_at") or row.get("last_update") or row.get("raw") or ""), reverse=True)
    return {
        "generated_at": utc_now_iso(),
        "events": events[:limit],
    }
