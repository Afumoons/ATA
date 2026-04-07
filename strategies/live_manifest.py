from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any, Dict, Iterable, List, Optional

from ..logging_utils import get_logger
from .base import StrategyDefinition
from .generator import _classify_template
from .pool import StrategyPool, StrategyRecord, strategy_motif

logger = get_logger(__name__)

BASE_DIR = Path(__file__).resolve().parent
LIVE_MANIFEST_PATH = BASE_DIR / "live_manifest.json"
STRATEGY_INDEX_PATH = BASE_DIR / "strategy_index.json"

LIVE_STATUSES = {"active", "exploratory"}
ARCHIVE_STATUSES = {"disabled", "retired", "archived"}
DEFAULT_MAX_LIVE_PER_SLOT = 16
DEFAULT_MAX_ARCHIVE_PER_SLOT = 120
DEFAULT_MAX_PER_BEST_REGIME = 8
DEFAULT_MAX_PER_FAMILY = 6


@dataclass
class LiveManifestEntry:
    name: str
    symbol: str
    timeframe: str
    status: str
    score: float
    family: str
    motif: str
    long_entry_rule: Optional[str]
    short_entry_rule: Optional[str]
    exit_rule: str
    stop_loss_pips: float
    take_profit_pips: float
    sl_atr_mult: Optional[float]
    tp_atr_mult: Optional[float]
    params: Dict[str, Any]
    stats: Dict[str, Any]
    manifest_rank: int
    origin: str = "pool"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class StrategyIndexEntry:
    name: str
    symbol: str
    timeframe: str
    status: str
    tier: str
    score: float
    family: str
    motif: str
    archived: bool
    has_strategy_payload: bool
    last_manifest_rank: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)



def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()



def _safe_write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(payload, indent=2, ensure_ascii=False)
    with NamedTemporaryFile("w", encoding="utf-8", delete=False, dir=path.parent, prefix=f".{path.stem}_", suffix=".tmp") as tmp:
        tmp.write(data)
        tmp_path = Path(tmp.name)
    tmp_path.replace(path)



def _infer_family_from_rules(strategy: Dict[str, Any]) -> str:
    long_rule = str(strategy.get("long_entry_rule") or "")
    short_rule = str(strategy.get("short_entry_rule") or "")
    families = []
    for rule in (long_rule, short_rule):
        if not rule:
            continue
        family, _ = _classify_template(rule)
        family = str(family or "unknown").strip() or "unknown"
        if family != "unknown":
            families.append(family)
    if not families:
        return "unknown"
    uniq = []
    for family in families:
        if family not in uniq:
            uniq.append(family)
    if len(uniq) == 1:
        return uniq[0]
    return f"mixed:{uniq[0]}+{uniq[1]}"



def _strategy_block(rec: StrategyRecord) -> Dict[str, Any]:
    strategy = ((rec.stats or {}).get("strategy") or {}).copy()
    params = dict(strategy.get("params") or {})
    family = str(
        strategy.get("family")
        or strategy.get("playbook_type")
        or params.get("family")
        or params.get("playbook_type")
        or params.get("long_family")
        or params.get("short_family")
        or (rec.stats or {}).get("family")
        or (rec.stats or {}).get("playbook_type")
        or "unknown"
    )
    if family == "unknown":
        family = _infer_family_from_rules(strategy)
    if family != "unknown" and not params:
        params = {"family": family, "playbook_type": family}
    return {
        "family": family,
        "long_entry_rule": strategy.get("long_entry_rule"),
        "short_entry_rule": strategy.get("short_entry_rule"),
        "exit_rule": strategy.get("exit_rule") or "False",
        "stop_loss_pips": float(strategy.get("stop_loss_pips", params.get("stop_loss_pips", 0.0)) or 0.0),
        "take_profit_pips": float(strategy.get("take_profit_pips", params.get("take_profit_pips", 0.0)) or 0.0),
        "sl_atr_mult": strategy.get("sl_atr_mult", params.get("sl_atr_mult")),
        "tp_atr_mult": strategy.get("tp_atr_mult", params.get("tp_atr_mult")),
        "params": params,
    }



def _rank_key(rec: StrategyRecord) -> tuple:
    meta = (((rec.stats or {}).get("strategy_explain", {}) or {}).get("meta", {}) or {})
    specialist_score = float(meta.get("specialist_score", 0.0) or 0.0)
    wf = float((rec.stats or {}).get("wf_overall_sharpe", 0.0) or 0.0)
    novelty = float((rec.stats or {}).get("research_novelty_score", 0.0) or 0.0)
    return (
        1 if rec.status == "active" else 0,
        specialist_score,
        novelty,
        wf,
        float(rec.score or 0.0),
    )



def _best_regime(rec: StrategyRecord) -> str:
    meta = (((rec.stats or {}).get("strategy_explain", {}) or {}).get("meta", {}) or {})
    return str(meta.get("best_regime", "unknown") or "unknown")



def _select_diversified_live_records(
    records: List[StrategyRecord],
    *,
    max_live_per_slot: int,
    max_per_best_regime: int = DEFAULT_MAX_PER_BEST_REGIME,
    max_per_family: int = DEFAULT_MAX_PER_FAMILY,
) -> List[StrategyRecord]:
    ranked = sorted(records, key=_rank_key, reverse=True)
    selected: List[StrategyRecord] = []
    regime_counts: Dict[str, int] = defaultdict(int)
    family_counts: Dict[str, int] = defaultdict(int)
    motif_counts: Dict[str, int] = defaultdict(int)

    buckets = {
        'specialist': [],
        'novel': [],
        'robust': [],
    }
    for rec in ranked:
        meta = (((rec.stats or {}).get("strategy_explain", {}) or {}).get("meta", {}) or {})
        if float(meta.get("specialist_score", 0.0) or 0.0) >= 0.65:
            buckets['specialist'].append(rec)
        if float((rec.stats or {}).get("research_novelty_score", 0.0) or 0.0) >= 0.35:
            buckets['novel'].append(rec)
        if float((rec.stats or {}).get("wf_overall_sharpe", 0.0) or 0.0) >= 0.75:
            buckets['robust'].append(rec)

    ordered_candidates: List[StrategyRecord] = []
    seen = set()
    round_robin = [buckets['specialist'], buckets['novel'], buckets['robust'], ranked]
    cursor = 0
    while len(ordered_candidates) < len(ranked):
        added = False
        for bucket in round_robin:
            if cursor < len(bucket):
                rec = bucket[cursor]
                if rec.name not in seen:
                    ordered_candidates.append(rec)
                    seen.add(rec.name)
                    added = True
        if not added and cursor >= len(ranked):
            break
        cursor += 1

    remaining = list(ordered_candidates)

    def _take(allow_family_overflow: bool, allow_regime_overflow: bool, allow_motif_overflow: bool) -> None:
        nonlocal remaining
        next_remaining: List[StrategyRecord] = []
        for rec in remaining:
            if len(selected) >= max_live_per_slot:
                next_remaining.append(rec)
                continue
            block = _strategy_block(rec)
            family = block["family"]
            motif = strategy_motif(StrategyDefinition(
                name=rec.name,
                symbol=rec.symbol,
                timeframe=rec.timeframe,
                long_entry_rule=block["long_entry_rule"],
                short_entry_rule=block["short_entry_rule"],
                exit_rule=block["exit_rule"],
                stop_loss_pips=block["stop_loss_pips"],
                take_profit_pips=block["take_profit_pips"],
                sl_atr_mult=block["sl_atr_mult"],
                tp_atr_mult=block["tp_atr_mult"],
                params=block["params"],
            ))
            regime = _best_regime(rec)
            family_blocked = family_counts[family] >= max_per_family
            regime_blocked = regime_counts[regime] >= max_per_best_regime
            motif_blocked = motif_counts[motif] >= 3
            if (family_blocked and not allow_family_overflow) or (regime_blocked and not allow_regime_overflow) or (motif_blocked and not allow_motif_overflow):
                next_remaining.append(rec)
                continue
            selected.append(rec)
            regime_counts[regime] += 1
            family_counts[family] += 1
            motif_counts[motif] += 1
        remaining = next_remaining

    _take(allow_family_overflow=False, allow_regime_overflow=False, allow_motif_overflow=False)
    if len(selected) < max_live_per_slot:
        _take(allow_family_overflow=True, allow_regime_overflow=False, allow_motif_overflow=False)
    if len(selected) < max_live_per_slot:
        _take(allow_family_overflow=True, allow_regime_overflow=True, allow_motif_overflow=True)

    return selected[:max_live_per_slot]



def build_live_manifest(
    pool: StrategyPool,
    *,
    max_live_per_slot: int = DEFAULT_MAX_LIVE_PER_SLOT,
) -> Dict[str, Any]:
    grouped: Dict[tuple[str, str], List[StrategyRecord]] = defaultdict(list)
    for rec in pool.strategies.values():
        if rec.status in LIVE_STATUSES:
            grouped[(rec.symbol, rec.timeframe)].append(rec)

    entries: List[LiveManifestEntry] = []
    for (symbol, timeframe), records in sorted(grouped.items()):
        ranked = _select_diversified_live_records(records, max_live_per_slot=max_live_per_slot)
        for idx, rec in enumerate(ranked, start=1):
            block = _strategy_block(rec)
            motif = strategy_motif(StrategyDefinition(
                name=rec.name,
                symbol=rec.symbol,
                timeframe=rec.timeframe,
                long_entry_rule=block["long_entry_rule"],
                short_entry_rule=block["short_entry_rule"],
                exit_rule=block["exit_rule"],
                stop_loss_pips=block["stop_loss_pips"],
                take_profit_pips=block["take_profit_pips"],
                sl_atr_mult=block["sl_atr_mult"],
                tp_atr_mult=block["tp_atr_mult"],
                params=block["params"],
            ))
            entries.append(
                LiveManifestEntry(
                    name=rec.name,
                    symbol=rec.symbol,
                    timeframe=rec.timeframe,
                    status=rec.status,
                    score=float(rec.score or 0.0),
                    family=block["family"],
                    motif=motif,
                    long_entry_rule=block["long_entry_rule"],
                    short_entry_rule=block["short_entry_rule"],
                    exit_rule=block["exit_rule"],
                    stop_loss_pips=block["stop_loss_pips"],
                    take_profit_pips=block["take_profit_pips"],
                    sl_atr_mult=block["sl_atr_mult"],
                    tp_atr_mult=block["tp_atr_mult"],
                    params=block["params"],
                    stats=rec.stats or {},
                    manifest_rank=idx,
                )
            )

    payload = {
        "schema_version": 1,
        "generated_at": _utc_now_iso(),
        "source": "pool_state",
        "entry_count": len(entries),
        "entries": [entry.to_dict() for entry in entries],
    }
    return payload



def build_strategy_index(
    pool: StrategyPool,
    *,
    max_archive_per_slot: int = DEFAULT_MAX_ARCHIVE_PER_SLOT,
) -> Dict[str, Any]:
    live_manifest = build_live_manifest(pool)
    manifest_ranks = {entry["name"]: entry["manifest_rank"] for entry in live_manifest["entries"]}

    grouped: Dict[tuple[str, str], List[StrategyRecord]] = defaultdict(list)
    for rec in pool.strategies.values():
        grouped[(rec.symbol, rec.timeframe)].append(rec)

    entries: List[StrategyIndexEntry] = []
    for (_symbol, _timeframe), records in sorted(grouped.items()):
        live_records = [rec for rec in records if rec.status in LIVE_STATUSES]
        inactive_records = [rec for rec in records if rec.status not in LIVE_STATUSES]
        ranked_inactive = sorted(inactive_records, key=lambda rec: float(rec.score or 0.0), reverse=True)

        working_names = {rec.name for rec in live_records}
        index_names = {rec.name for rec in ranked_inactive[:max_archive_per_slot]}

        for rec in records:
            block = _strategy_block(rec)
            archived = rec.status in ARCHIVE_STATUSES or (rec.status not in LIVE_STATUSES and rec.name not in index_names)
            tier = "live" if rec.name in working_names else ("index" if rec.name in index_names and not archived else "archive")
            motif = strategy_motif(StrategyDefinition(
                name=rec.name,
                symbol=rec.symbol,
                timeframe=rec.timeframe,
                long_entry_rule=block["long_entry_rule"],
                short_entry_rule=block["short_entry_rule"],
                exit_rule=block["exit_rule"],
                stop_loss_pips=block["stop_loss_pips"],
                take_profit_pips=block["take_profit_pips"],
                sl_atr_mult=block["sl_atr_mult"],
                tp_atr_mult=block["tp_atr_mult"],
                params=block["params"],
            ))
            entries.append(
                StrategyIndexEntry(
                    name=rec.name,
                    symbol=rec.symbol,
                    timeframe=rec.timeframe,
                    status=rec.status,
                    tier=tier,
                    score=float(rec.score or 0.0),
                    family=block["family"],
                    motif=motif,
                    archived=archived,
                    has_strategy_payload=bool(block["long_entry_rule"] or block["short_entry_rule"] or block["params"]),
                    last_manifest_rank=manifest_ranks.get(rec.name),
                )
            )

    payload = {
        "schema_version": 1,
        "generated_at": _utc_now_iso(),
        "source": "pool_state",
        "entry_count": len(entries),
        "entries": [entry.to_dict() for entry in sorted(entries, key=lambda e: (e.symbol, e.timeframe, e.tier, -e.score, e.name))],
    }
    return payload



def save_live_manifest(payload: Dict[str, Any], path: Path = LIVE_MANIFEST_PATH) -> None:
    _safe_write_json(path, payload)
    logger.info("Live manifest saved: %s entries=%d", path, int(payload.get("entry_count", 0) or 0))



def save_strategy_index(payload: Dict[str, Any], path: Path = STRATEGY_INDEX_PATH) -> None:
    _safe_write_json(path, payload)
    logger.info("Strategy index saved: %s entries=%d", path, int(payload.get("entry_count", 0) or 0))



def load_live_manifest(path: Path = LIVE_MANIFEST_PATH) -> Dict[str, Any]:
    if not path.exists():
        return {"schema_version": 1, "generated_at": None, "source": "missing", "entry_count": 0, "entries": []}
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)



def load_strategy_index(path: Path = STRATEGY_INDEX_PATH) -> Dict[str, Any]:
    if not path.exists():
        return {"schema_version": 1, "generated_at": None, "source": "missing", "entry_count": 0, "entries": []}
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)



def manifest_entries_for_slot(
    manifest: Dict[str, Any],
    *,
    symbol: str,
    timeframe: str,
) -> List[Dict[str, Any]]:
    return [
        dict(entry)
        for entry in (manifest.get("entries") or [])
        if entry.get("symbol") == symbol and entry.get("timeframe") == timeframe
    ]



def strategy_definition_from_manifest_entry(entry: Dict[str, Any]) -> StrategyDefinition:
    return StrategyDefinition(
        name=str(entry.get("name") or ""),
        symbol=str(entry.get("symbol") or ""),
        timeframe=str(entry.get("timeframe") or ""),
        long_entry_rule=entry.get("long_entry_rule"),
        short_entry_rule=entry.get("short_entry_rule"),
        exit_rule=str(entry.get("exit_rule") or "False"),
        stop_loss_pips=float(entry.get("stop_loss_pips", 0.0) or 0.0),
        take_profit_pips=float(entry.get("take_profit_pips", 0.0) or 0.0),
        sl_atr_mult=entry.get("sl_atr_mult"),
        tp_atr_mult=entry.get("tp_atr_mult"),
        params=dict(entry.get("params") or {}),
    )



def strategy_record_from_manifest_entry(entry: Dict[str, Any]) -> StrategyRecord:
    return StrategyRecord(
        name=str(entry.get("name") or ""),
        symbol=str(entry.get("symbol") or ""),
        timeframe=str(entry.get("timeframe") or ""),
        status=str(entry.get("status") or "candidate"),
        score=float(entry.get("score", 0.0) or 0.0),
        stats=dict(entry.get("stats") or {}),
    )



def strategy_pool_from_manifest_entries(entries: Iterable[Dict[str, Any]]) -> StrategyPool:
    return StrategyPool(
        strategies={
            str(entry.get("name") or ""): strategy_record_from_manifest_entry(entry)
            for entry in entries
            if entry.get("name")
        }
    )



def rebuild_runtime_artifacts(
    pool: StrategyPool,
    *,
    manifest_path: Path = LIVE_MANIFEST_PATH,
    index_path: Path = STRATEGY_INDEX_PATH,
    max_live_per_slot: int = DEFAULT_MAX_LIVE_PER_SLOT,
    max_archive_per_slot: int = DEFAULT_MAX_ARCHIVE_PER_SLOT,
) -> Dict[str, Dict[str, Any]]:
    manifest = build_live_manifest(pool, max_live_per_slot=max_live_per_slot)
    index = build_strategy_index(pool, max_archive_per_slot=max_archive_per_slot)
    save_live_manifest(manifest, manifest_path)
    save_strategy_index(index, index_path)
    return {"manifest": manifest, "index": index}
