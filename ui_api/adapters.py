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
    from ..execution.manual_trade_identity import is_manual_trade_payload
    from ..execution.strategy_live_stats import STATS_PATH, is_manual_strategy_bucket
    from ..strategies.base import StrategyDefinition
    from ..strategies.live_manifest import LIVE_MANIFEST_PATH, STRATEGY_INDEX_PATH, load_live_manifest, load_strategy_index
    from ..strategies.pool import POOL_STATE_PATH, load_pool, semantic_similarity, strategy_motif, summarize_status_counts
except ImportError:
    from execution.audit_utils import POOL_AUDIT_TRAIL_PATH, UNMATCHED_CLOSED_DEALS_PATH
    from execution.live_state_utils import LIVE_STATE_PATH
    from execution.manual_trade_identity import is_manual_trade_payload
    from execution.strategy_live_stats import STATS_PATH, is_manual_strategy_bucket
    from strategies.base import StrategyDefinition
    from strategies.live_manifest import LIVE_MANIFEST_PATH, STRATEGY_INDEX_PATH, load_live_manifest, load_strategy_index
    from strategies.pool import POOL_STATE_PATH, load_pool, semantic_similarity, strategy_motif, summarize_status_counts

BASE_DIR = Path(__file__).resolve().parent.parent
EXECUTION_DIR = BASE_DIR / "execution"
OPEN_TRADES_PATH = EXECUTION_DIR / "open_trades.json"
TRADES_LOG_PATH = EXECUTION_DIR / "trades.log"
TRADE_CONTEXT_JOURNAL_PATH = EXECUTION_DIR / "trade_context_journal.json"
RESEARCH_SUMMARY_DIR = BASE_DIR / "tmp" / "research_family_stage_summaries"
LOGS_DIR = BASE_DIR / "logs"

TRADE_LOG_PATTERN = re.compile(r"(\w+)=([^\s]+)")
SYSTEM_LOG_PATTERN = re.compile(r"^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}) \[(?P<level>[A-Z]+)\] (?P<logger>[^:]+): (?P<message>.*)$")
TRADE_CONTEXT_FAILURE_PATTERN = re.compile(
    r"Failed to register trade (?P<phase>entry|exit) context for (?P<strategy>.+?) (?P<ticket_label>ticket|deal)=(?P<ticket>[^\s]+)",
    re.IGNORECASE,
)


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


def _coerce_int(value: Any) -> int:
    try:
        return int(value or 0)
    except Exception:
        return 0


def _normalize_skip_sample(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    return text.split(":", 1)[0].strip() or text


def _summarize_research_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    families = payload.get("families") or {}
    funnel_totals: Counter[str] = Counter()
    rejection_totals: Counter[str] = Counter()
    family_rows: List[Dict[str, Any]] = []
    family_skip_drilldown: List[Dict[str, Any]] = []
    top_rejection_samples: Dict[str, List[str]] = {}

    for family_name, family_payload in families.items():
        if not isinstance(family_payload, dict):
            continue
        stages = family_payload.get("stages") or {}
        skips = family_payload.get("skip_reasons") or {}
        samples = family_payload.get("skip_samples") or {}
        generated = _coerce_int(stages.get("generated"))
        accepted = _coerce_int(stages.get("accepted"))
        rejection_count = sum(_coerce_int(value) for value in skips.values())
        conversion_pct = (accepted / generated * 100.0) if generated > 0 else 0.0

        for key, value in stages.items():
            funnel_totals[key] += _coerce_int(value)
        for key, value in skips.items():
            rejection_totals[key] += _coerce_int(value)
        for key, value in samples.items():
            if key not in top_rejection_samples and isinstance(value, list):
                top_rejection_samples[key] = value[:3]

        top_rejection = "-"
        if isinstance(skips, dict) and skips:
            top_rejection = max(skips.items(), key=lambda item: _coerce_int(item[1]))[0]

        reason_rows: List[Dict[str, Any]] = []
        if isinstance(skips, dict):
            for reason, count in sorted(skips.items(), key=lambda item: (_coerce_int(item[1]), str(item[0])), reverse=True):
                samples_for_reason = samples.get(reason) if isinstance(samples, dict) else []
                if not isinstance(samples_for_reason, list):
                    samples_for_reason = []
                reason_rows.append({
                    "reason": str(reason),
                    "count": _coerce_int(count),
                    "samples": [str(sample) for sample in samples_for_reason[:3]],
                })

        family_rows.append({
            "family": str(family_name),
            "generated": generated,
            "accepted": accepted,
            "rejection_count": rejection_count,
            "conversion_pct": round(conversion_pct, 2),
            "top_rejection": top_rejection,
        })
        family_skip_drilldown.append({
            "family": str(family_name),
            "generated": generated,
            "accepted": accepted,
            "rejection_count": rejection_count,
            "conversion_pct": round(conversion_pct, 2),
            "top_rejection": top_rejection,
            "reasons": reason_rows,
        })

    family_rows.sort(key=lambda row: (row["accepted"], row["generated"], row["family"]), reverse=True)
    family_skip_drilldown.sort(key=lambda row: (int(row["rejection_count"]), int(row["generated"]), str(row["family"])), reverse=True)
    return {
        "families": families,
        "funnel_totals": dict(sorted(funnel_totals.items())),
        "rejection_totals": dict(sorted(rejection_totals.items(), key=lambda item: item[1], reverse=True)),
        "top_rejection_samples": top_rejection_samples,
        "family_rows": family_rows,
        "family_skip_drilldown": family_skip_drilldown,
    }


def _load_previous_research_summary(symbol: str, timeframe: str, current_generated_at: Any) -> Tuple[Dict[str, Any], Path] | Tuple[None, None]:
    current_stamp = parse_iso_datetime(current_generated_at)
    candidates: List[Tuple[datetime, Path, Dict[str, Any]]] = []

    for path in RESEARCH_SUMMARY_DIR.rglob(f"{symbol}_{timeframe}.json"):
        if path.parent == RESEARCH_SUMMARY_DIR:
            continue
        payload = read_json_file(path, default=None)
        if not isinstance(payload, dict):
            continue
        generated_at = parse_iso_datetime(payload.get("generated_at"))
        if generated_at is None:
            continue
        if current_stamp and generated_at >= current_stamp:
            continue
        candidates.append((generated_at, path, payload))

    if not candidates:
        return None, None

    candidates.sort(key=lambda item: item[0], reverse=True)
    _, path, payload = candidates[0]
    return payload, path


def _build_research_comparison(symbol: str, timeframe: str, current_payload: Dict[str, Any], current_summary: Dict[str, Any]) -> Dict[str, Any]:
    previous_payload, previous_path = _load_previous_research_summary(symbol, timeframe, current_payload.get("generated_at"))
    if not previous_payload or previous_path is None:
        return {}

    previous_summary = _summarize_research_payload(previous_payload)
    current_rows = {str(row["family"]): row for row in current_summary["family_rows"]}
    previous_rows = {str(row["family"]): row for row in previous_summary["family_rows"]}

    funnel_delta = {
        key: _coerce_int(current_summary["funnel_totals"].get(key)) - _coerce_int(previous_summary["funnel_totals"].get(key))
        for key in sorted(set(current_summary["funnel_totals"].keys()) | set(previous_summary["funnel_totals"].keys()))
    }
    rejection_delta = {
        key: _coerce_int(current_summary["rejection_totals"].get(key)) - _coerce_int(previous_summary["rejection_totals"].get(key))
        for key in sorted(set(current_summary["rejection_totals"].keys()) | set(previous_summary["rejection_totals"].keys()))
    }

    family_deltas: List[Dict[str, Any]] = []
    for family in sorted(set(current_rows.keys()) | set(previous_rows.keys())):
        current_row = current_rows.get(family, {})
        previous_row = previous_rows.get(family, {})
        family_deltas.append({
            "family": family,
            "generated_delta": _coerce_int(current_row.get("generated")) - _coerce_int(previous_row.get("generated")),
            "accepted_delta": _coerce_int(current_row.get("accepted")) - _coerce_int(previous_row.get("accepted")),
            "rejection_delta": _coerce_int(current_row.get("rejection_count")) - _coerce_int(previous_row.get("rejection_count")),
            "conversion_pct_delta": round(float(current_row.get("conversion_pct", 0.0) or 0.0) - float(previous_row.get("conversion_pct", 0.0) or 0.0), 2),
            "current_conversion_pct": float(current_row.get("conversion_pct", 0.0) or 0.0),
            "previous_conversion_pct": float(previous_row.get("conversion_pct", 0.0) or 0.0),
            "current_top_rejection": current_row.get("top_rejection") or "-",
            "previous_top_rejection": previous_row.get("top_rejection") or "-",
        })

    family_deltas.sort(key=lambda row: (abs(float(row["accepted_delta"])), abs(float(row["conversion_pct_delta"])), abs(float(row["generated_delta"]))), reverse=True)

    current_generated = _coerce_int(current_summary["funnel_totals"].get("generated"))
    previous_generated = _coerce_int(previous_summary["funnel_totals"].get("generated"))
    current_accepted = _coerce_int(current_summary["funnel_totals"].get("accepted"))
    previous_accepted = _coerce_int(previous_summary["funnel_totals"].get("accepted"))
    current_conversion_pct = (current_accepted / current_generated * 100.0) if current_generated > 0 else 0.0
    previous_conversion_pct = (previous_accepted / previous_generated * 100.0) if previous_generated > 0 else 0.0

    positive_families = [row for row in family_deltas if float(row["accepted_delta"]) > 0 or float(row["conversion_pct_delta"]) > 0]
    negative_families = [row for row in family_deltas if float(row["accepted_delta"]) < 0 or float(row["conversion_pct_delta"]) < 0]
    relative_parent = previous_path.parent.relative_to(RESEARCH_SUMMARY_DIR)
    comparison_label = "previous snapshot" if str(relative_parent) == "." else str(relative_parent)

    return {
        "label": comparison_label,
        "previous_generated_at": previous_payload.get("generated_at") or utc_now_iso(),
        "previous_path": str(previous_path.relative_to(BASE_DIR)),
        "summary": {
            "generated_delta": current_generated - previous_generated,
            "accepted_delta": current_accepted - previous_accepted,
            "conversion_pct_delta": round(current_conversion_pct - previous_conversion_pct, 2),
            "family_count_delta": len(current_rows) - len(previous_rows),
            "largest_gain_family": positive_families[0] if positive_families else None,
            "largest_drop_family": negative_families[0] if negative_families else None,
        },
        "funnel_deltas": funnel_delta,
        "rejection_deltas": rejection_delta,
        "family_deltas": family_deltas[:8],
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


def _strategy_identity_tone(level: str) -> str:
    if level in {"success", "info", "warning", "critical", "neutral"}:
        return level
    return "neutral"


def _average_or_none(total: float, count: int) -> Optional[float]:
    if count <= 0:
        return None
    return total / count


def _build_strategy_definition(
    *,
    name: str,
    symbol: str,
    timeframe: str,
    payload: Dict[str, Any],
) -> Optional[StrategyDefinition]:
    if not isinstance(payload, dict):
        return None

    exit_rule = payload.get("exit_rule")
    if not exit_rule:
        return None

    try:
        return StrategyDefinition(
            name=name,
            symbol=str(symbol or payload.get("symbol") or "unknown"),
            timeframe=str(timeframe or payload.get("timeframe") or "unknown"),
            long_entry_rule=payload.get("long_entry_rule"),
            short_entry_rule=payload.get("short_entry_rule"),
            exit_rule=str(exit_rule),
            stop_loss_pips=float(payload.get("stop_loss_pips") or 0.0),
            take_profit_pips=float(payload.get("take_profit_pips") or 0.0),
            sl_atr_mult=_safe_float(payload.get("sl_atr_mult")),
            tp_atr_mult=_safe_float(payload.get("tp_atr_mult")),
            params=dict(payload.get("params") or {}),
        )
    except Exception:
        return None


def _resolve_strategy_definition(
    *,
    name: str,
    symbol: str,
    timeframe: str,
    pool_record: Dict[str, Any] | None,
    manifest_entry: Dict[str, Any] | None,
    index_entry: Dict[str, Any] | None,
) -> Optional[StrategyDefinition]:
    pool_stats = (pool_record or {}).get("stats") if isinstance(pool_record, dict) else {}
    strategy_payload = (pool_stats or {}).get("strategy") if isinstance(pool_stats, dict) else None
    if isinstance(strategy_payload, dict):
        definition = _build_strategy_definition(name=name, symbol=symbol, timeframe=timeframe, payload=strategy_payload)
        if definition is not None:
            return definition

    fallback_payload = {
        "long_entry_rule": (manifest_entry or {}).get("long_entry_rule") or (index_entry or {}).get("long_entry_rule"),
        "short_entry_rule": (manifest_entry or {}).get("short_entry_rule") or (index_entry or {}).get("short_entry_rule"),
        "exit_rule": (manifest_entry or {}).get("exit_rule") or (index_entry or {}).get("exit_rule"),
        "stop_loss_pips": (manifest_entry or {}).get("stop_loss_pips") or (index_entry or {}).get("stop_loss_pips"),
        "take_profit_pips": (manifest_entry or {}).get("take_profit_pips") or (index_entry or {}).get("take_profit_pips"),
        "sl_atr_mult": (manifest_entry or {}).get("sl_atr_mult") or (index_entry or {}).get("sl_atr_mult"),
        "tp_atr_mult": (manifest_entry or {}).get("tp_atr_mult") or (index_entry or {}).get("tp_atr_mult"),
        "params": (manifest_entry or {}).get("params") or (index_entry or {}).get("params") or {},
    }
    return _build_strategy_definition(name=name, symbol=symbol, timeframe=timeframe, payload=fallback_payload)


def _is_structural_clone(a: StrategyDefinition, b: StrategyDefinition) -> bool:
    return (
        str(a.long_entry_rule or "") == str(b.long_entry_rule or "")
        and str(a.short_entry_rule or "") == str(b.short_entry_rule or "")
        and str(a.exit_rule or "") == str(b.exit_rule or "")
        and _safe_float(a.sl_atr_mult) == _safe_float(b.sl_atr_mult)
        and _safe_float(a.tp_atr_mult) == _safe_float(b.tp_atr_mult)
        and _safe_float(a.stop_loss_pips) == _safe_float(b.stop_loss_pips)
        and _safe_float(a.take_profit_pips) == _safe_float(b.take_profit_pips)
    )


def _build_strategy_similarity_panel(
    *,
    target_name: str,
    pool: Any,
    manifest_by_name: Dict[str, Dict[str, Any]],
    index_by_name: Dict[str, Dict[str, Any]],
    live_strategy_rows: Dict[str, Any],
) -> Dict[str, Any]:
    target_rec = pool.strategies.get(target_name) if hasattr(pool, "strategies") else None
    if target_rec is None:
        return {}

    target_pool_record = target_rec.to_dict() if hasattr(target_rec, "to_dict") else {}
    target_manifest = manifest_by_name.get(target_name) or {}
    target_index = index_by_name.get(target_name) or {}
    target_definition = _resolve_strategy_definition(
        name=target_name,
        symbol=str(target_rec.symbol or "unknown"),
        timeframe=str(target_rec.timeframe or "unknown"),
        pool_record=target_pool_record,
        manifest_entry=target_manifest,
        index_entry=target_index,
    )
    if target_definition is None:
        return {}

    target_stats = (target_pool_record.get("stats") or {}) if isinstance(target_pool_record, dict) else {}
    target_strategy_payload = (target_stats.get("strategy") or {}) if isinstance(target_stats, dict) else {}
    target_family = str(
        target_manifest.get("family")
        or target_index.get("family")
        or target_strategy_payload.get("family")
        or target_stats.get("family")
        or "unknown"
    )
    target_motif = str(target_stats.get("research_motif") or target_stats.get("motif") or strategy_motif(target_definition) or "unknown")
    target_status = str(target_rec.status or target_manifest.get("status") or target_index.get("status") or "unknown")

    neighbor_rows: List[Dict[str, Any]] = []
    high_similarity_count = 0
    same_slot_high_similarity_count = 0
    structural_clone_count = 0

    for other_name, other_rec in pool.strategies.items():
        if other_name == target_name:
            continue

        other_pool_record = other_rec.to_dict() if hasattr(other_rec, "to_dict") else {}
        other_manifest = manifest_by_name.get(other_name) or {}
        other_index = index_by_name.get(other_name) or {}
        other_definition = _resolve_strategy_definition(
            name=other_name,
            symbol=str(other_rec.symbol or "unknown"),
            timeframe=str(other_rec.timeframe or "unknown"),
            pool_record=other_pool_record,
            manifest_entry=other_manifest,
            index_entry=other_index,
        )
        if other_definition is None:
            continue

        similarity = round(float(semantic_similarity(target_definition, other_definition)), 4)
        other_stats = (other_pool_record.get("stats") or {}) if isinstance(other_pool_record, dict) else {}
        other_strategy_payload = (other_stats.get("strategy") or {}) if isinstance(other_stats, dict) else {}
        other_family = str(
            other_manifest.get("family")
            or other_index.get("family")
            or other_strategy_payload.get("family")
            or other_stats.get("family")
            or "unknown"
        )
        other_motif = str(other_stats.get("research_motif") or other_stats.get("motif") or strategy_motif(other_definition) or "unknown")
        same_slot = target_definition.symbol == other_definition.symbol and target_definition.timeframe == other_definition.timeframe
        same_family = target_family == other_family
        same_motif = target_motif == other_motif
        structural_clone = _is_structural_clone(target_definition, other_definition)

        if similarity >= 0.85:
            high_similarity_count += 1
            if same_slot:
                same_slot_high_similarity_count += 1
        if structural_clone:
            structural_clone_count += 1

        relationship_parts: List[str] = []
        if same_slot:
            relationship_parts.append("same slot")
        if same_family:
            relationship_parts.append("same family")
        if same_motif:
            relationship_parts.append("same motif")
        if structural_clone:
            relationship_parts.append("structural clone")
        if not relationship_parts:
            relationship_parts.append("cross-lineage neighbor")

        if structural_clone or similarity >= 0.92:
            risk_tone = "critical"
            risk_label = "clone risk"
        elif similarity >= 0.85:
            risk_tone = "warning"
            risk_label = "near clone"
        elif similarity >= 0.75:
            risk_tone = "info"
            risk_label = "adjacent"
        else:
            risk_tone = "neutral"
            risk_label = "distant"

        other_live = live_strategy_rows.get(other_name) if isinstance(live_strategy_rows.get(other_name), dict) else {}
        neighbor_rows.append({
            "name": other_name,
            "status": str(other_rec.status or other_manifest.get("status") or other_index.get("status") or "unknown"),
            "score": _safe_float(other_rec.score),
            "symbol": str(other_rec.symbol or other_definition.symbol),
            "timeframe": str(other_rec.timeframe or other_definition.timeframe),
            "family": other_family,
            "motif": other_motif,
            "similarity": similarity,
            "relationship": ", ".join(relationship_parts),
            "same_slot": same_slot,
            "same_family": same_family,
            "same_motif": same_motif,
            "structural_clone": structural_clone,
            "risk_tone": risk_tone,
            "risk_label": risk_label,
            "research_return_pct": _safe_float(other_stats.get("return_pct")),
            "research_sharpe": _safe_float(other_stats.get("sharpe_ratio")),
            "research_nearest_similarity": _safe_float(other_stats.get("research_nearest_similarity")),
            "research_novelty_score": _safe_float(other_stats.get("research_novelty_score")),
            "live_total_pnl": _safe_float((other_live or {}).get("total_pnl")),
            "live_num_trades": _safe_int((other_live or {}).get("num_trades")),
        })

    neighbor_rows.sort(
        key=lambda row: (
            bool(row.get("structural_clone")),
            bool(row.get("same_slot")),
            bool(row.get("same_family")),
            float(row.get("similarity") or 0.0),
            float(row.get("score") or float("-inf")),
        ),
        reverse=True,
    )

    nearest_neighbor = neighbor_rows[0] if neighbor_rows else None
    target_research_nearest_similarity = _safe_float(target_stats.get("research_nearest_similarity"))
    target_novelty_score = _safe_float(target_stats.get("research_novelty_score"))
    duplicate_risk = "low"
    duplicate_tone = "success"
    if structural_clone_count > 0 or (nearest_neighbor and float(nearest_neighbor.get("similarity") or 0.0) >= 0.92):
        duplicate_risk = "high"
        duplicate_tone = "critical"
    elif same_slot_high_similarity_count > 0 or (nearest_neighbor and float(nearest_neighbor.get("similarity") or 0.0) >= 0.85):
        duplicate_risk = "watch"
        duplicate_tone = "warning"
    elif high_similarity_count > 0:
        duplicate_risk = "moderate"
        duplicate_tone = "info"

    if nearest_neighbor:
        headline = f"Nearest live neighbor is {nearest_neighbor['name']} at {float(nearest_neighbor['similarity']) * 100:.1f}% similarity."
    else:
        headline = "No comparable live neighbors were recoverable from the current pool payload."

    summary_parts = [
        f"{_humanize_token(target_family).title()} posture is {duplicate_risk}",
        f"{high_similarity_count} neighbor(s) clear the 85% similarity line",
        f"{same_slot_high_similarity_count} of those sit in the same slot",
    ]
    if structural_clone_count:
        summary_parts.append(f"{structural_clone_count} structural clone(s) share the same core rules")
    if target_novelty_score is not None:
        summary_parts.append(f"research novelty score is {target_novelty_score:.2f}")

    return {
        "headline": headline,
        "summary": ", ".join(summary_parts) + ".",
        "target": {
            "name": target_name,
            "status": target_status,
            "family": target_family,
            "motif": target_motif,
            "research_nearest_similarity": target_research_nearest_similarity,
            "research_novelty_score": target_novelty_score,
        },
        "duplicate_risk": duplicate_risk,
        "tone": duplicate_tone,
        "high_similarity_count": high_similarity_count,
        "same_slot_high_similarity_count": same_slot_high_similarity_count,
        "structural_clone_count": structural_clone_count,
        "nearest_neighbor": nearest_neighbor,
        "neighbors": neighbor_rows[:8],
        "thresholds": {
            "near_clone": 0.85,
            "clone_risk": 0.92,
        },
    }


def _build_strategy_duplicate_risk_context(
    *,
    symbol: str,
    timeframe: str,
    family: str,
    similarity_panel: Dict[str, Any],
) -> Dict[str, Any]:
    if not symbol or not timeframe or not family or family == "unknown":
        return {}

    payload = read_json_file(RESEARCH_SUMMARY_DIR / f"{symbol}_{timeframe}.json", default=None)
    if not isinstance(payload, dict):
        return {}

    summary = _summarize_research_payload(payload)
    family_row = next((row for row in summary["family_skip_drilldown"] if str(row.get("family") or "") == family), None)
    if not isinstance(family_row, dict):
        return {}

    family_reasons = {
        str(item.get("reason") or ""): item
        for item in family_row.get("reasons", [])
        if isinstance(item, dict) and item.get("reason")
    }
    semantic_reason = family_reasons.get("semantic_duplicate") or {}
    memory_reason = family_reasons.get("memory_veto") or {}
    semantic_count = _coerce_int(semantic_reason.get("count"))
    memory_count = _coerce_int(memory_reason.get("count"))
    family_generated = _coerce_int(family_row.get("generated"))
    family_accepted = _coerce_int(family_row.get("accepted"))

    slot_semantic_total = 0
    slot_memory_total = 0
    for other_row in summary["family_skip_drilldown"]:
        if not isinstance(other_row, dict):
            continue
        for reason_row in other_row.get("reasons", []):
            if not isinstance(reason_row, dict):
                continue
            reason_name = str(reason_row.get("reason") or "")
            if reason_name == "semantic_duplicate":
                slot_semantic_total += _coerce_int(reason_row.get("count"))
            elif reason_name == "memory_veto":
                slot_memory_total += _coerce_int(reason_row.get("count"))

    reason_rows: List[Dict[str, Any]] = []
    for reason_name, label, tone, payload_row in [
        ("semantic_duplicate", "Semantic duplicate", "warning", semantic_reason),
        ("memory_veto", "Memory veto", "critical", memory_reason),
    ]:
        count = _coerce_int(payload_row.get("count"))
        raw_samples = payload_row.get("samples") if isinstance(payload_row, dict) else []
        samples = [_normalize_skip_sample(item) for item in raw_samples] if isinstance(raw_samples, list) else []
        samples = [item for item in samples if item]
        if count <= 0 and not samples:
            continue
        if reason_name == "memory_veto":
            reading = "Research memory found too many bad historical neighbors for similar candidates."
        else:
            reading = "Fresh candidates in this family were blocked for landing too close to an existing strategy shape."
        reason_rows.append({
            "reason": reason_name,
            "label": label,
            "count": count,
            "samples": samples[:3],
            "tone": tone,
            "reading": reading,
        })

    risk_label = "clear"
    risk_tone = "success"
    if memory_count > 0 or str(similarity_panel.get("duplicate_risk") or "") == "high":
        risk_label = "memory pressure"
        risk_tone = "critical"
    elif semantic_count > 0 or str(similarity_panel.get("duplicate_risk") or "") in {"watch", "moderate"}:
        risk_label = "duplicate pressure"
        risk_tone = "warning"

    summary_parts: List[str] = []
    if semantic_count > 0:
        summary_parts.append(f"{semantic_count} recent semantic-duplicate skip(s) hit this family")
    if memory_count > 0:
        summary_parts.append(f"{memory_count} memory-veto skip(s) also landed here")
    if not summary_parts:
        summary_parts.append("Latest research run did not log semantic-duplicate or memory-veto skips for this family")
    summary_parts.append(f"{slot_semantic_total} semantic duplicate skip(s) across the full {symbol} {timeframe} slot")
    if slot_memory_total > 0:
        summary_parts.append(f"{slot_memory_total} memory-veto skip(s) across the slot")

    headline = f"Latest {symbol} {timeframe} research run shows {risk_label} around the {family} family."

    return {
        "headline": headline,
        "summary": ", ".join(summary_parts) + ".",
        "tone": risk_tone,
        "risk_label": risk_label,
        "generated_at": payload.get("generated_at"),
        "symbol": symbol,
        "timeframe": timeframe,
        "family": family,
        "family_generated": family_generated,
        "family_accepted": family_accepted,
        "family_rejection_count": _coerce_int(family_row.get("rejection_count")),
        "semantic_duplicate_count": semantic_count,
        "memory_veto_count": memory_count,
        "slot_semantic_duplicate_total": slot_semantic_total,
        "slot_memory_veto_total": slot_memory_total,
        "reasons": reason_rows,
    }


def _build_strategy_identity(
    *,
    family: str,
    current_status: str,
    meta: Dict[str, Any],
    risk_behavior: Dict[str, Any],
    regime_pnl: Dict[str, Any],
    session_pnl: Dict[str, Any],
    stability: Dict[str, Any],
    live_decay: Dict[str, Any],
) -> Dict[str, Any]:
    best_regime = str(meta.get("best_regime") or "unknown")
    best_session = str(meta.get("best_session") or "unknown")
    allowed_regimes = [str(item) for item in (meta.get("allowed_regimes") or []) if item]
    allowed_sessions = [str(item) for item in (meta.get("allowed_sessions") or []) if item]
    is_trend_follower = bool(meta.get("is_trend_follower"))
    is_range_trader = bool(meta.get("is_range_trader"))
    avg_holding_bars = _safe_float(risk_behavior.get("avg_holding_bars"))
    exit_rule_ratio = _safe_float(risk_behavior.get("exit_rule_ratio"))
    max_consecutive_losses = _safe_int(risk_behavior.get("max_consecutive_losses"))
    sharpe_std = _safe_float(stability.get("sharpe_std"))
    live_negative_ratio = _safe_float(live_decay.get("negative_ratio"))
    live_loss_streak = _safe_int(live_decay.get("loss_streak"))

    session_rows: List[Tuple[str, float]] = []
    for session_name, payload in session_pnl.items():
        if not isinstance(payload, dict):
            continue
        session_rows.append((str(session_name), _safe_float(payload.get("return_pct")) or 0.0))
    session_rows.sort(key=lambda item: item[1], reverse=True)
    positive_sessions = [item for item in session_rows if item[1] > 0]
    strongest_session_share = None
    if positive_sessions:
        positive_total = sum(item[1] for item in positive_sessions)
        if positive_total > 0:
            strongest_session_share = positive_sessions[0][1] / positive_total

    regime_rows: List[Tuple[str, float]] = []
    for regime_name, payload in regime_pnl.items():
        if not isinstance(payload, dict):
            continue
        regime_rows.append((str(regime_name), _safe_float(payload.get("return_pct")) or 0.0))
    regime_rows.sort(key=lambda item: item[1], reverse=True)
    positive_regimes = [item for item in regime_rows if item[1] > 0]
    strongest_regime_share = None
    if positive_regimes:
        positive_total = sum(item[1] for item in positive_regimes)
        if positive_total > 0:
            strongest_regime_share = positive_regimes[0][1] / positive_total

    archetype_bits: List[str] = []
    if is_range_trader:
        archetype_bits.append("range specialist")
    if is_trend_follower:
        archetype_bits.append("trend follower")
    if strongest_session_share is not None and strongest_session_share >= 0.55 and best_session != "unknown":
        archetype_bits.append(f"{_humanize_token(best_session)}-session dependent")
    if strongest_regime_share is not None and strongest_regime_share >= 0.6 and best_regime != "unknown":
        archetype_bits.append(f"{_humanize_token(best_regime)} regime specialist")
    if not archetype_bits:
        archetype_bits.append(f"{_humanize_token(family)} operator")
    archetype = ", ".join(dict.fromkeys(archetype_bits))

    edge_badges: List[Dict[str, Any]] = [
        {
            "label": _humanize_token(family).title(),
            "tone": "info",
            "detail": "Declared strategy family from manifest/index research lineage.",
        },
        {
            "label": f"Best regime: {_humanize_token(best_regime).title()}",
            "tone": "success" if best_regime != "unknown" else "neutral",
            "detail": "Highest-return detected market regime from research explain metadata.",
        },
        {
            "label": f"Best session: {_humanize_token(best_session).title()}",
            "tone": "success" if best_session != "unknown" else "neutral",
            "detail": "Trading session that contributes the strongest research return.",
        },
    ]
    if is_range_trader:
        edge_badges.append({
            "label": "Range trader",
            "tone": "info",
            "detail": "Research metadata classifies this strategy as a mean-reversion / range operator.",
        })
    if is_trend_follower:
        edge_badges.append({
            "label": "Trend follower",
            "tone": "info",
            "detail": "Research metadata classifies this strategy as momentum / trend-following.",
        })
    if allowed_regimes:
        edge_badges.append({
            "label": f"Regime allowance: {len(allowed_regimes)}",
            "tone": "neutral" if len(allowed_regimes) > 2 else "warning",
            "detail": f"Allowed regimes: {', '.join(_humanize_token(item) for item in allowed_regimes)}.",
        })
    if allowed_sessions:
        edge_badges.append({
            "label": f"Session allowance: {len(allowed_sessions)}",
            "tone": "neutral" if len(allowed_sessions) > 2 else "warning",
            "detail": f"Allowed sessions: {', '.join(_humanize_token(item) for item in allowed_sessions)}.",
        })

    warnings: List[Dict[str, Any]] = []
    family_lower = family.lower()
    best_regime_lower = best_regime.lower()
    if "range" in family_lower and is_trend_follower:
        warnings.append({
            "label": "Family vs style mismatch",
            "tone": "warning",
            "detail": "The family names this as a range setup, but research metadata still flags trend-following behavior.",
        })
    if "trend" in family_lower and is_range_trader:
        warnings.append({
            "label": "Family vs style mismatch",
            "tone": "warning",
            "detail": "The family names this as a trend setup, but research metadata still flags range-trading behavior.",
        })
    if "range" in family_lower and "trend" in best_regime_lower:
        warnings.append({
            "label": "Family / regime mismatch",
            "tone": "warning",
            "detail": f"The family reads range-oriented while the strongest regime comes from {_humanize_token(best_regime)} conditions.",
        })
    if "trend" in family_lower and "rang" in best_regime_lower:
        warnings.append({
            "label": "Family / regime mismatch",
            "tone": "warning",
            "detail": f"The family reads trend-oriented while the strongest regime comes from {_humanize_token(best_regime)} conditions.",
        })
    if strongest_session_share is not None and strongest_session_share >= 0.6 and best_session != "unknown":
        warnings.append({
            "label": "Session dependence",
            "tone": "warning",
            "detail": f"About {strongest_session_share * 100:.0f}% of positive session return comes from {_humanize_token(best_session)}.",
        })
    if positive_sessions and len(positive_sessions) == 1:
        warnings.append({
            "label": "Single-session edge",
            "tone": "critical",
            "detail": f"Only {_humanize_token(positive_sessions[0][0])} contributes positive session return in the current research snapshot.",
        })

    fragility_markers: List[Dict[str, Any]] = []
    if exit_rule_ratio is not None and exit_rule_ratio >= 0.8:
        fragility_markers.append({
            "label": "Exit-rule dependency",
            "tone": "warning",
            "detail": f"{exit_rule_ratio * 100:.0f}% of exits come from the explicit exit rule instead of TP/SL resolution.",
        })
    if avg_holding_bars is not None and avg_holding_bars <= 1.0:
        fragility_markers.append({
            "label": "Ultra-short holding",
            "tone": "warning",
            "detail": f"Average hold is only {avg_holding_bars:.1f} bars, so execution friction can distort live edge quickly.",
        })
    if max_consecutive_losses is not None and max_consecutive_losses >= 5:
        fragility_markers.append({
            "label": "Loss-streak sensitivity",
            "tone": "warning" if max_consecutive_losses < 7 else "critical",
            "detail": f"Research already saw a {max_consecutive_losses}-trade consecutive loss streak.",
        })
    if sharpe_std is not None and sharpe_std >= 0.9:
        fragility_markers.append({
            "label": "Subperiod instability",
            "tone": "warning",
            "detail": f"Subperiod Sharpe dispersion is {sharpe_std:.2f}, suggesting the edge shape moves across windows.",
        })
    if live_negative_ratio is not None and live_negative_ratio >= 0.7:
        fragility_markers.append({
            "label": "Live decay pressure",
            "tone": "critical" if current_status in {"active", "exploratory"} else "warning",
            "detail": f"Recent live negative-trade ratio is {live_negative_ratio * 100:.0f}% with loss streak {live_loss_streak or 0}.",
        })

    summary_parts = [f"{_humanize_token(family).title()} DNA points to a {archetype}"]
    if best_regime != "unknown":
        summary_parts.append(f"best in {_humanize_token(best_regime)} regimes")
    if best_session != "unknown":
        summary_parts.append(f"and strongest during {_humanize_token(best_session)}")
    if warnings:
        summary_parts.append(f"with {len(warnings)} operator warning{'s' if len(warnings) != 1 else ''}")
    if fragility_markers:
        summary_parts.append(f"plus {len(fragility_markers)} fragility marker{'s' if len(fragility_markers) != 1 else ''}")

    return {
        "archetype": archetype,
        "summary": ", ".join(summary_parts) + ".",
        "edge_badges": [
            {**item, "tone": _strategy_identity_tone(str(item.get("tone") or "neutral"))}
            for item in edge_badges
        ],
        "warnings": [
            {**item, "tone": _strategy_identity_tone(str(item.get("tone") or "neutral"))}
            for item in warnings
        ],
        "fragility_markers": [
            {**item, "tone": _strategy_identity_tone(str(item.get("tone") or "neutral"))}
            for item in fragility_markers
        ],
        "metrics": {
            "allowed_regime_count": len(allowed_regimes),
            "allowed_session_count": len(allowed_sessions),
            "strongest_session_share": strongest_session_share,
            "strongest_regime_share": strongest_regime_share,
            "avg_holding_bars": avg_holding_bars,
            "exit_rule_ratio": exit_rule_ratio,
            "max_consecutive_losses": max_consecutive_losses,
            "sharpe_std": sharpe_std,
        },
    }


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

    autonomous_strategies = {
        name: row
        for name, row in strategies.items()
        if not is_manual_strategy_bucket(name)
    }
    manual_buckets = {
        name: row
        for name, row in strategies.items()
        if is_manual_strategy_bucket(name)
    }

    total_pnl = sum(float((row or {}).get("total_pnl", 0.0) or 0.0) for row in autonomous_strategies.values())
    total_trades = sum(int((row or {}).get("num_trades", 0) or 0) for row in autonomous_strategies.values())
    ranked = sorted(
        (
            {
                "name": name,
                "total_pnl": float((row or {}).get("total_pnl", 0.0) or 0.0),
                "num_trades": int((row or {}).get("num_trades", 0) or 0),
                "last_update": (row or {}).get("last_update"),
                "recent_pnls": list((row or {}).get("recent_pnls") or []),
            }
            for name, row in autonomous_strategies.items()
        ),
        key=lambda row: (row["num_trades"], row["total_pnl"]),
        reverse=True,
    )
    manual_total_pnl = sum(float((row or {}).get("total_pnl", 0.0) or 0.0) for row in manual_buckets.values())
    manual_total_trades = sum(int((row or {}).get("num_trades", 0) or 0) for row in manual_buckets.values())
    return {
        "strategy_count": len(autonomous_strategies),
        "total_realized_pnl": total_pnl,
        "total_trades": total_trades,
        "top_active": ranked[:10],
        "strategies": autonomous_strategies,
        "manual_bucket_count": len(manual_buckets),
        "manual_total_realized_pnl": manual_total_pnl,
        "manual_total_trades": manual_total_trades,
        "manual_buckets": manual_buckets,
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


def load_trade_context_journal() -> Dict[str, Any]:
    data = read_json_file(TRADE_CONTEXT_JOURNAL_PATH, default={})
    if not isinstance(data, dict):
        return {}
    trades = data.get("trades")
    if not isinstance(trades, dict):
        trades = {}
    data["trades"] = trades
    return data


def _iter_system_log_paths(limit: int = 6) -> List[Path]:
    if not LOGS_DIR.exists():
        return []
    return sorted(
        (path for path in LOGS_DIR.glob("system.log*") if path.is_file()),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )[:limit]


def _classify_trade_context_failure_cause(cause: str, traceback_lines: List[str]) -> Tuple[str, str]:
    haystack = " ".join([cause, *traceback_lines]).lower()
    if "read_parquet" in haystack or ".parquet" in haystack:
        return ("feature_snapshot", "Feature snapshot read failed while enriching the trade-context journal.")
    if "permission" in haystack or "access is denied" in haystack:
        return ("permission", "The runtime could not read or write a required file for journal registration.")
    if "json" in haystack or "decode" in haystack or "expecting value" in haystack:
        return ("journal_payload", "The existing trade-context journal payload could not be decoded cleanly.")
    if "no such file" in haystack or "filenotfounderror" in haystack:
        return ("missing_artifact", "A required artifact was missing when the runtime tried to register context.")
    if "os.replace" in haystack or "mkstemp" in haystack or "safe_write_json" in haystack:
        return ("journal_write", "The runtime failed while writing the trade-context journal atomically.")
    return ("unknown", "The runtime raised an unexpected exception while registering trade context.")


def load_recent_trade_context_registration_failures(limit: int = 12) -> Dict[str, Any]:
    rows: List[Dict[str, Any]] = []
    for path in _iter_system_log_paths():
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except Exception:
            continue

        index = 0
        while index < len(lines):
            line = lines[index]
            match = SYSTEM_LOG_PATTERN.match(line)
            if not match:
                index += 1
                continue

            message = str(match.group("message") or "")
            failure_match = TRADE_CONTEXT_FAILURE_PATTERN.search(message)
            if not failure_match:
                index += 1
                continue

            traceback_lines: List[str] = []
            cursor = index + 1
            while cursor < len(lines) and not SYSTEM_LOG_PATTERN.match(lines[cursor]):
                extra_line = lines[cursor].rstrip()
                if extra_line:
                    traceback_lines.append(extra_line)
                cursor += 1

            cause_line = next((entry for entry in reversed(traceback_lines) if ":" in entry), traceback_lines[-1] if traceback_lines else "")
            cause_key, cause_detail = _classify_trade_context_failure_cause(cause_line, traceback_lines)
            timestamp = parse_iso_datetime(str(match.group("timestamp") or "").replace(",", "."))
            rows.append({
                "timestamp": timestamp.replace(microsecond=0).isoformat() if timestamp else None,
                "phase": str(failure_match.group("phase") or "").lower(),
                "strategy_name": str(failure_match.group("strategy") or "").strip(),
                "ticket": str(failure_match.group("ticket") or "").strip(),
                "ticket_label": str(failure_match.group("ticket_label") or "ticket").lower(),
                "log_file": path.name,
                "logger": str(match.group("logger") or ""),
                "message": message,
                "cause": cause_line or "No stack-trace cause captured",
                "cause_key": cause_key,
                "cause_detail": cause_detail,
                "traceback": traceback_lines[-8:],
            })
            index = cursor

    rows.sort(key=lambda row: str(row.get("timestamp") or ""), reverse=True)
    limited_rows = rows[:limit]
    phase_counts = Counter(str(row.get("phase") or "unknown") for row in limited_rows)
    cause_counts = Counter(str(row.get("cause_key") or "unknown") for row in limited_rows)
    strategy_counts = Counter(str(row.get("strategy_name") or "unknown") for row in limited_rows)

    return {
        "count": len(rows),
        "latest_at": limited_rows[0].get("timestamp") if limited_rows else None,
        "entry_count": int(phase_counts.get("entry", 0)),
        "exit_count": int(phase_counts.get("exit", 0)),
        "files_scanned": [path.name for path in _iter_system_log_paths()],
        "causes": [
            {"key": key, "count": count}
            for key, count in sorted(cause_counts.items(), key=lambda item: (-item[1], item[0]))
        ],
        "strategies": [
            {"strategy_name": key, "count": count}
            for key, count in strategy_counts.most_common(8)
        ],
        "recent": limited_rows,
    }


def _path_mtime_iso(path: Path) -> str | None:
    if not path.exists():
        return None
    try:
        return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).replace(microsecond=0).isoformat()
    except Exception:
        return None


def _build_execution_artifact_warnings(
    live_state: Dict[str, Any],
    live_stats: Dict[str, Any],
    open_trades: Dict[str, Any],
    recent_trade_log: List[Dict[str, Any]],
    trade_context_journal: Dict[str, Any],
    unmatched_rows: List[Dict[str, Any]],
    trade_context_registration_failures: Dict[str, Any],
) -> Dict[str, Any]:
    now = datetime.now(timezone.utc)
    latest_log_time = max(
        (
            parse_iso_datetime(row.get("ts") or row.get("timestamp") or row.get("recorded_at") or row.get("time"))
            for row in recent_trade_log
            if isinstance(row, dict)
        ),
        default=None,
    )
    latest_system_log_path = next(iter(_iter_system_log_paths(limit=1)), None)

    journal_trades = trade_context_journal.get("trades") if isinstance(trade_context_journal, dict) else {}
    if not isinstance(journal_trades, dict):
        journal_trades = {}

    artifact_specs = [
        {
            "key": "live_state",
            "label": "Live state snapshot",
            "path": LIVE_STATE_PATH,
            "observed_at": _path_mtime_iso(LIVE_STATE_PATH),
            "warning_minutes": 90,
            "critical_minutes": 180,
            "missing_tone": "critical",
            "count": None,
            "operator_meaning": "Day lock, equity, and top-level runtime posture may no longer reflect the current executor state.",
        },
        {
            "key": "strategy_live_stats",
            "label": "Strategy live stats",
            "path": STATS_PATH,
            "observed_at": _path_mtime_iso(STATS_PATH),
            "warning_minutes": 90,
            "critical_minutes": 180,
            "missing_tone": "critical",
            "count": int(live_stats.get("strategy_count", 0) or 0),
            "operator_meaning": "Per-strategy live trade counts and realized PnL may be stale, which weakens execution diagnosis and drift review.",
        },
        {
            "key": "open_trades",
            "label": "Open trades snapshot",
            "path": OPEN_TRADES_PATH,
            "observed_at": _path_mtime_iso(OPEN_TRADES_PATH),
            "warning_minutes": 120,
            "critical_minutes": 240,
            "missing_tone": "critical",
            "count": int(open_trades.get("count", 0) or 0),
            "operator_meaning": "Position posture, SL/TP coverage, and exposure counts may no longer match the actual open book.",
        },
        {
            "key": "trade_log",
            "label": "Trade execution log",
            "path": TRADES_LOG_PATH,
            "observed_at": latest_log_time.replace(microsecond=0).isoformat() if latest_log_time else _path_mtime_iso(TRADES_LOG_PATH),
            "warning_minutes": 90,
            "critical_minutes": 180,
            "missing_tone": "critical",
            "count": len(recent_trade_log),
            "operator_meaning": "Recent fills, opens, and no-trade timing evidence may be incomplete or lagging.",
        },
        {
            "key": "trade_context_journal",
            "label": "Trade-context journal",
            "path": TRADE_CONTEXT_JOURNAL_PATH,
            "observed_at": _path_mtime_iso(TRADE_CONTEXT_JOURNAL_PATH),
            "warning_minutes": 120,
            "critical_minutes": 240,
            "missing_tone": "warning",
            "count": len(journal_trades),
            "operator_meaning": "Exit attribution, regime/session context, and recent explainability surfaces may be incomplete.",
        },
        {
            "key": "unmatched_closed_deals",
            "label": "Unmatched closed-deal artifact",
            "path": UNMATCHED_CLOSED_DEALS_PATH,
            "observed_at": _path_mtime_iso(UNMATCHED_CLOSED_DEALS_PATH),
            "warning_minutes": 360,
            "critical_minutes": 720,
            "missing_tone": "warning",
            "count": len(unmatched_rows),
            "operator_meaning": "Reconciliation warnings may be lagging, especially if new closed deals are failing to pair.",
        },
        {
            "key": "system_log",
            "label": "System log feed",
            "path": latest_system_log_path,
            "observed_at": _path_mtime_iso(latest_system_log_path) if latest_system_log_path else None,
            "warning_minutes": 120,
            "critical_minutes": 240,
            "missing_tone": "warning",
            "count": int(trade_context_registration_failures.get("count", 0) or 0),
            "operator_meaning": "Registration-failure monitoring may miss fresh exceptions until the runtime emits new system-log lines.",
        },
    ]

    rows: List[Dict[str, Any]] = []
    tone_counts: Counter[str] = Counter()

    for spec in artifact_specs:
        path = spec.get("path")
        exists = bool(path and isinstance(path, Path) and path.exists())
        observed_at = parse_iso_datetime(spec.get("observed_at"))
        minutes_old = None
        if observed_at:
            minutes_old = max(int((now - observed_at).total_seconds() // 60), 0)

        tone = "success"
        status = "healthy"
        detail = "Artifact freshness is within the expected execution window."
        count = spec.get("count")
        missing_tone = str(spec.get("missing_tone") or "warning")
        warning_minutes = int(spec.get("warning_minutes") or 120)
        critical_minutes = int(spec.get("critical_minutes") or 240)

        if not exists:
            tone = missing_tone
            status = "missing"
            detail = "Artifact file is missing, so this execution surface cannot be trusted fully."
        elif minutes_old is None:
            tone = "warning"
            status = "unknown"
            detail = "Artifact exists, but its freshness timestamp could not be parsed."
        elif spec.get("key") == "unmatched_closed_deals" and int(count or 0) == 0 and minutes_old >= warning_minutes:
            tone = "neutral"
            status = "quiet"
            detail = f"Artifact is {minutes_old} minute(s) old, but it currently contains no unresolved rows."
        elif minutes_old >= critical_minutes:
            tone = "critical"
            status = "critical_stale"
            detail = f"Artifact is {minutes_old} minute(s) old, beyond the critical freshness threshold."
        elif minutes_old >= warning_minutes:
            tone = "warning"
            status = "watch"
            detail = f"Artifact is {minutes_old} minute(s) old, beyond the watch threshold."

        note_parts: List[str] = []
        if count is not None:
            note_parts.append(f"visible count {int(count)}")
        if path and isinstance(path, Path):
            note_parts.append(path.name)

        tone_counts[tone] += 1
        rows.append({
            "key": spec.get("key"),
            "label": spec.get("label"),
            "tone": tone,
            "status": status,
            "path": str(path) if path else None,
            "observed_at": observed_at.replace(microsecond=0).isoformat() if observed_at else None,
            "minutes_old": minutes_old,
            "detail": detail,
            "operator_meaning": spec.get("operator_meaning"),
            "note": " · ".join(note_parts) if note_parts else None,
        })

    headline = "Execution artifacts look fresh"
    summary_tone = "success"
    if tone_counts.get("critical"):
        headline = f"{tone_counts['critical']} execution artifact(s) are critically stale"
        summary_tone = "critical"
    elif tone_counts.get("warning"):
        headline = f"{tone_counts['warning']} execution artifact(s) need freshness review"
        summary_tone = "warning"
    elif tone_counts.get("neutral"):
        headline = "Some low-traffic execution artifacts are quiet but not actively unhealthy"
        summary_tone = "info"

    return {
        "headline": headline,
        "tone": summary_tone,
        "critical_count": int(tone_counts.get("critical", 0)),
        "warning_count": int(tone_counts.get("warning", 0)),
        "missing_count": sum(1 for row in rows if row.get("status") == "missing"),
        "healthy_count": int(tone_counts.get("success", 0)),
        "artifacts": rows,
    }


def _build_recent_fill_exit_summary(recent_trade_log: List[Dict[str, Any]], trade_context_journal: Dict[str, Any], *, window_hours: int = 24) -> Dict[str, Any]:
    fill_rows: List[Dict[str, Any]] = []
    now = datetime.now(timezone.utc)
    window_start = now - timedelta(hours=window_hours)

    for row in recent_trade_log:
        if not isinstance(row, dict):
            continue
        reason = str(row.get("reason") or row.get("event") or row.get("type") or "").strip().lower()
        if reason and reason not in {"executed", "filled", "opened", "open"}:
            continue

        timestamp = parse_iso_datetime(row.get("ts") or row.get("timestamp") or row.get("recorded_at") or row.get("time"))
        volume = _safe_float(row.get("vol") or row.get("volume") or row.get("lots"))
        fill_rows.append({
            "timestamp": timestamp.replace(microsecond=0).isoformat() if timestamp else None,
            "strategy_name": row.get("strategy") or row.get("strategy_name"),
            "symbol": row.get("symbol"),
            "side": _canonical_trade_side(row.get("dir") or row.get("direction") or row.get("side")),
            "ticket": row.get("ticket") or row.get("position_id"),
            "volume": volume,
            "price": _safe_float(row.get("price")),
            "reason": reason or "executed",
            "within_window": bool(timestamp and timestamp >= window_start),
        })

    fill_rows.sort(key=lambda item: str(item.get("timestamp") or ""), reverse=True)
    fills_in_window = [row for row in fill_rows if row.get("within_window")]
    fill_symbol_counts = Counter(str(row.get("symbol") or "unknown") for row in fills_in_window)

    exit_rows: List[Dict[str, Any]] = []
    journal_trades = trade_context_journal.get("trades") or {}
    if isinstance(journal_trades, dict):
        for ticket, row in journal_trades.items():
            if not isinstance(row, dict) or not row.get("exit_time"):
                continue
            timestamp = parse_iso_datetime(row.get("exit_time"))
            pnl = _safe_float(row.get("pnl"))
            exit_context = row.get("exit_context") if isinstance(row.get("exit_context"), dict) else {}
            exit_rows.append({
                "timestamp": timestamp.replace(microsecond=0).isoformat() if timestamp else None,
                "strategy_name": row.get("strategy_name"),
                "symbol": row.get("symbol") or row.get("symbol_canonical"),
                "ticket": row.get("ticket") or ticket,
                "pnl": pnl,
                "session": exit_context.get("session"),
                "regime": exit_context.get("regime"),
                "within_window": bool(timestamp and timestamp >= window_start),
            })

    exit_rows.sort(key=lambda item: str(item.get("timestamp") or ""), reverse=True)
    exits_in_window = [row for row in exit_rows if row.get("within_window")]
    exit_symbol_counts = Counter(str(row.get("symbol") or "unknown") for row in exits_in_window)
    exit_pnls = [float(row.get("pnl") or 0.0) for row in exits_in_window]

    return {
        "window_hours": window_hours,
        "fills": {
            "count": len(fills_in_window),
            "total_volume": round(sum(float(row.get("volume") or 0.0) for row in fills_in_window), 2),
            "buy_count": sum(1 for row in fills_in_window if row.get("side") == "long"),
            "sell_count": sum(1 for row in fills_in_window if row.get("side") == "short"),
            "latest_at": fill_rows[0].get("timestamp") if fill_rows else None,
            "top_symbol": fill_symbol_counts.most_common(1)[0][0] if fill_symbol_counts else None,
            "recent": fill_rows[:8],
        },
        "exits": {
            "count": len(exits_in_window),
            "net_pnl": round(sum(exit_pnls), 2),
            "avg_pnl": round(sum(exit_pnls) / len(exit_pnls), 2) if exit_pnls else 0.0,
            "win_count": sum(1 for pnl in exit_pnls if pnl > 0),
            "loss_count": sum(1 for pnl in exit_pnls if pnl < 0),
            "latest_at": exit_rows[0].get("timestamp") if exit_rows else None,
            "top_symbol": exit_symbol_counts.most_common(1)[0][0] if exit_symbol_counts else None,
            "recent": exit_rows[:8],
        },
    }


def _build_no_trade_diagnosis(
    live_state: Dict[str, Any],
    live_stats: Dict[str, Any],
    open_trades: Dict[str, Any],
    recent_trade_log: List[Dict[str, Any]],
    recent_activity: Dict[str, Any],
    unmatched_rows: List[Dict[str, Any]],
) -> Dict[str, Any]:
    locked_for_day = bool(live_state.get("locked_for_day"))
    open_trade_count = _coerce_int(open_trades.get("count"))
    trades_today = _coerce_int(live_state.get("trades_today"))
    live_strategy_count = _coerce_int(live_stats.get("strategy_count"))
    total_live_trades = _coerce_int(live_stats.get("total_trades"))
    fills = (recent_activity.get("fills") or {}) if isinstance(recent_activity, dict) else {}
    exits = (recent_activity.get("exits") or {}) if isinstance(recent_activity, dict) else {}
    recent_fill_count = _coerce_int(fills.get("count"))
    recent_exit_count = _coerce_int(exits.get("count"))
    unmatched_count = len(unmatched_rows)
    log_timestamps = [
        parse_iso_datetime(row.get("ts") or row.get("timestamp") or row.get("recorded_at") or row.get("time"))
        for row in recent_trade_log
        if isinstance(row, dict)
    ]
    latest_log_time = max((timestamp for timestamp in log_timestamps if timestamp is not None), default=None)
    minutes_since_log = None
    if latest_log_time is not None:
        minutes_since_log = max(int((datetime.now(timezone.utc) - latest_log_time).total_seconds() // 60), 0)

    causes: List[Dict[str, Any]] = []

    def add_cause(key: str, label: str, tone: str, status: str, evidence: str, detail: str) -> None:
        causes.append({
            "key": key,
            "label": label,
            "tone": tone,
            "status": status,
            "evidence": evidence,
            "detail": detail,
        })

    if locked_for_day:
        add_cause(
            "day_lock",
            "Daily lock is suppressing new trades",
            "warning",
            "active",
            f"locked_for_day=true with {trades_today} trade(s) recorded today",
            "Current inactivity can be intentional because the runtime reports the trading day as locked.",
        )
    else:
        add_cause(
            "day_lock",
            "Daily lock is not active",
            "success",
            "clear",
            f"locked_for_day=false with {trades_today} trade(s) today",
            "The backend does not report a day-level lock, so inactivity needs another explanation.",
        )

    if open_trade_count > 0:
        add_cause(
            "open_positions",
            "Open positions are already engaged",
            "info",
            "context",
            f"{open_trade_count} open trade(s) visible in the latest snapshot",
            "This is not a true no-trade state because the executor is already carrying live exposure.",
        )
    else:
        add_cause(
            "open_positions",
            "No open positions in the current snapshot",
            "warning",
            "active",
            "0 open trades reported by execution/open_trades.json",
            "If the desk expected live exposure right now, the operator should look to fills, exits, and telemetry freshness next.",
        )

    if recent_fill_count > 0:
        add_cause(
            "recent_fills",
            "Recent fills show the executor was active",
            "info",
            "context",
            f"{recent_fill_count} fill(s) in the last {recent_activity.get('window_hours', 24)}h",
            "The system has traded recently, so zero open positions may simply mean entries were short-lived or already closed.",
        )
    else:
        add_cause(
            "recent_fills",
            "No recent fills in the active lookback window",
            "warning",
            "active",
            f"0 fills in the last {recent_activity.get('window_hours', 24)}h",
            "Recent execution traces do not show fresh entries, which strengthens the no-trade diagnosis.",
        )

    if recent_exit_count > 0 and recent_fill_count == 0 and open_trade_count == 0:
        add_cause(
            "recent_exits_only",
            "Recent exits without new entries",
            "warning",
            "active",
            f"{recent_exit_count} exit(s) but no fills in the same lookback window",
            "Positions may have been closed out while no replacement entries were triggered afterward.",
        )
    elif recent_exit_count > 0:
        add_cause(
            "recent_exits_only",
            "Recent exits are visible",
            "neutral",
            "context",
            f"{recent_exit_count} exit(s) in the last {recent_activity.get('window_hours', 24)}h",
            "Recent exits provide context for posture changes even if they do not explain the current state by themselves.",
        )

    if live_strategy_count == 0:
        add_cause(
            "live_strategy_stats",
            "Live strategy stats are missing",
            "critical",
            "active",
            "strategy_live_stats returned zero active strategy rows",
            "No-trade diagnosis is weak because backend telemetry for live strategies is currently absent.",
        )
    else:
        add_cause(
            "live_strategy_stats",
            "Live strategy telemetry is present",
            "success",
            "clear",
            f"{live_strategy_count} strategy row(s), {total_live_trades} total live trades",
            "Backend strategy telemetry is populated, so inactivity is less likely to be caused by a total stats outage.",
        )

    if unmatched_count > 0:
        add_cause(
            "reconciliation",
            "Reconciliation anomalies still need cleanup",
            "critical" if unmatched_count >= 5 else "warning",
            "active",
            f"{unmatched_count} unmatched closed deal(s) remain unresolved",
            "Execution may still be trading, but reconciliation noise reduces trust in the runtime picture and deserves operator review.",
        )
    else:
        add_cause(
            "reconciliation",
            "Closed-deal reconciliation is clean",
            "success",
            "clear",
            "0 unmatched closed deals in the latest snapshot",
            "There is no current evidence that pairing failures are masking trade activity.",
        )

    if minutes_since_log is None:
        add_cause(
            "log_freshness",
            "Trade log freshness is unknown",
            "warning",
            "active",
            "No parsable timestamps were found in the recent trade log sample",
            "Without fresh log timestamps, it is harder to separate true inactivity from missing execution traces.",
        )
    elif minutes_since_log >= 360 and open_trade_count == 0:
        add_cause(
            "log_freshness",
            "Execution traces look stale",
            "warning",
            "active",
            f"Latest trade-log event is {minutes_since_log} minute(s) old",
            "The runtime has not emitted a recent trade trace, which makes a genuine no-trade lull more plausible.",
        )
    else:
        add_cause(
            "log_freshness",
            "Execution trace freshness looks acceptable",
            "success" if minutes_since_log <= 120 else "info",
            "clear" if minutes_since_log <= 120 else "context",
            f"Latest trade-log event is {minutes_since_log} minute(s) old",
            "Recent trade-log timestamps are still fresh enough to support operator diagnosis.",
        )

    active_causes = [cause for cause in causes if cause.get("status") == "active"]
    if locked_for_day:
        posture = "locked"
        headline = "Inactivity currently looks intentional"
        detail = "The strongest visible cause is the day-level lock, with supporting context from the latest execution snapshot."
    elif open_trade_count > 0:
        posture = "engaged"
        headline = "The executor is active, not fully idle"
        detail = "Open positions or recent fills indicate the runtime is already engaged, so this section is mostly explaining posture rather than a true no-trade gap."
    elif live_strategy_count == 0:
        posture = "telemetry_gap"
        headline = "Telemetry gap is the main blocker"
        detail = "The most important issue is missing live strategy stats, which limits confidence in every other no-trade signal."
    elif active_causes:
        posture = "inactive_watch"
        headline = "No-trade risk deserves operator review"
        detail = "There are active causes that explain why the system currently has little or no visible execution activity."
    else:
        posture = "clear"
        headline = "No strong no-trade blocker is visible"
        detail = "The runtime snapshot does not currently point to a dominant cause for inactivity."

    return {
        "posture": posture,
        "headline": headline,
        "detail": detail,
        "primary_cause": active_causes[0].get("label") if active_causes else None,
        "active_cause_count": len(active_causes),
        "causes": causes,
    }


def _normalize_symbol_key(value: Any) -> str:
    symbol = str(value or "").strip().upper()
    if symbol.endswith("M") and len(symbol) > 3:
        return symbol[:-1]
    return symbol


def _canonical_trade_side(value: Any) -> str:
    side = str(value or "").strip().lower()
    if side in {"buy", "long"}:
        return "long"
    if side in {"sell", "short"}:
        return "short"
    return side or "unknown"


def _build_open_trade_drilldown(
    trades: List[Dict[str, Any]],
    live_stats: Dict[str, Any],
    recent_trade_log: List[Dict[str, Any]],
) -> Dict[str, Any]:
    strategy_rows = (live_stats.get("strategies") or {}) if isinstance(live_stats, dict) else {}
    if not isinstance(strategy_rows, dict):
        strategy_rows = {}

    recent_trade_keys = {
        (str(row.get("strategy") or row.get("strategy_name") or ""), _normalize_symbol_key(row.get("symbol")), _canonical_trade_side(row.get("dir") or row.get("direction") or row.get("side")))
        for row in recent_trade_log
        if isinstance(row, dict)
    }

    by_symbol: Dict[str, Dict[str, Any]] = {}
    drilldown_rows: List[Dict[str, Any]] = []
    protected_count = 0
    incomplete_protection_count = 0
    aged_trade_count = 0
    stale_update_count = 0
    floating_loss_count = 0
    total_floating_pnl = 0.0
    manual_open_trade_count = 0
    manual_net_floating_pnl = 0.0

    now = datetime.now(timezone.utc)

    for trade in trades:
        is_manual = is_manual_trade_payload(trade)
        strategy_name = str(trade.get("strategy_name") or trade.get("comment") or "")
        symbol = str(trade.get("symbol") or "")
        normalized_symbol = _normalize_symbol_key(symbol)
        side = _canonical_trade_side(trade.get("side") or trade.get("direction") or trade.get("dir"))
        volume = _safe_float(trade.get("volume") or trade.get("lots")) or 0.0
        floating_pnl = _safe_float(trade.get("floating_pnl") or trade.get("pnl") or trade.get("profit")) or 0.0
        open_price = _safe_float(trade.get("open_price"))
        stop_loss = _safe_float(trade.get("sl"))
        take_profit = _safe_float(trade.get("tp"))
        open_time = parse_iso_datetime(trade.get("open_time") or trade.get("opened_at"))
        last_update = parse_iso_datetime(trade.get("last_update") or trade.get("updated_at"))
        live_row = strategy_rows.get(strategy_name) if isinstance(strategy_rows.get(strategy_name), dict) else {}
        live_total_pnl = _safe_float((live_row or {}).get("total_pnl"))
        live_num_trades = _safe_int((live_row or {}).get("num_trades"))
        recent_pnls = list((live_row or {}).get("recent_pnls") or [])[:5]

        age_minutes = int((now - open_time).total_seconds() // 60) if open_time else None
        minutes_since_update = int((now - last_update).total_seconds() // 60) if last_update else None

        stop_distance = abs(open_price - stop_loss) if open_price is not None and stop_loss is not None else None
        target_distance = abs(take_profit - open_price) if open_price is not None and take_profit is not None else None
        risk_reward = round(target_distance / stop_distance, 2) if stop_distance and target_distance and stop_distance > 0 else None

        has_stop = stop_loss is not None
        has_target = take_profit is not None
        protection_status = "sl_tp" if has_stop and has_target else "sl_only" if has_stop else "tp_only" if has_target else "unprotected"

        flags: List[str] = []
        if floating_pnl < 0:
            flags.append("floating_loss")
            floating_loss_count += 1
        if is_manual:
            flags.append("manual_user")
            manual_open_trade_count += 1
            manual_net_floating_pnl += floating_pnl
        if protection_status != "sl_tp":
            flags.append("incomplete_protection")
            incomplete_protection_count += 1
        else:
            protected_count += 1
        if age_minutes is not None and age_minutes >= 240:
            flags.append("aged_position")
            aged_trade_count += 1
        if minutes_since_update is not None and minutes_since_update >= 60:
            flags.append("stale_update")
            stale_update_count += 1
        if not live_row:
            flags.append("missing_live_stats")
        if (strategy_name, normalized_symbol, side) not in recent_trade_keys:
            flags.append("no_recent_log_match")

        total_floating_pnl += floating_pnl

        symbol_bucket = by_symbol.setdefault(
            symbol or normalized_symbol or "unknown",
            {
                "symbol": symbol or normalized_symbol or "unknown",
                "open_trade_count": 0,
                "net_floating_pnl": 0.0,
                "total_volume": 0.0,
                "strategies": set(),
                "oldest_open_time": None,
                "aged_trade_count": 0,
                "floating_loss_count": 0,
                "manual_open_trade_count": 0,
            },
        )
        symbol_bucket["open_trade_count"] += 1
        symbol_bucket["net_floating_pnl"] += floating_pnl
        symbol_bucket["total_volume"] += volume
        if is_manual:
            symbol_bucket["manual_open_trade_count"] += 1
        if strategy_name:
            symbol_bucket["strategies"].add(strategy_name)
        if age_minutes is not None and age_minutes >= 240:
            symbol_bucket["aged_trade_count"] += 1
        if floating_pnl < 0:
            symbol_bucket["floating_loss_count"] += 1
        current_oldest = parse_iso_datetime(symbol_bucket.get("oldest_open_time"))
        if open_time and (current_oldest is None or open_time < current_oldest):
            symbol_bucket["oldest_open_time"] = open_time.replace(microsecond=0).isoformat()

        drilldown_rows.append({
            **trade,
            "strategy_name": strategy_name or None,
            "symbol_normalized": normalized_symbol or None,
            "side": side,
            "floating_pnl": floating_pnl,
            "volume": volume,
            "open_price": open_price,
            "sl": stop_loss,
            "tp": take_profit,
            "holding_minutes": age_minutes,
            "minutes_since_update": minutes_since_update,
            "stop_distance": round(stop_distance, 5) if stop_distance is not None else None,
            "target_distance": round(target_distance, 5) if target_distance is not None else None,
            "risk_reward": risk_reward,
            "protection_status": protection_status,
            "live_total_pnl": live_total_pnl,
            "live_num_trades": live_num_trades,
            "recent_realized_pnls": recent_pnls,
            "is_manual": is_manual,
            "order_origin": str(trade.get("order_origin") or ("manual_user" if is_manual else "autonomous_strategy")),
            "origin_label": "Manual user" if is_manual else "Autonomous strategy",
            "origin_tone": "warning" if is_manual else "info",
            "exclude_from_strategy_eval": bool(trade.get("exclude_from_strategy_eval")) or is_manual,
            "operator_flags": flags,
        })

    by_symbol_rows = []
    for bucket in by_symbol.values():
        strategies = sorted(bucket["strategies"])
        oldest_open_time = bucket.get("oldest_open_time")
        oldest_age_minutes = None
        oldest_open_dt = parse_iso_datetime(oldest_open_time)
        if oldest_open_dt:
            oldest_age_minutes = int((now - oldest_open_dt).total_seconds() // 60)
        by_symbol_rows.append({
            "symbol": bucket["symbol"],
            "open_trade_count": bucket["open_trade_count"],
            "net_floating_pnl": round(float(bucket["net_floating_pnl"]), 2),
            "total_volume": round(float(bucket["total_volume"]), 4),
            "strategy_count": len(strategies),
            "strategies": strategies,
            "oldest_open_time": oldest_open_time,
            "oldest_age_minutes": oldest_age_minutes,
            "aged_trade_count": bucket["aged_trade_count"],
            "floating_loss_count": bucket["floating_loss_count"],
            "manual_open_trade_count": bucket["manual_open_trade_count"],
        })

    by_symbol_rows.sort(key=lambda row: (abs(float(row["net_floating_pnl"])), int(row["open_trade_count"])), reverse=True)
    drilldown_rows.sort(
        key=lambda row: (
            abs(float(row.get("floating_pnl") or 0.0)),
            int(row.get("holding_minutes") or 0),
            str(row.get("strategy_name") or ""),
        ),
        reverse=True,
    )

    return {
        "summary": {
            "symbol_count": len(by_symbol_rows),
            "net_floating_pnl": round(total_floating_pnl, 2),
            "protected_count": protected_count,
            "incomplete_protection_count": incomplete_protection_count,
            "aged_trade_count": aged_trade_count,
            "stale_update_count": stale_update_count,
            "floating_loss_count": floating_loss_count,
            "manual_open_trade_count": manual_open_trade_count,
            "autonomous_open_trade_count": max(len(drilldown_rows) - manual_open_trade_count, 0),
            "manual_net_floating_pnl": round(manual_net_floating_pnl, 2),
            "by_symbol": by_symbol_rows,
        },
        "drilldown": drilldown_rows,
    }


def _build_unmatched_closed_deal_dashboard(unmatched_rows: List[Dict[str, Any]], trade_context_journal: Dict[str, Any]) -> Dict[str, Any]:
    journal_trades = trade_context_journal.get("trades") or {}
    if not isinstance(journal_trades, dict):
        journal_trades = {}

    now = datetime.now(timezone.utc)
    lane_counts: Counter[str] = Counter()
    reason_counts: Counter[str] = Counter()
    symbol_totals: Dict[str, Dict[str, Any]] = defaultdict(lambda: {
        "symbol": "unknown",
        "count": 0,
        "recoverable_count": 0,
        "profit": 0.0,
        "latest_recorded_at": None,
    })
    manual_bucket_counts: Counter[str] = Counter()
    confidence_counts: Counter[str] = Counter()
    signal_counts: Counter[str] = Counter()
    total_profit = 0.0
    recoverable_count = 0
    ambiguous_count = 0
    manual_bucket_only_count = 0
    journal_context_count = 0
    newest_recorded_at: str | None = None
    oldest_recorded_at: str | None = None
    newest_dt: datetime | None = None
    oldest_dt: datetime | None = None
    enriched_rows: List[Dict[str, Any]] = []

    for raw_row in unmatched_rows:
        if not isinstance(raw_row, dict):
            continue

        row = dict(raw_row)
        symbol = str(row.get("symbol_canonical") or row.get("symbol") or "unknown")
        reason = str(row.get("reason") or "unknown")
        manual_bucket = str(row.get("manual_bucket") or "")
        candidate_matches = row.get("candidate_matches") or []
        if not isinstance(candidate_matches, list):
            candidate_matches = []
        candidate_matches = [str(candidate) for candidate in candidate_matches if candidate]
        candidate_matches = list(dict.fromkeys(candidate_matches))[:5]
        alias_count = sum(1 for key in ("deal_ticket", "order_ticket", "position_id") if row.get(key) not in (None, ""))

        journal_context = None
        for key in (row.get("deal_ticket"), row.get("position_id"), row.get("order_ticket"), row.get("ticket")):
            if key in (None, ""):
                continue
            candidate = journal_trades.get(str(key))
            if isinstance(candidate, dict):
                journal_context = candidate
                break

        pairing_reasons: List[str] = []
        pairing_signal_flags: List[str] = []
        pairing_score = 0

        if len(candidate_matches) == 1:
            lane = "recoverable"
            lane_label = "Single candidate match"
            lane_detail = f"Heuristics narrowed this deal to {candidate_matches[0]}."
            recoverable_count += 1
            pairing_score += 3
            pairing_reasons.append(f"single candidate match ({candidate_matches[0]})")
            pairing_signal_flags.append("single_candidate_match")
        elif len(candidate_matches) > 1:
            lane = "ambiguous"
            lane_label = "Multiple candidates"
            lane_detail = "Ticket/comment hints found more than one possible strategy."
            ambiguous_count += 1
            pairing_score += 1
            pairing_reasons.append(f"{len(candidate_matches)} candidate matches still compete")
            pairing_signal_flags.append("multiple_candidate_matches")
        elif manual_bucket:
            lane = "manual_bucket_only"
            lane_label = "Manual bucket fallback"
            lane_detail = f"PnL landed in {manual_bucket} because no unique strategy lineage was recovered."
            manual_bucket_only_count += 1
            pairing_reasons.append(f"manual fallback bucket {manual_bucket}")
            pairing_signal_flags.append("manual_bucket_fallback")
        else:
            lane = "unclassified"
            lane_label = "No recovery hints"
            lane_detail = "The audit row has no unique candidate match or manual fallback label."
            pairing_reasons.append("no candidate strategy lineage was recovered")
            pairing_signal_flags.append("no_candidate_lineage")

        if journal_context:
            journal_context_count += 1
            pairing_score += 1
            pairing_signal_flags.append("journal_context")
            strategy_name = journal_context.get("strategy_name")
            if strategy_name:
                pairing_reasons.append(f"trade-context journal hit for {strategy_name}")
                if lane != "recoverable":
                    lane_detail = f"{lane_detail} A trade-context journal row exists for {strategy_name}."
            else:
                pairing_reasons.append("trade-context journal hit")

        if alias_count >= 2:
            pairing_score += 1
            pairing_reasons.append(f"{alias_count} ticket aliases align")
            pairing_signal_flags.append("multiple_ticket_aliases")
        elif alias_count == 1:
            pairing_reasons.append("one ticket alias is available")
            pairing_signal_flags.append("single_ticket_alias")

        if row.get("comment_uid4"):
            pairing_score += 1
            pairing_reasons.append("comment UID is present")
            pairing_signal_flags.append("comment_uid")

        if lane == "recoverable" and pairing_score >= 5:
            pairing_confidence = "high"
        elif lane in {"recoverable", "ambiguous"} and pairing_score >= 2:
            pairing_confidence = "medium"
        else:
            pairing_confidence = "low"

        confidence_counts[pairing_confidence] += 1
        for flag in pairing_signal_flags:
            signal_counts[flag] += 1

        recorded_at = row.get("recorded_at")
        recorded_dt = parse_iso_datetime(recorded_at)
        if recorded_dt:
            if newest_dt is None or recorded_dt > newest_dt:
                newest_dt = recorded_dt
                newest_recorded_at = recorded_dt.isoformat()
            if oldest_dt is None or recorded_dt < oldest_dt:
                oldest_dt = recorded_dt
                oldest_recorded_at = recorded_dt.isoformat()
            age_minutes = max(int((now - recorded_dt).total_seconds() // 60), 0)
        else:
            age_minutes = None

        try:
            profit = float(row.get("profit") if row.get("profit") is not None else row.get("pnl") or 0.0)
        except Exception:
            profit = 0.0
        total_profit += profit

        lane_counts[lane] += 1
        reason_counts[reason] += 1
        if manual_bucket:
            manual_bucket_counts[manual_bucket] += 1

        symbol_row = symbol_totals[symbol]
        symbol_row["symbol"] = symbol
        symbol_row["count"] += 1
        symbol_row["profit"] = round(float(symbol_row.get("profit") or 0.0) + profit, 2)
        if lane == "recoverable":
            symbol_row["recoverable_count"] += 1
        if not symbol_row.get("latest_recorded_at") or (recorded_at and str(recorded_at) > str(symbol_row.get("latest_recorded_at"))):
            symbol_row["latest_recorded_at"] = recorded_at

        enriched_rows.append({
            **row,
            "symbol": symbol,
            "reason": reason,
            "manual_bucket": manual_bucket or None,
            "candidate_matches": candidate_matches,
            "candidate_count": len(candidate_matches),
            "ticket_alias_count": alias_count,
            "has_comment_uid4": bool(row.get("comment_uid4")),
            "journal_context_present": bool(journal_context),
            "journal_strategy_name": journal_context.get("strategy_name") if journal_context else None,
            "resolution_lane": lane,
            "resolution_label": lane_label,
            "resolution_detail": lane_detail,
            "pairing_confidence": pairing_confidence,
            "pairing_score": pairing_score,
            "pairing_confidence_detail": "; ".join(pairing_reasons) if pairing_reasons else "No confidence signals were captured.",
            "pairing_signal_flags": pairing_signal_flags,
            "age_minutes": age_minutes,
            "profit": round(profit, 2),
        })

    lane_meta = {
        "recoverable": ("success", "Single-candidate heuristic recovery"),
        "ambiguous": ("warning", "More than one strategy candidate needs operator choice"),
        "manual_bucket_only": ("critical", "PnL was bucketed manually without a unique strategy link"),
        "unclassified": ("critical", "The row lacks enough hints for automatic recovery"),
    }

    enriched_rows.sort(
        key=lambda row: (
            parse_iso_datetime(row.get("recorded_at")) or datetime.fromtimestamp(0, tz=timezone.utc),
            str(row.get("deal_ticket") or row.get("position_id") or ""),
        ),
        reverse=True,
    )

    confidence_meta = {
        "high": {
            "tone": "success",
            "detail": "Exactly one strategy candidate survived and at least two corroborating hints were present.",
        },
        "medium": {
            "tone": "warning",
            "detail": "There is some usable lineage evidence, but the operator should still verify before trusting the pairing.",
        },
        "low": {
            "tone": "critical",
            "detail": "The row lacks enough corroboration and should be treated as weak attribution evidence.",
        },
    }
    signal_meta = {
        "single_candidate_match": {
            "label": "Single candidate match",
            "impact": "positive",
            "detail": "Heuristics collapsed to one strategy name.",
        },
        "multiple_candidate_matches": {
            "label": "Multiple candidate matches",
            "impact": "mixed",
            "detail": "The candidate set is useful, but an operator still has to choose between several strategies.",
        },
        "manual_bucket_fallback": {
            "label": "Manual bucket fallback",
            "impact": "negative",
            "detail": "The row fell back to a manual bucket because no unique lineage was recovered.",
        },
        "no_candidate_lineage": {
            "label": "No candidate lineage",
            "impact": "negative",
            "detail": "The audit row currently offers no candidate strategy names.",
        },
        "journal_context": {
            "label": "Trade-context journal hit",
            "impact": "positive",
            "detail": "The ticket or position appears in the trade-context journal.",
        },
        "multiple_ticket_aliases": {
            "label": "Multiple ticket aliases",
            "impact": "positive",
            "detail": "Several ticket identifiers line up on the same row.",
        },
        "single_ticket_alias": {
            "label": "Single ticket alias",
            "impact": "mixed",
            "detail": "Only one ticket identifier is available, so the linkage is thinner.",
        },
        "comment_uid": {
            "label": "Comment UID present",
            "impact": "positive",
            "detail": "The close row preserved a comment UID that can support attribution.",
        },
    }

    return {
        "summary": {
            "count": len(enriched_rows),
            "symbols_affected": len(symbol_totals),
            "recoverable_count": recoverable_count,
            "ambiguous_count": ambiguous_count,
            "manual_bucket_only_count": manual_bucket_only_count,
            "journal_context_count": journal_context_count,
            "manual_bucket_count": sum(manual_bucket_counts.values()),
            "total_profit": round(total_profit, 2),
            "newest_recorded_at": newest_recorded_at,
            "oldest_recorded_at": oldest_recorded_at,
        },
        "confidence": {
            "heuristic": "High confidence requires one surviving strategy candidate plus corroborating evidence such as journal context, multiple ticket aliases, or a preserved comment UID. Medium means some lineage exists but operator confirmation is still warranted. Low means the row is mostly manual or uncorroborated.",
            "buckets": [
                {
                    "key": key,
                    "label": key,
                    "count": int(confidence_counts.get(key, 0)),
                    "tone": confidence_meta[key]["tone"],
                    "detail": confidence_meta[key]["detail"],
                }
                for key in ("high", "medium", "low")
            ],
            "signals": [
                {
                    "key": key,
                    "label": meta["label"],
                    "count": int(signal_counts.get(key, 0)),
                    "impact": meta["impact"],
                    "detail": meta["detail"],
                }
                for key, meta in signal_meta.items()
                if int(signal_counts.get(key, 0)) > 0
            ],
        },
        "lanes": [
            {
                "key": lane,
                "label": lane.replace("_", " "),
                "count": count,
                "tone": lane_meta.get(lane, ("warning", ""))[0],
                "detail": lane_meta.get(lane, ("warning", "Needs inspection"))[1],
            }
            for lane, count in sorted(lane_counts.items(), key=lambda item: (-item[1], item[0]))
        ],
        "reasons": [
            {"reason": reason, "count": count}
            for reason, count in sorted(reason_counts.items(), key=lambda item: (-item[1], item[0]))
        ],
        "symbols": sorted(
            symbol_totals.values(),
            key=lambda row: (-int(row.get("count") or 0), -abs(float(row.get("profit") or 0.0)), str(row.get("symbol") or "")),
        )[:10],
        "manual_buckets": [
            {"bucket": bucket, "count": count}
            for bucket, count in manual_bucket_counts.most_common(10)
        ],
        "recent": enriched_rows[:25],
    }


def load_execution_summary() -> Dict[str, Any]:
    live_state = load_live_state_snapshot()
    live_stats = load_strategy_live_stats_snapshot()
    open_trades = load_open_trades_snapshot()
    recent_trade_log = load_recent_trade_log()
    trade_context_journal = load_trade_context_journal()
    trade_context_registration_failures = load_recent_trade_context_registration_failures()
    open_trade_context = _build_open_trade_drilldown(open_trades.get("trades") or [], live_stats, recent_trade_log)
    recent_activity = _build_recent_fill_exit_summary(recent_trade_log, trade_context_journal)
    unmatched_rows = read_json_file(UNMATCHED_CLOSED_DEALS_PATH, default=[])
    if not isinstance(unmatched_rows, list):
        unmatched_rows = []
    unmatched_dashboard = _build_unmatched_closed_deal_dashboard(unmatched_rows, trade_context_journal)
    execution_artifact_warnings = _build_execution_artifact_warnings(
        live_state,
        live_stats,
        open_trades,
        recent_trade_log,
        trade_context_journal,
        unmatched_rows,
        trade_context_registration_failures,
    )
    no_trade_diagnosis = _build_no_trade_diagnosis(
        live_state,
        live_stats,
        open_trades,
        recent_trade_log,
        recent_activity,
        unmatched_rows,
    )
    return {
        "generated_at": utc_now_iso(),
        "live_state": live_state,
        "strategy_live_stats": {
            "strategy_count": live_stats["strategy_count"],
            "total_realized_pnl": live_stats["total_realized_pnl"],
            "total_trades": live_stats["total_trades"],
            "top_active": live_stats["top_active"],
        },
        "open_trades": {
            **open_trades,
            **open_trade_context,
        },
        "unmatched_closed_deals": {
            "count": len(unmatched_rows),
            "recent": unmatched_dashboard.get("recent") or unmatched_rows[-20:],
            "dashboard": unmatched_dashboard,
        },
        "execution_artifact_warnings": execution_artifact_warnings,
        "trade_context_registration_failures": trade_context_registration_failures,
        "recent_activity": recent_activity,
        "no_trade_diagnosis": no_trade_diagnosis,
        "recent_trade_log": recent_trade_log,
    }


def load_pool_summary_payload() -> Dict[str, Any]:
    pool = load_pool()
    manifest_by_name = {str(entry.get("name") or ""): entry for entry in load_manifest_entries() if isinstance(entry, dict)}
    index_by_name = {str(entry.get("name") or ""): entry for entry in load_strategy_index_entries() if isinstance(entry, dict)}
    live_stats_snapshot = load_strategy_live_stats_snapshot()
    live_strategy_rows = live_stats_snapshot.get("strategies") or {}
    by_slot: Dict[Tuple[str, str], int] = defaultdict(int)
    family_counts: Counter[str] = Counter()
    symbol_counts: Counter[str] = Counter()
    family_rollups: Dict[str, Dict[str, Any]] = {}
    top_strategies = sorted(pool.strategies.values(), key=lambda rec: float(rec.score or 0.0), reverse=True)[:15]
    for rec in pool.strategies.values():
        name = str(rec.name or "")
        manifest_entry = manifest_by_name.get(name) or {}
        index_entry = index_by_name.get(name) or {}
        live_stats = live_strategy_rows.get(name) if isinstance(live_strategy_rows, dict) else {}
        pool_dict = rec.to_dict()
        stats_block = ((pool_dict or {}).get("stats") or {}) if isinstance(pool_dict, dict) else {}
        explain = ((stats_block.get("strategy_explain") or {}) if isinstance(stats_block, dict) else {})
        meta = explain.get("meta") or {}
        regime_pnl = explain.get("regime_pnl") or {}
        session_pnl = explain.get("session_pnl") or {}
        stability = explain.get("stability") or {}
        risk_behavior = explain.get("risk_behavior") or {}
        live_decay = (stats_block.get("live_decay") or {}) if isinstance(stats_block, dict) else {}

        by_slot[(rec.symbol, rec.timeframe)] += 1
        symbol_counts[str(rec.symbol or "unknown")] += 1
        family = str(
            manifest_entry.get("family")
            or index_entry.get("family")
            or ((stats_block.get("strategy") or {}).get("family") if isinstance(stats_block, dict) else None)
            or stats_block.get("family")
            or (((rec.stats or {}).get("strategy") or {}).get("family") if isinstance(rec.stats, dict) else None)
            or ((rec.stats or {}).get("family") if isinstance(rec.stats, dict) else None)
            or "unknown"
        )
        family_counts[family] += 1

        current_status = str(rec.status or index_entry.get("status") or manifest_entry.get("status") or "unknown")
        score = _safe_float(rec.score)
        research_return_pct = _safe_float(stats_block.get("return_pct"))
        research_sharpe = _safe_float(stats_block.get("sharpe_ratio"))
        live_total_pnl = _safe_float((live_stats or {}).get("total_pnl"))
        live_trade_count = _safe_int((live_stats or {}).get("num_trades"))
        live_vs_research_delta = None
        if live_total_pnl is not None and research_return_pct is not None:
            live_vs_research_delta = live_total_pnl - research_return_pct
        identity = _build_strategy_identity(
            family=family,
            current_status=current_status,
            meta=meta if isinstance(meta, dict) else {},
            risk_behavior=risk_behavior if isinstance(risk_behavior, dict) else {},
            regime_pnl=regime_pnl if isinstance(regime_pnl, dict) else {},
            session_pnl=session_pnl if isinstance(session_pnl, dict) else {},
            stability=stability if isinstance(stability, dict) else {},
            live_decay=live_decay if isinstance(live_decay, dict) else {},
        )

        family_bucket = family_rollups.setdefault(
            family,
            {
                "family": family,
                "label": _humanize_token(family).title(),
                "strategy_count": 0,
                "manifest_count": 0,
                "live_count": 0,
                "active_count": 0,
                "candidate_count": 0,
                "exploratory_count": 0,
                "disabled_count": 0,
                "score_total": 0.0,
                "score_count": 0,
                "research_return_total": 0.0,
                "research_return_count": 0,
                "research_sharpe_total": 0.0,
                "research_sharpe_count": 0,
                "live_pnl_total": 0.0,
                "live_trades_total": 0,
                "live_vs_research_delta_total": 0.0,
                "live_vs_research_delta_count": 0,
                "warning_count": 0,
                "warning_strategy_count": 0,
                "fragility_count": 0,
                "fragility_strategy_count": 0,
                "archetype_counts": Counter(),
                "top_regime_totals": Counter(),
                "top_session_totals": Counter(),
            },
        )
        family_bucket["strategy_count"] += 1
        if name in manifest_by_name:
            family_bucket["manifest_count"] += 1
        if isinstance(live_stats, dict) and live_stats:
            family_bucket["live_count"] += 1
        if current_status == "active":
            family_bucket["active_count"] += 1
        elif current_status == "candidate":
            family_bucket["candidate_count"] += 1
        elif current_status == "exploratory":
            family_bucket["exploratory_count"] += 1
        elif current_status in {"disabled", "retired"}:
            family_bucket["disabled_count"] += 1
        if score is not None:
            family_bucket["score_total"] += score
            family_bucket["score_count"] += 1
        if research_return_pct is not None:
            family_bucket["research_return_total"] += research_return_pct
            family_bucket["research_return_count"] += 1
        if research_sharpe is not None:
            family_bucket["research_sharpe_total"] += research_sharpe
            family_bucket["research_sharpe_count"] += 1
        if live_total_pnl is not None:
            family_bucket["live_pnl_total"] += live_total_pnl
        if live_trade_count is not None:
            family_bucket["live_trades_total"] += live_trade_count
        if live_vs_research_delta is not None:
            family_bucket["live_vs_research_delta_total"] += live_vs_research_delta
            family_bucket["live_vs_research_delta_count"] += 1

        warnings = identity.get("warnings") if isinstance(identity, dict) else []
        fragility_markers = identity.get("fragility_markers") if isinstance(identity, dict) else []
        warning_count = len(warnings) if isinstance(warnings, list) else 0
        fragility_count = len(fragility_markers) if isinstance(fragility_markers, list) else 0
        family_bucket["warning_count"] += warning_count
        family_bucket["fragility_count"] += fragility_count
        if warning_count:
            family_bucket["warning_strategy_count"] += 1
        if fragility_count:
            family_bucket["fragility_strategy_count"] += 1

        archetype = str((identity or {}).get("archetype") or "")
        if archetype:
            family_bucket["archetype_counts"][archetype] += 1
        best_regime = str(meta.get("best_regime") or "unknown")
        if best_regime and best_regime != "unknown":
            family_bucket["top_regime_totals"][best_regime] += 1
        best_session = str(meta.get("best_session") or "unknown")
        if best_session and best_session != "unknown":
            family_bucket["top_session_totals"][best_session] += 1

    family_comparison_rows: List[Dict[str, Any]] = []
    for family, bucket in family_rollups.items():
        dominant_archetype = None
        if bucket["archetype_counts"]:
            dominant_archetype = bucket["archetype_counts"].most_common(1)[0][0]
        top_regime = None
        if bucket["top_regime_totals"]:
            top_regime = bucket["top_regime_totals"].most_common(1)[0][0]
        top_session = None
        if bucket["top_session_totals"]:
            top_session = bucket["top_session_totals"].most_common(1)[0][0]

        strategy_count = int(bucket["strategy_count"])
        warning_density = (float(bucket["warning_strategy_count"]) / strategy_count) if strategy_count else 0.0
        fragility_density = (float(bucket["fragility_strategy_count"]) / strategy_count) if strategy_count else 0.0
        family_comparison_rows.append(
            {
                "family": family,
                "label": bucket["label"],
                "strategy_count": strategy_count,
                "manifest_count": int(bucket["manifest_count"]),
                "live_count": int(bucket["live_count"]),
                "active_count": int(bucket["active_count"]),
                "candidate_count": int(bucket["candidate_count"]),
                "exploratory_count": int(bucket["exploratory_count"]),
                "disabled_count": int(bucket["disabled_count"]),
                "avg_score": _average_or_none(float(bucket["score_total"]), int(bucket["score_count"])),
                "avg_research_return_pct": _average_or_none(float(bucket["research_return_total"]), int(bucket["research_return_count"])),
                "avg_research_sharpe": _average_or_none(float(bucket["research_sharpe_total"]), int(bucket["research_sharpe_count"])),
                "live_total_pnl": float(bucket["live_pnl_total"]),
                "live_trades_total": int(bucket["live_trades_total"]),
                "avg_live_vs_research_delta": _average_or_none(float(bucket["live_vs_research_delta_total"]), int(bucket["live_vs_research_delta_count"])),
                "warning_count": int(bucket["warning_count"]),
                "warning_strategy_count": int(bucket["warning_strategy_count"]),
                "warning_density": warning_density,
                "fragility_count": int(bucket["fragility_count"]),
                "fragility_strategy_count": int(bucket["fragility_strategy_count"]),
                "fragility_density": fragility_density,
                "dominant_archetype": dominant_archetype,
                "top_regime": top_regime,
                "top_session": top_session,
            }
        )

    family_comparison_rows.sort(
        key=lambda row: (
            int(row["manifest_count"]),
            int(row["active_count"]),
            float(row["avg_research_return_pct"] or float("-inf")),
            int(row["strategy_count"]),
            str(row["family"]),
        ),
        reverse=True,
    )

    strongest_research_family = max(
        family_comparison_rows,
        key=lambda row: float(row["avg_research_return_pct"] or float("-inf")),
        default=None,
    )
    strongest_live_family = max(
        family_comparison_rows,
        key=lambda row: float(row["live_total_pnl"] or float("-inf")),
        default=None,
    )
    deepest_manifest_family = max(
        family_comparison_rows,
        key=lambda row: (int(row["manifest_count"]), int(row["strategy_count"])),
        default=None,
    )
    highest_warning_density_family = max(
        family_comparison_rows,
        key=lambda row: (float(row["warning_density"] or 0.0), int(row["warning_strategy_count"]), int(row["strategy_count"])),
        default=None,
    )
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
        "family_comparison": {
            "rows": family_comparison_rows,
            "summary": {
                "family_count": len(family_comparison_rows),
                "strongest_research_family": strongest_research_family,
                "strongest_live_family": strongest_live_family,
                "deepest_manifest_family": deepest_manifest_family,
                "highest_warning_density_family": highest_warning_density_family,
                "manual_bucket_count": int(live_stats_snapshot.get("manual_bucket_count", 0) or 0),
                "manual_total_trades": int(live_stats_snapshot.get("manual_total_trades", 0) or 0),
                "manual_total_realized_pnl": float(live_stats_snapshot.get("manual_total_realized_pnl", 0.0) or 0.0),
                "manual_exclusion_note": "manual_user buckets are excluded from pool family scoreboards and live-vs-research attribution.",
            },
        },
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
    manifest_entries = load_manifest_entries()
    index_entries = load_strategy_index_entries()
    manifest_by_name = {str(entry.get("name") or ""): entry for entry in manifest_entries if isinstance(entry, dict)}
    index_by_name = {str(entry.get("name") or ""): entry for entry in index_entries if isinstance(entry, dict)}
    manifest_entry = manifest_by_name.get(name)
    index_entry = index_by_name.get(name)
    pool = load_pool()
    pool_rec = pool.strategies.get(name)
    live_strategy_rows = load_strategy_live_stats_snapshot().get("strategies", {})
    stats = live_strategy_rows.get(name)
    if not any([manifest_entry, index_entry, pool_rec, stats]):
        return None

    pool_dict = pool_rec.to_dict() if pool_rec else None
    stats_block = ((pool_dict or {}).get("stats") or {}) if isinstance(pool_dict, dict) else {}
    explain = ((stats_block.get("strategy_explain") or {}) if isinstance(stats_block, dict) else {})
    regime_pnl = explain.get("regime_pnl") or {}
    session_pnl = explain.get("session_pnl") or {}
    meta = explain.get("meta") or {}
    stability = explain.get("stability") or {}
    risk_behavior = explain.get("risk_behavior") or {}
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

    detail_symbol = str((manifest_entry or {}).get("symbol") or (index_entry or {}).get("symbol") or (pool_dict or {}).get("symbol") or "")
    detail_timeframe = str((manifest_entry or {}).get("timeframe") or (index_entry or {}).get("timeframe") or (pool_dict or {}).get("timeframe") or "")
    similarity_panel = _build_strategy_similarity_panel(
        target_name=name,
        pool=pool,
        manifest_by_name=manifest_by_name,
        index_by_name=index_by_name,
        live_strategy_rows=live_strategy_rows if isinstance(live_strategy_rows, dict) else {},
    )

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
        "strategy_identity": _build_strategy_identity(
            family=family,
            current_status=current_status,
            meta=meta if isinstance(meta, dict) else {},
            risk_behavior=risk_behavior if isinstance(risk_behavior, dict) else {},
            regime_pnl=regime_pnl if isinstance(regime_pnl, dict) else {},
            session_pnl=session_pnl if isinstance(session_pnl, dict) else {},
            stability=stability if isinstance(stability, dict) else {},
            live_decay=live_decay if isinstance(live_decay, dict) else {},
        ),
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
        "similarity_panel": similarity_panel,
        "duplicate_risk_context": _build_strategy_duplicate_risk_context(
            symbol=detail_symbol,
            timeframe=detail_timeframe,
            family=family,
            similarity_panel=similarity_panel if isinstance(similarity_panel, dict) else {},
        ),
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

    summary = _summarize_research_payload(payload)

    return {
        "generated_at": payload.get("generated_at") or utc_now_iso(),
        "symbol": payload.get("symbol") or symbol,
        "timeframe": payload.get("timeframe") or timeframe,
        "families": summary["families"],
        "funnel_totals": summary["funnel_totals"],
        "rejection_totals": summary["rejection_totals"],
        "top_rejection_samples": summary["top_rejection_samples"],
        "family_skip_drilldown": summary["family_skip_drilldown"],
        "comparison": _build_research_comparison(symbol, timeframe, payload, summary),
        "available_filters": artifacts,
    }


def load_drift_summary() -> Dict[str, Any]:
    pool = load_pool()
    live_stats_snapshot = load_strategy_live_stats_snapshot()
    live_stats = live_stats_snapshot.get("strategies", {})
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
            "manual_bucket_count": int(live_stats_snapshot.get("manual_bucket_count", 0) or 0),
            "manual_total_trades": int(live_stats_snapshot.get("manual_total_trades", 0) or 0),
            "manual_total_realized_pnl": float(live_stats_snapshot.get("manual_total_realized_pnl", 0.0) or 0.0),
            "manual_exclusion_note": "manual_user buckets are excluded from autonomous drift rows and strategy-vs-research comparisons.",
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


def _annotate_audit_event_origin(event: Dict[str, Any]) -> Dict[str, Any]:
    source = str(event.get("source") or "")
    annotated = dict(event)
    is_manual = is_manual_trade_payload(annotated) or bool(annotated.get("manual_bucket"))

    if is_manual:
        origin = "manual_user"
        label = "Manual user"
        tone = "warning"
    elif source == "pool_audit":
        origin = "autonomous_strategy"
        label = "Autonomous strategy"
        tone = "info"
    elif source == "trades_log":
        origin = "autonomous_execution"
        label = "Autonomous execution"
        tone = "info"
    else:
        origin = "execution_audit"
        label = "Execution audit"
        tone = "neutral"

    annotated["is_manual"] = bool(is_manual)
    annotated["event_origin"] = origin
    annotated["event_origin_label"] = label
    annotated["event_origin_tone"] = tone
    if is_manual:
        annotated["exclude_from_strategy_eval"] = True
        stage = str(annotated.get("audit_stage") or "").strip().lower()
        if stage == "preview_intent":
            annotated["manual_lifecycle_stage"] = "preview_intent"
            annotated["manual_lifecycle_label"] = "Preview intent"
            annotated["manual_lifecycle_tone"] = "info"
        elif stage == "submit_intent":
            annotated["manual_lifecycle_stage"] = "submit_intent"
            annotated["manual_lifecycle_label"] = "Submit intent"
            annotated["manual_lifecycle_tone"] = "warning"
        elif stage == "execution_result":
            submit_status = str(annotated.get("submit_status") or "").strip().lower()
            lifecycle_tone = "success" if submit_status in {"submitted", "placed", "filled", "done", "success", "ok"} else "critical"
            annotated["manual_lifecycle_stage"] = "execution_result"
            annotated["manual_lifecycle_label"] = "Broker result"
            annotated["manual_lifecycle_tone"] = lifecycle_tone
        elif source == "unmatched_closed_deal" or annotated.get("manual_bucket"):
            annotated["manual_lifecycle_stage"] = "reconciliation_gap"
            annotated["manual_lifecycle_label"] = "Reconciliation gap"
            annotated["manual_lifecycle_tone"] = "critical"
        elif source == "trades_log":
            annotated["manual_lifecycle_stage"] = "trade_log_activity"
            annotated["manual_lifecycle_label"] = "Trade log activity"
            annotated["manual_lifecycle_tone"] = "info"
        else:
            annotated["manual_lifecycle_stage"] = "manual_activity"
            annotated["manual_lifecycle_label"] = "Manual activity"
            annotated["manual_lifecycle_tone"] = "warning"
    return annotated


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
            events.append(_annotate_audit_event_origin({"source": "pool_audit", **row}))
    for row in unmatched_rows[-limit:]:
        if isinstance(row, dict):
            events.append(_annotate_audit_event_origin({"source": "unmatched_closed_deal", **row}))
    for row in load_recent_trade_log(limit=limit):
        events.append(_annotate_audit_event_origin({"source": "trades_log", **row}))

    events.sort(key=lambda row: str(row.get("recorded_at") or row.get("last_update") or row.get("raw") or ""), reverse=True)
    return {
        "generated_at": utc_now_iso(),
        "events": events[:limit],
    }
