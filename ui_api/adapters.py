from __future__ import annotations

import json
import re
from collections import Counter, defaultdict, deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

from ..execution.audit_utils import POOL_AUDIT_TRAIL_PATH, UNMATCHED_CLOSED_DEALS_PATH
from ..execution.live_state_utils import LIVE_STATE_PATH
from ..execution.strategy_live_stats import STATS_PATH
from ..strategies.live_manifest import LIVE_MANIFEST_PATH, STRATEGY_INDEX_PATH, load_live_manifest, load_strategy_index
from ..strategies.pool import POOL_STATE_PATH, load_pool, summarize_status_counts

BASE_DIR = Path(__file__).resolve().parent.parent
EXECUTION_DIR = BASE_DIR / "execution"
OPEN_TRADES_PATH = EXECUTION_DIR / "open_trades.json"
TRADES_LOG_PATH = EXECUTION_DIR / "trades.log"

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
            "manifest_generated_at": manifest_summary["generated_at"],
            "index_generated_at": index_summary["generated_at"],
            "index_tier_counts": index_summary["tier_counts"],
        },
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
    top_strategies = sorted(pool.strategies.values(), key=lambda rec: float(rec.score or 0.0), reverse=True)[:15]
    for rec in pool.strategies.values():
        by_slot[(rec.symbol, rec.timeframe)] += 1
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
    return {
        "name": name,
        "manifest_entry": manifest_entry,
        "index_entry": index_entry,
        "pool_record": pool_rec.to_dict() if pool_rec else None,
        "live_stats": stats,
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
