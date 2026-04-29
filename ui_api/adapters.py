from __future__ import annotations

import json
import re
from collections import Counter, defaultdict, deque
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

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
RESEARCH_SUMMARY_DIR = BASE_DIR / "tmp" / "research_family_stage_summaries"

TRADE_LOG_PATTERN = re.compile(r"(\w+)=([^\s]+)")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def parse_iso_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def read_json_file(path: Path, *, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def list_research_summary_artifacts() -> Dict[str, List[str]]:
    symbol_to_timeframes: Dict[str, set[str]] = defaultdict(set)
    if not RESEARCH_SUMMARY_DIR.exists():
        return {"symbols": [], "timeframes": []}

    for path in RESEARCH_SUMMARY_DIR.glob("*.json"):
        stem = path.stem
        if "_" not in stem:
            continue
        symbol, timeframe = stem.rsplit("_", 1)
        if not symbol or not timeframe:
            continue
        symbol_to_timeframes[symbol].add(timeframe)

    all_timeframes = sorted({timeframe for values in symbol_to_timeframes.values() for timeframe in values})
    return {
        "symbols": sorted(symbol_to_timeframes.keys()),
        "timeframes": all_timeframes,
        "timeframes_by_symbol": {symbol: sorted(values) for symbol, values in sorted(symbol_to_timeframes.items())},
    }


def _humanize_token(value: Any, fallback: str = "unknown") -> str:
    text = str(value or "").strip()
    if not text:
        return fallback
    return text.replace("_", " ")


def _format_reason_sentence(reason: Any) -> str:
    text = _humanize_token(reason, fallback="no explicit reason recorded")
    return text[0].upper() + text[1:] if text else "No explicit reason recorded"


def _safe_float(value: Any) -> Optional[float]:
    try:
        return float(value)
    except Exception:
        return None


def _safe_int(value: Any) -> Optional[int]:
    try:
        return int(value)
    except Exception:
        return None


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
    live_decay = (stats_block.get("live_decay") or {}) if isinstance(stats_block, dict) else {}
    live_total_pnl = float(((stats or {}).get("total_pnl", 0.0)) or 0.0) if isinstance(stats, dict) else 0.0
    research_return_pct = float((stats_block.get("return_pct", 0.0)) or 0.0) if isinstance(stats_block, dict) else 0.0
    research_sharpe = float((stats_block.get("sharpe_ratio", 0.0)) or 0.0) if isinstance(stats_block, dict) else 0.0

    audit_rows = read_json_file(POOL_AUDIT_TRAIL_PATH, default=[])
    if not isinstance(audit_rows, list):
        audit_rows = []

    transition_history: List[Dict[str, Any]] = []
    strategy_events: List[Dict[str, Any]] = []
    latest_reason_text: Optional[str] = None
    latest_reason_source = "heuristic"
    latest_reason_at: Optional[str] = None

    for row in reversed(audit_rows):
        if not isinstance(row, dict):
            continue

        event = str(row.get("event") or "")
        recorded_at = row.get("recorded_at")
        direct_match = str(row.get("strategy_name") or "") == name

        if direct_match:
            strategy_events.append({
                "recorded_at": recorded_at,
                "event": event,
                "reason": row.get("reason"),
                "status": row.get("status"),
                "old_status": row.get("old_status") or row.get("from_status"),
                "new_status": row.get("new_status") or row.get("to_status"),
                "metrics": row.get("metrics"),
            })

        if direct_match and event == "live_decay_degrade":
            transition_history.append({
                "recorded_at": recorded_at,
                "event": event,
                "from_status": row.get("old_status") or row.get("from_status"),
                "to_status": row.get("new_status") or row.get("to_status"),
                "reason": row.get("reason"),
                "summary": f"{_humanize_token(row.get('old_status'))} → {_humanize_token(row.get('new_status'))}",
                "source": "live_decay",
            })
        elif direct_match and row.get("old_status") and row.get("new_status"):
            transition_history.append({
                "recorded_at": recorded_at,
                "event": event,
                "from_status": row.get("old_status") or row.get("from_status"),
                "to_status": row.get("new_status") or row.get("to_status"),
                "reason": row.get("reason"),
                "summary": f"{_humanize_token(row.get('old_status'))} → {_humanize_token(row.get('new_status'))}",
                "source": "pool_audit",
            })

        if event == "circuit_breaker_disable":
            disabled_entries = row.get("disabled_entries") or []
            if isinstance(disabled_entries, list):
                for entry in disabled_entries:
                    if not isinstance(entry, str) or not entry.startswith(f"{name}:"):
                        continue
                    previous_status = entry.split(":", 1)[1] or "live"
                    dd_pct = _safe_float(row.get("dd_pct"))
                    threshold = _safe_float(row.get("threshold"))
                    reason = (
                        f"portfolio drawdown {dd_pct:.2f}% exceeded threshold {threshold:.2f}%"
                        if dd_pct is not None and threshold is not None
                        else "portfolio drawdown exceeded circuit-breaker threshold"
                    )
                    transition_history.append({
                        "recorded_at": recorded_at,
                        "event": event,
                        "from_status": previous_status,
                        "to_status": "disabled",
                        "reason": reason,
                        "summary": f"{_humanize_token(previous_status)} → disabled",
                        "source": "circuit_breaker",
                    })
                    strategy_events.append({
                        "recorded_at": recorded_at,
                        "event": event,
                        "reason": reason,
                        "status": "disabled",
                        "old_status": previous_status,
                        "new_status": "disabled",
                        "metrics": {
                            "dd_pct": row.get("dd_pct"),
                            "threshold": row.get("threshold"),
                        },
                    })

    transition_history.sort(key=lambda item: str(item.get("recorded_at") or ""), reverse=True)
    strategy_events.sort(key=lambda item: str(item.get("recorded_at") or ""), reverse=True)

    current_status = str((manifest_entry or {}).get("status") or (index_entry or {}).get("status") or (pool_dict or {}).get("status") or "unknown")
    current_tier = str((index_entry or {}).get("tier") or (manifest_entry or {}).get("tier") or "unknown")
    manifest_rank = (manifest_entry or {}).get("manifest_rank")
    decay_warning_count = sum(1 for event in strategy_events if event.get("event") == "live_decay_warning")
    latest_warning = next((event for event in strategy_events if event.get("event") == "live_decay_warning"), None)
    latest_transition = transition_history[0] if transition_history else None

    if latest_transition:
        latest_reason_text = _format_reason_sentence(latest_transition.get("reason"))
        latest_reason_source = str(latest_transition.get("source") or "pool_audit")
        latest_reason_at = latest_transition.get("recorded_at")
    elif latest_warning:
        latest_reason_text = _format_reason_sentence(latest_warning.get("reason"))
        latest_reason_source = "live_decay_warning"
        latest_reason_at = latest_warning.get("recorded_at")

    if not latest_reason_text and isinstance(pool_dict, dict):
        circuit_disabled_at = stats_block.get("circuit_breaker_disabled_at")
        circuit_prev_status = stats_block.get("circuit_breaker_previous_status")
        circuit_dd_pct = _safe_float(stats_block.get("circuit_breaker_dd_pct"))
        circuit_threshold = _safe_float(stats_block.get("circuit_breaker_threshold"))
        if circuit_disabled_at and current_status == "disabled":
            latest_reason_text = (
                f"Disabled by circuit breaker after portfolio drawdown {circuit_dd_pct:.2f}% crossed {circuit_threshold:.2f}%"
                if circuit_dd_pct is not None and circuit_threshold is not None
                else "Disabled by circuit breaker"
            )
            latest_reason_source = "circuit_breaker_snapshot"
            latest_reason_at = circuit_disabled_at
            transition_history.insert(0, {
                "recorded_at": circuit_disabled_at,
                "event": "circuit_breaker_snapshot",
                "from_status": circuit_prev_status,
                "to_status": "disabled",
                "reason": latest_reason_text,
                "summary": f"{_humanize_token(circuit_prev_status, fallback='live')} → disabled",
                "source": "pool_snapshot",
            })
            transition_history.sort(key=lambda item: str(item.get("recorded_at") or ""), reverse=True)

    latest_transition = transition_history[0] if transition_history else None

    family = str((manifest_entry or {}).get("family") or (index_entry or {}).get("family") or (stats_block.get("strategy") or {}).get("family") or stats_block.get("family") or "unknown")
    best_regime = meta.get("best_regime")
    routing_confidence = _safe_float(meta.get("routing_confidence"))
    specialist_score = _safe_float(meta.get("specialist_score"))
    live_trade_count = _safe_int(((stats or {}).get("num_trades")) if isinstance(stats, dict) else None) or 0
    live_vs_research_delta = live_total_pnl - research_return_pct

    explanation_parts: List[str] = []
    if current_status == "active":
        explanation_parts.append("Active because it is currently deployed in the live manifest")
        if manifest_rank is not None:
            explanation_parts.append(f"ranked #{int(manifest_rank)} within its live slot")
        explanation_parts.append(f"with {family} research edge at {research_return_pct:.2f}% return and {research_sharpe:.2f} sharpe")
    elif current_status == "exploratory":
        explanation_parts.append("Exploratory because it is still live-eligible but running in a lower-conviction posture")
        if manifest_rank is not None:
            explanation_parts.append(f"currently occupying live manifest rank #{int(manifest_rank)}")
        explanation_parts.append(f"while the backend keeps it visible for {family} regime coverage")
    elif current_status == "candidate":
        explanation_parts.append("Candidate because it remains in the research inventory but is not currently promoted into the live manifest")
        explanation_parts.append(f"Its research profile is {research_return_pct:.2f}% return and {research_sharpe:.2f} sharpe")
        explanation_parts.append(f"so it stays available for future promotion in the {family} family")
    elif current_status == "disabled":
        explanation_parts.append("Disabled because it is not currently eligible for live routing")
        if latest_reason_text:
            explanation_parts.append(latest_reason_text.lower())
        elif current_tier == "archive" or bool((index_entry or {}).get("archived")):
            explanation_parts.append("and it has already fallen into the archive tier")
    else:
        explanation_parts.append(f"Current status is {_humanize_token(current_status)} based on the latest pool snapshot")

    if routing_confidence is not None or specialist_score is not None:
        explanation_parts.append(
            f"Routing confidence {routing_confidence:.2f} and specialist score {specialist_score:.2f} frame its operator posture"
            if routing_confidence is not None and specialist_score is not None
            else f"Routing confidence {routing_confidence:.2f} helps frame its operator posture"
            if routing_confidence is not None
            else f"Specialist score {specialist_score:.2f} helps frame its operator posture"
        )

    if best_regime:
        explanation_parts.append(f"Best research regime is {_humanize_token(best_regime)}")

    if latest_warning:
        explanation_parts.append(f"Latest live warning: {_humanize_token(latest_warning.get('reason'), fallback='warning recorded')}")
    elif isinstance(live_decay, dict) and live_decay.get("reason"):
        explanation_parts.append(f"Latest live warning: {_humanize_token(live_decay.get('reason'), fallback='warning recorded')}")

    if live_trade_count > 0:
        explanation_parts.append(f"Live counters show {live_trade_count} recorded trades and a {live_vs_research_delta:.2f} live-vs-research delta")

    decision_explanation = ". ".join(part.rstrip(".") for part in explanation_parts if part).strip()
    if decision_explanation and not decision_explanation.endswith("."):
        decision_explanation += "."

    if not latest_reason_text:
        if current_status == "active":
            latest_reason_text = "Live manifest retained this strategy in the active set"
        elif current_status == "exploratory":
            latest_reason_text = "Live manifest retained this strategy as exploratory coverage"
        elif current_status == "candidate":
            latest_reason_text = "Research inventory retained this strategy as a promotion candidate"
        elif current_status == "disabled":
            latest_reason_text = "Current pool snapshot keeps this strategy disabled"
        else:
            latest_reason_text = f"Current pool snapshot reports status {_humanize_token(current_status)}"

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
        "research_sharpe": research_sharpe,
        "decision_context": {
            "current_status": current_status,
            "current_tier": current_tier,
            "manifest_rank": manifest_rank,
            "in_manifest": bool(manifest_entry),
            "archived": bool((index_entry or {}).get("archived")),
            "latest_reason": latest_reason_text,
            "latest_reason_source": latest_reason_source,
            "latest_reason_at": latest_reason_at,
            "latest_transition": latest_transition,
            "transition_history": transition_history[:8],
            "strategy_events": strategy_events[:8],
            "decision_explanation": decision_explanation,
            "decision_label": f"{_humanize_token(current_status).title()} posture",
            "decay_warning_count": decay_warning_count,
        },
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
    artifacts = list_research_summary_artifacts()
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
        "available_filters": artifacts,
    }


def load_drift_summary() -> Dict[str, Any]:
    pool = load_pool()
    live_stats = load_strategy_live_stats_snapshot().get("strategies", {})
    audit_rows = read_json_file(POOL_AUDIT_TRAIL_PATH, default=[])
    unmatched_rows = read_json_file(UNMATCHED_CLOSED_DEALS_PATH, default=[])
    if not isinstance(audit_rows, list):
        audit_rows = []
    if not isinstance(unmatched_rows, list):
        unmatched_rows = []

    decay_warning_counts: Counter[str] = Counter()
    latest_decay_reason: Dict[str, str] = {}
    for row in audit_rows:
        if not isinstance(row, dict) or row.get("event") != "live_decay_warning":
            continue
        strategy_name = str(row.get("strategy_name") or "")
        if not strategy_name:
            continue
        decay_warning_counts[strategy_name] += 1
        if strategy_name not in latest_decay_reason:
            latest_decay_reason[strategy_name] = str(row.get("reason") or "live_decay_warning")

    unmatched_counts: Counter[str] = Counter()
    unmatched_without_strategy = 0
    for row in unmatched_rows:
        if not isinstance(row, dict):
            continue
        strategy_name = str(row.get("strategy_name") or row.get("strategy") or "")
        if strategy_name:
            unmatched_counts[strategy_name] += 1
        else:
            unmatched_without_strategy += 1

    rows: List[Dict[str, Any]] = []
    symbols: Counter[str] = Counter()
    families: Counter[str] = Counter()
    statuses: Counter[str] = Counter()
    severities: Counter[str] = Counter()
    regime_alignment_counts: Counter[str] = Counter()
    unresolved_anomaly_groups: Counter[str] = Counter()
    now = datetime.now(timezone.utc)
    stale_threshold = now - timedelta(hours=12)

    def pick_live_observed_regime(explain: Dict[str, Any]) -> Optional[str]:
        live_meta = explain.get("live_meta") or {}
        if isinstance(live_meta, dict):
            best_regime = live_meta.get("best_regime")
            if best_regime:
                return str(best_regime)

        live_regime_pnl = explain.get("live_regime_pnl") or {}
        if not isinstance(live_regime_pnl, dict):
            return None

        ranked_live_regimes: List[Tuple[int, float, str]] = []
        for label, stats in live_regime_pnl.items():
            if not isinstance(stats, dict):
                continue
            ranked_live_regimes.append((
                int(stats.get("num_trades", 0) or 0),
                float(stats.get("total_pnl", 0.0) or 0.0),
                str(label),
            ))
        if not ranked_live_regimes:
            return None
        ranked_live_regimes.sort(key=lambda item: (item[0], abs(item[1]), item[1]), reverse=True)
        return ranked_live_regimes[0][2]

    for name, rec in pool.strategies.items():
        stats = rec.stats or {}
        explain = (stats.get("strategy_explain") or {}) if isinstance(stats, dict) else {}
        meta = (explain.get("meta") or {}) if isinstance(explain, dict) else {}
        live = live_stats.get(name) or {}
        live_missing = not isinstance(live_stats.get(name), dict)

        research_return_pct = float(stats.get("return_pct", 0.0) or 0.0)
        research_sharpe = float(stats.get("sharpe_ratio", 0.0) or 0.0)
        live_total_pnl = float((live.get("total_pnl", 0.0) or 0.0)) if isinstance(live, dict) else 0.0
        live_trades = int((live.get("num_trades", 0) or 0)) if isinstance(live, dict) else 0
        recent_pnls_raw = list((live.get("recent_pnls") or [])) if isinstance(live, dict) else []
        recent_pnls = [float(x or 0.0) for x in recent_pnls_raw]
        recent_avg = (sum(recent_pnls) / len(recent_pnls)) if recent_pnls else 0.0
        drift_score = abs(live_total_pnl - research_return_pct)
        decay_warning = live_trades >= 3 and recent_avg < 0
        research_best_regime = meta.get("best_regime")
        live_observed_regime = pick_live_observed_regime(explain) if isinstance(explain, dict) else None

        regime_alignment = "unknown"
        if research_best_regime and live_observed_regime:
            regime_alignment = "aligned" if str(research_best_regime) == str(live_observed_regime) else "mismatch"
        elif research_best_regime:
            regime_alignment = "insufficient_live_data"

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
        last_update = live.get("last_update") if isinstance(live, dict) else None
        parsed_last_update = parse_iso_datetime(last_update)
        decay_warning_count = int(decay_warning_counts.get(name, 0))

        unresolved_anomalies: List[str] = []
        if unmatched_counts.get(name, 0):
            unresolved_anomalies.append("unmatched_close")
        if live_missing:
            unresolved_anomalies.append("missing_live_stats")
        if parsed_last_update and parsed_last_update < stale_threshold:
            unresolved_anomalies.append("stale_update")

        review_reasons: List[str] = []
        if decay_warning_count >= 2:
            review_reasons.append(f"{decay_warning_count} decay warnings logged")
        if severity in {"drifting", "broken"}:
            review_reasons.append(f"severity {severity}")
        if regime_alignment == "mismatch":
            review_reasons.append("regime mismatch")
        if unmatched_counts.get(name, 0):
            review_reasons.append(f"{int(unmatched_counts[name])} unmatched closes")
        if live_missing:
            review_reasons.append("missing live stats")
        if parsed_last_update and parsed_last_update < stale_threshold:
            review_reasons.append("stale live update")
        needs_manual_review = bool(review_reasons)

        symbols[symbol] += 1
        families[str(family)] += 1
        statuses[status] += 1
        severities[severity] += 1
        regime_alignment_counts[regime_alignment] += 1
        for anomaly in unresolved_anomalies:
            unresolved_anomaly_groups[anomaly] += 1

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
            "best_regime": research_best_regime,
            "worst_regime": meta.get("worst_regime"),
            "live_observed_regime": live_observed_regime,
            "regime_alignment": regime_alignment,
            "drift_score": drift_score,
            "decay_warning": decay_warning,
            "decay_warning_count": decay_warning_count,
            "latest_decay_reason": latest_decay_reason.get(name),
            "severity": severity,
            "last_update": last_update,
            "unmatched_close_count": int(unmatched_counts.get(name, 0)),
            "unresolved_anomalies": unresolved_anomalies,
            "unresolved_anomaly_count": len(unresolved_anomalies),
            "needs_manual_review": needs_manual_review,
            "review_reasons": review_reasons,
        })

    rows.sort(key=lambda row: (float({"healthy": 0, "watch": 1, "drifting": 2, "broken": 3}.get(str(row.get("severity")), 0)), bool(row.get("decay_warning")), float(row.get("drift_score", 0.0))), reverse=True)
    attention = [row for row in rows if row.get("severity") in {"drifting", "broken"} or row.get("decay_warning") or abs(float(row.get("recent_avg_pnl", 0.0))) > 0]
    manual_review_queue = [
        row for row in sorted(
            rows,
            key=lambda row: (
                int(row.get("unresolved_anomaly_count", 0)),
                int(row.get("decay_warning_count", 0)),
                float({"healthy": 0, "watch": 1, "drifting": 2, "broken": 3}.get(str(row.get("severity")), 0)),
                float(row.get("drift_score", 0.0)),
            ),
            reverse=True,
        )
        if row.get("needs_manual_review")
    ]

    return {
        "generated_at": utc_now_iso(),
        "rows": rows[:50],
        "manual_review_queue": manual_review_queue[:15],
        "summary": {
            "strategy_count": len(rows),
            "attention_count": len(attention),
            "decay_warning_count": sum(1 for row in rows if row.get("decay_warning")),
            "repeated_decay_strategy_count": sum(1 for row in rows if int(row.get("decay_warning_count", 0)) >= 2),
            "negative_recent_avg_count": sum(1 for row in rows if float(row.get("recent_avg_pnl", 0.0)) < 0),
            "manual_review_count": len(manual_review_queue),
            "severity_counts": dict(sorted(severities.items())),
            "regime_alignment_counts": dict(sorted(regime_alignment_counts.items())),
            "unresolved_anomaly_groups": {
                **dict(sorted(unresolved_anomaly_groups.items())),
                "unmatched_without_strategy": unmatched_without_strategy,
            },
            "available_filters": {
                "symbols": sorted(symbols.keys()),
                "families": sorted(families.keys()),
                "statuses": sorted(statuses.keys()),
                "severities": ["healthy", "watch", "drifting", "broken"],
            },
        },
    }


def load_review_queue() -> Dict[str, Any]:
    pool = load_pool()
    drift_payload = load_drift_summary()
    drift_rows = drift_payload.get("rows") or []
    drift_by_name = {
        str(row.get("name") or ""): row
        for row in drift_rows
        if isinstance(row, dict) and row.get("name")
    }

    manifest_entries = load_manifest_entries()
    manifest_by_name = {
        str(entry.get("name") or ""): entry
        for entry in manifest_entries
        if isinstance(entry, dict) and entry.get("name")
    }
    index_entries = load_strategy_index_entries()
    index_by_name = {
        str(entry.get("name") or ""): entry
        for entry in index_entries
        if isinstance(entry, dict) and entry.get("name")
    }

    manifest_floor_by_slot: Dict[Tuple[str, str], float] = {}
    for entry in manifest_entries:
        if not isinstance(entry, dict):
            continue
        score = _safe_float(entry.get("score"))
        if score is None:
            continue
        slot = (str(entry.get("symbol") or "unknown"), str(entry.get("timeframe") or "unknown"))
        manifest_floor_by_slot[slot] = min(score, manifest_floor_by_slot.get(slot, score))

    rows: List[Dict[str, Any]] = []
    category_counts: Counter[str] = Counter()
    triage_counts: Counter[str] = Counter()
    status_counts: Counter[str] = Counter()
    bucket_rank = {"promote_watch": 0, "demote_watch": 1, "inspect": 2, "archive": 3}

    for name, rec in pool.strategies.items():
        manifest_entry = manifest_by_name.get(name) or {}
        index_entry = index_by_name.get(name) or {}
        drift_row = drift_by_name.get(name) or {}
        stats = rec.stats or {}
        strategy_stats = (stats.get("strategy") or {}) if isinstance(stats, dict) else {}

        symbol = str(rec.symbol or index_entry.get("symbol") or manifest_entry.get("symbol") or "unknown")
        timeframe = str(rec.timeframe or index_entry.get("timeframe") or manifest_entry.get("timeframe") or "unknown")
        status = str(rec.status or index_entry.get("status") or manifest_entry.get("status") or "unknown")
        tier = str(index_entry.get("tier") or manifest_entry.get("tier") or "unknown")
        score = _safe_float(rec.score if rec.score is not None else index_entry.get("score") or manifest_entry.get("score"))
        family_values = {
            str(value)
            for value in [
                manifest_entry.get("family"),
                index_entry.get("family"),
                strategy_stats.get("family"),
                stats.get("family") if isinstance(stats, dict) else None,
            ]
            if value not in {None, "", "unknown"}
        }
        family = next(iter(family_values), str(index_entry.get("family") or manifest_entry.get("family") or strategy_stats.get("family") or stats.get("family") or "unknown"))
        family_mismatch = len(family_values) >= 2
        regime_mismatch = str(drift_row.get("regime_alignment") or "") == "mismatch"
        severity = str(drift_row.get("severity") or "unknown")
        unresolved_anomalies = [str(value) for value in (drift_row.get("unresolved_anomalies") or []) if value]
        unmatched_close_count = int(drift_row.get("unmatched_close_count") or 0)
        unresolved_anomaly_count = int(drift_row.get("unresolved_anomaly_count") or 0)
        decay_warning_count = int(drift_row.get("decay_warning_count") or 0)
        last_update = drift_row.get("last_update")
        parsed_last_update = parse_iso_datetime(last_update)
        stale_hours = None
        if parsed_last_update is not None:
            stale_hours = max((datetime.now(timezone.utc) - parsed_last_update).total_seconds() / 3600.0, 0.0)

        slot = (symbol, timeframe)
        manifest_floor = manifest_floor_by_slot.get(slot)
        promotion_gap = None if score is None or manifest_floor is None else score - manifest_floor
        almost_accepted = (
            status == "candidate"
            and bool(stats.get("accepted"))
            and score is not None
            and manifest_floor is not None
            and promotion_gap >= -0.25
        )
        live_drifting = status in {"active", "exploratory"} and severity in {"drifting", "broken"}
        stale_but_active = status in {"active", "exploratory"} and "stale_update" in unresolved_anomalies
        repeated_reconciliation_anomalies = unmatched_close_count >= 2 or ("unmatched_close" in unresolved_anomalies and unresolved_anomaly_count >= 2)
        family_or_regime_mismatched = family_mismatch or regime_mismatch

        category_flags: List[str] = []
        triage_reasons: List[str] = []

        if almost_accepted:
            category_flags.append("almost_accepted")
            if promotion_gap is not None:
                triage_reasons.append(f"Promotion gap {promotion_gap:+.2f} vs live manifest floor")
        if live_drifting:
            category_flags.append("live_drifting")
            triage_reasons.append(f"Live severity is {severity}")
        if family_or_regime_mismatched:
            category_flags.append("family_or_regime_mismatched")
            if family_mismatch:
                triage_reasons.append("Family metadata disagrees across manifest, index, or pool")
            if regime_mismatch:
                triage_reasons.append("Research best regime disagrees with live observed regime")
        if stale_but_active:
            category_flags.append("stale_but_active")
            if stale_hours is not None:
                triage_reasons.append(f"Live update is stale by {stale_hours:.1f}h")
        if repeated_reconciliation_anomalies:
            category_flags.append("repeated_reconciliation_anomalies")
            triage_reasons.append(f"{unmatched_close_count} unmatched closes remain unresolved")

        if not category_flags:
            continue

        if status in {"disabled", "retired"} or tier == "archive":
            triage_bucket = "archive"
        elif almost_accepted:
            triage_bucket = "promote_watch"
        elif family_or_regime_mismatched or repeated_reconciliation_anomalies:
            triage_bucket = "inspect"
        elif live_drifting or stale_but_active:
            triage_bucket = "demote_watch"
        else:
            triage_bucket = "inspect"

        for category in category_flags:
            category_counts[category] += 1
        triage_counts[triage_bucket] += 1
        status_counts[status] += 1

        rows.append({
            "name": name,
            "symbol": symbol,
            "timeframe": timeframe,
            "status": status,
            "tier": tier,
            "family": family,
            "score": score,
            "manifest_rank": manifest_entry.get("manifest_rank"),
            "manifest_floor_score": manifest_floor,
            "promotion_gap": promotion_gap,
            "category_flags": category_flags,
            "triage_bucket": triage_bucket,
            "triage_reasons": triage_reasons,
            "drift_severity": drift_row.get("severity"),
            "drift_score": drift_row.get("drift_score"),
            "research_return_pct": drift_row.get("research_return_pct"),
            "live_total_pnl": drift_row.get("live_total_pnl"),
            "recent_avg_pnl": drift_row.get("recent_avg_pnl"),
            "regime_alignment": drift_row.get("regime_alignment"),
            "last_update": last_update,
            "stale_hours": stale_hours,
            "unmatched_close_count": unmatched_close_count,
            "decay_warning_count": decay_warning_count,
            "unresolved_anomaly_count": unresolved_anomaly_count,
            "family_mismatch": family_mismatch,
            "regime_mismatch": regime_mismatch,
        })

    rows.sort(
        key=lambda row: (
            bucket_rank.get(str(row.get("triage_bucket") or "inspect"), 99),
            -len(row.get("category_flags") or []),
            -float(row.get("promotion_gap") or -9999.0),
            -float(row.get("drift_score") or 0.0),
            str(row.get("name") or ""),
        )
    )

    return {
        "generated_at": utc_now_iso(),
        "rows": rows,
        "summary": {
            "queue_count": len(rows),
            "category_counts": dict(sorted(category_counts.items())),
            "triage_counts": dict(sorted(triage_counts.items())),
            "status_counts": dict(sorted(status_counts.items())),
            "available_filters": {
                "symbols": sorted({str(row.get("symbol") or "unknown") for row in rows}),
                "statuses": sorted(status_counts.keys()),
                "categories": [
                    "almost_accepted",
                    "live_drifting",
                    "family_or_regime_mismatched",
                    "stale_but_active",
                    "repeated_reconciliation_anomalies",
                ],
                "triage_buckets": ["promote_watch", "demote_watch", "inspect", "archive"],
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
