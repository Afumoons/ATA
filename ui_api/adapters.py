from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

from ..execution.live_state_utils import LIVE_STATE_PATH
from ..strategies.live_manifest import LIVE_MANIFEST_PATH, STRATEGY_INDEX_PATH, load_live_manifest, load_strategy_index
from ..strategies.pool import POOL_STATE_PATH, load_pool, summarize_status_counts

BASE_DIR = Path(__file__).resolve().parent.parent
EXECUTION_DIR = BASE_DIR / "execution"


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


def load_manifest_entries() -> List[Dict[str, Any]]:
    manifest = load_live_manifest(LIVE_MANIFEST_PATH)
    entries = manifest.get("entries") or []
    return [dict(entry) for entry in entries if isinstance(entry, dict)]


def load_strategy_index_entries() -> List[Dict[str, Any]]:
    index = load_strategy_index(STRATEGY_INDEX_PATH)
    entries = index.get("entries") or []
    return [dict(entry) for entry in entries if isinstance(entry, dict)]
