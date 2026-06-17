from __future__ import annotations

import json
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Dict, List, Optional, Any
import re
from collections import Counter, defaultdict
from tempfile import NamedTemporaryFile

try:
    from ..logging_utils import get_logger
    from .base import StrategyDefinition
    from ..execution.audit_utils import append_pool_audit
except ImportError:
    from logging_utils import get_logger
    from strategies.base import StrategyDefinition
    from execution.audit_utils import append_pool_audit

logger = get_logger(__name__)

POOL_DIR = Path(__file__).resolve().parent
POOL_STATE_PATH = POOL_DIR / "pool_state.json"

_VALID_STATUSES = {"active", "exploratory", "candidate", "disabled", "retired"}
_LIVE_STATUSES = {"active", "exploratory"}
_MAX_INACTIVE_STRATEGIES = 200

# Status rank — higher = more protected during deduplication
_STATUS_RANK = {
    "active":      4,
    "exploratory": 3,
    "candidate":   2,
    "disabled":    1,
    "retired":     0,
}


def normalize_status(status: Any, default: str = "candidate") -> str:
    raw = str(status or "").strip().lower()
    if raw in _VALID_STATUSES:
        return raw
    return default


def summarize_status_counts(records: Dict[str, "StrategyRecord"]) -> Dict[str, int]:
    counts = {status: 0 for status in ("active", "exploratory", "candidate", "disabled", "retired")}
    counts["other"] = 0
    for rec in records.values():
        status = normalize_status(getattr(rec, "status", None), default="candidate")
        if status in counts:
            counts[status] += 1
        else:
            counts["other"] += 1
    return counts


def _normalize_family(value: Any) -> str:
    return str(value or "").strip() or "unknown"


def _family_from_params(params: Dict[str, Any]) -> str:
    params = params or {}
    family = params.get("family") or params.get("playbook_type")
    if family:
        return _normalize_family(family)

    long_family = _normalize_family(params.get("long_family"))
    short_family = _normalize_family(params.get("short_family"))
    if long_family != "unknown" and short_family != "unknown" and long_family != short_family:
        return f"mixed:{long_family}+{short_family}"
    if long_family != "unknown":
        return long_family
    if short_family != "unknown":
        return short_family
    return "unknown"


def _family_from_stats(stats: Dict[str, Any]) -> str:
    strategy = (stats or {}).get("strategy") or {}
    params = (strategy.get("params") if isinstance(strategy, dict) else None) or {}
    return _normalize_family(
        (strategy.get("family") if isinstance(strategy, dict) else None)
        or (strategy.get("playbook_type") if isinstance(strategy, dict) else None)
        or _family_from_params(params)
        or (stats or {}).get("family")
        or (stats or {}).get("playbook_type")
    )


def _family_from_strategy_payload(strategy_payload: Dict[str, Any]) -> str:
    strategy_payload = strategy_payload or {}
    params = strategy_payload.get("params") or {}
    return _normalize_family(
        strategy_payload.get("family")
        or strategy_payload.get("playbook_type")
        or _family_from_params(params)
    )


def _structural_fingerprint(strategy: StrategyDefinition) -> str:
    """Canonical fingerprint based on trading logic only (not name/UUID).

    Two strategies are structural duplicates if they share the same
    entry/exit rules and ATR multipliers — regardless of their name.
    Used to prevent pool accumulating hundreds of identically-behaving
    strategies that waste compute and create hidden concentration risk.
    """
    params = getattr(strategy, "params", {}) or {}
    family = str(params.get("family") or params.get("playbook_type") or "unknown")
    return "|".join([
        family,
        str(strategy.long_entry_rule or ""),
        str(strategy.short_entry_rule or ""),
        str(strategy.exit_rule or ""),
        str(getattr(strategy, "sl_atr_mult", "") or ""),
        str(getattr(strategy, "tp_atr_mult", "") or ""),
        str(getattr(strategy, "stop_loss_pips", "") or ""),
        str(getattr(strategy, "take_profit_pips", "") or ""),
    ])



def _rule_token_set(rule: Any) -> set[str]:
    text = str(rule or "").lower()
    normalized = re.sub(r"[^a-z0-9_><=]+", " ", text)
    return {tok for tok in normalized.split() if tok and not tok.replace('.', '', 1).isdigit()}



def _semantic_fingerprint(strategy: StrategyDefinition) -> str:
    params = getattr(strategy, "params", {}) or {}
    family = str(params.get("family") or params.get("playbook_type") or "unknown")
    long_tokens = sorted(_rule_token_set(getattr(strategy, "long_entry_rule", "")))
    short_tokens = sorted(_rule_token_set(getattr(strategy, "short_entry_rule", "")))
    exit_tokens = sorted(_rule_token_set(getattr(strategy, "exit_rule", "")))
    topology = {
        "long_has_or": " or " in str(getattr(strategy, "long_entry_rule", "") or "").lower(),
        "short_has_or": " or " in str(getattr(strategy, "short_entry_rule", "") or "").lower(),
        "exit_has_or": " or " in str(getattr(strategy, "exit_rule", "") or "").lower(),
    }
    return json.dumps({
        "family": family,
        "long": long_tokens,
        "short": short_tokens,
        "exit": exit_tokens,
        "topology": topology,
        "has_time_stop": bool(params.get("time_stop_bars")),
        "has_session_exit_guard": bool(params.get("has_session_exit_guard", False)),
    }, sort_keys=True)



def strategy_motif(strategy: StrategyDefinition) -> str:
    params = getattr(strategy, "params", {}) or {}
    family = str(params.get("family") or params.get("playbook_type") or "unknown")
    all_tokens = (
        _rule_token_set(getattr(strategy, "long_entry_rule", ""))
        | _rule_token_set(getattr(strategy, "short_entry_rule", ""))
        | _rule_token_set(getattr(strategy, "exit_rule", ""))
    )

    if family in {"rsi_range"}:
        return "range_fade"
    if family in {"session_breakout"}:
        return "session_breakout"
    if family in {"compression_breakout"}:
        return "compression_expansion"
    if family in {"vol_breakout"}:
        return "volatility_breakout"
    if family in {"pullback_trend", "xau_impulse_pullback"}:
        return "trend_pullback"
    if family in {"ma_trend", "xau_session_continuation"}:
        return "trend_continuation"
    if family in {"vwap_profile"}:
        return "vwap_volume_profile"
    if "fib_zone" in all_tokens or "tenkan_sen" in all_tokens or "kijun_sen" in all_tokens:
        return "structure_confluence"
    if "rsi" in all_tokens and "trend_strength" in all_tokens:
        return "hybrid_regime"
    return family



def semantic_similarity(a: StrategyDefinition, b: StrategyDefinition) -> float:
    a_params = getattr(a, "params", {}) or {}
    b_params = getattr(b, "params", {}) or {}
    a_family = str(a_params.get("family") or a_params.get("playbook_type") or "unknown")
    b_family = str(b_params.get("family") or b_params.get("playbook_type") or "unknown")

    a_long = _rule_token_set(getattr(a, "long_entry_rule", ""))
    a_short = _rule_token_set(getattr(a, "short_entry_rule", ""))
    a_exit = _rule_token_set(getattr(a, "exit_rule", ""))
    b_long = _rule_token_set(getattr(b, "long_entry_rule", ""))
    b_short = _rule_token_set(getattr(b, "short_entry_rule", ""))
    b_exit = _rule_token_set(getattr(b, "exit_rule", ""))

    def _jaccard(x: set[str], y: set[str]) -> float:
        union = x | y
        return (len(x & y) / len(union)) if union else 1.0

    long_jaccard = _jaccard(a_long, b_long)
    short_jaccard = _jaccard(a_short, b_short)
    exit_jaccard = _jaccard(a_exit, b_exit)
    token_jaccard = 0.4 * long_jaccard + 0.4 * short_jaccard + 0.2 * exit_jaccard

    numeric_keys = [
        "trend_min", "trend_exit", "rsi_exit", "vol_min", "vol_max",
        "time_stop_bars", "stop_loss_pips", "take_profit_pips",
        "sl_atr_mult", "tp_atr_mult",
    ]
    compared = 0
    close = 0
    for key in numeric_keys:
        av = a_params.get(key)
        bv = b_params.get(key)
        if av is None or bv is None:
            continue
        compared += 1
        try:
            tolerance = 0.1
            if key == "time_stop_bars":
                tolerance = 1.0
            elif key in {"stop_loss_pips", "take_profit_pips"}:
                tolerance = 10.0
            elif key in {"sl_atr_mult", "tp_atr_mult"}:
                tolerance = 0.2
            if abs(float(av) - float(bv)) <= tolerance:
                close += 1
        except Exception:
            pass

    family_bonus = 1.0 if a_family == b_family else 0.0
    motif_bonus = 1.0 if strategy_motif(a) == strategy_motif(b) else 0.0
    session_guard_bonus = 1.0 if (
        bool(a_params.get("has_session_exit_guard", False))
        == bool(b_params.get("has_session_exit_guard", False))
    ) else 0.0
    exit_archetype_bonus = 1.0 if (
        str(a_params.get("exit_archetype", "")) == str(b_params.get("exit_archetype", ""))
    ) else 0.0

    numeric_similarity = (close / compared) if compared else 0.0
    score = (
        0.35 * token_jaccard
        + 0.20 * numeric_similarity
        + 0.15 * family_bonus
        + 0.10 * motif_bonus
        + 0.10 * session_guard_bonus
        + 0.10 * exit_archetype_bonus
    )

    if a_family == b_family and token_jaccard <= 0.85:
        score = min(score, 0.84)
    return score


@dataclass
class StrategyRecord:
    name: str
    symbol: str
    timeframe: str
    status: str
    score: float
    stats: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "StrategyRecord":
        return cls(
            name=data["name"],
            symbol=data["symbol"],
            timeframe=data["timeframe"],
            status=normalize_status(data.get("status", "candidate"), default="candidate"),
            score=float(data.get("score", 0.0)),
            stats=data.get("stats", {}),
        )


@dataclass
class StrategyPool:
    strategies: Dict[str, StrategyRecord] = field(default_factory=dict)

    # fingerprint → strategy_name for O(1) duplicate detection
    # Not persisted — rebuilt on load and maintained on upsert/prune.
    _fp_map: Dict[str, str] = field(default_factory=dict, repr=False, compare=False)

    def _rebuild_fp_map(self) -> None:
        self._fp_map = {}
        for name, rec in self.strategies.items():
            strat_dict = (rec.stats or {}).get("strategy") or {}
            if not strat_dict:
                continue
            # Gunakan logic yang sama dengan _structural_fingerprint
            params = strat_dict.get("params") or {}
            family = str(
                params.get("family")
                or params.get("playbook_type")
                or strat_dict.get("family")
                or strat_dict.get("playbook_type")
                or "unknown"
            )
            fp = "|".join([
                family,
                str(strat_dict.get("long_entry_rule", "") or ""),
                str(strat_dict.get("short_entry_rule", "") or ""),
                str(strat_dict.get("exit_rule", "") or ""),
                str(strat_dict.get("sl_atr_mult", "") or ""),
                str(strat_dict.get("tp_atr_mult", "") or ""),
                str(strat_dict.get("stop_loss_pips", "") or ""),
                str(strat_dict.get("take_profit_pips", "") or ""),
            ])
            self._fp_map[fp] = name

    def to_dict(self) -> Dict[str, Dict[str, Any]]:
        return {name: rec.to_dict() for name, rec in self.strategies.items()}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "StrategyPool":
        strategies: Dict[str, StrategyRecord] = {}
        for name, rec in data.items():
            try:
                strategies[name] = StrategyRecord.from_dict(rec)
            except Exception as e:
                logger.warning("Pool: skipping corrupt record '%s': %s", name, e)
        pool = cls(strategies=strategies)
        pool._rebuild_fp_map()
        return pool

    # -------------------------------------------------------------------------
    # P0 FIX #4: upsert_strategy() sekarang return bool
    #
    # BEFORE (bug):
    #   def upsert_strategy(...) -> None:   ← always None, caller tidak tahu
    #                                          apakah pool benar-benar berubah
    #
    # AFTER (fixed):
    #   def upsert_strategy(...) -> bool:  ← True = pool berubah
    #                                         False = skip (duplicate/no improvement)
    #
    # Ini memungkinkan scheduler/main.py melacak pool_modified secara akurat:
    #   pool_modified |= pool.upsert_strategy(...)
    # -------------------------------------------------------------------------
    def upsert_strategy(
        self,
        strategy: StrategyDefinition,
        stats: Dict[str, Any],
        score: float,
        status: str = "candidate",
    ) -> bool:
        """Insert atau update strategy dengan structural deduplication.

        Returns:
            True  → pool benar-benar berubah (insert baru atau replace)
            False → skip karena duplicate tanpa improvement (pool tidak berubah)
        """
        fp = _structural_fingerprint(strategy)
        existing_name = self._fp_map.get(fp)

        if existing_name and existing_name != strategy.name:
            existing_rec = self.strategies.get(existing_name)
            if existing_rec is not None:
                new_rank = _STATUS_RANK.get(status, 0)
                existing_rank = _STATUS_RANK.get(existing_rec.status, 0)

                if new_rank < existing_rank:
                    # Existing punya status lebih baik
                    if score > existing_rec.score:
                        # Update score/stats saja — ini perubahan kecil, catat sebagai modified
                        existing_rec.score = score
                        existing_rec.stats = stats
                        logger.debug(
                            "Pool dedup: score update %s (clone=%s) → %.3f",
                            existing_name, strategy.name, score,
                        )
                        return True  # score berubah = pool modified
                    else:
                        logger.debug(
                            "Pool dedup: skip clone %s (rules==%s, no improvement)",
                            strategy.name, existing_name,
                        )
                        return False  # tidak ada perubahan

                elif new_rank == existing_rank and score <= existing_rec.score:
                    logger.debug(
                        "Pool dedup: skip clone %s (same tier as %s, no improvement)",
                        strategy.name, existing_name,
                    )
                    return False  # tidak ada perubahan

                else:
                    # New entry strictly better — replace
                    logger.info(
                        "Pool dedup: replacing %s with %s (status %s→%s, score %.3f→%.3f)",
                        existing_name, strategy.name,
                        existing_rec.status, status,
                        existing_rec.score, score,
                    )
                    append_pool_audit({
                        "event": "dedup_replace",
                        "old_name": existing_name,
                        "new_name": strategy.name,
                        "old_status": existing_rec.status,
                        "new_status": status,
                        "old_score": existing_rec.score,
                        "new_score": score,
                    })
                    del self.strategies[existing_name]
                    del self._fp_map[fp]
                    # Fall through ke insert bawah

        rec = StrategyRecord(
            name=strategy.name,
            symbol=strategy.symbol,
            timeframe=strategy.timeframe,
            status=status,
            score=score,
            stats=stats,
        )
        self.strategies[strategy.name] = rec
        self._fp_map[fp] = strategy.name
        logger.info("Pool upsert: %s status=%s score=%.3f", strategy.name, status, score)
        return True  # insert/replace = pool modified

    def set_status(self, name: str, status: str) -> bool:
        """Set status strategy.

        Returns:
            True  → status berubah (pool modified)
            False → strategy tidak ditemukan atau status sama
        """
        rec = self.strategies.get(name)
        if not rec:
            logger.warning("Pool set_status: strategy %s not found", name)
            return False
        new_status = normalize_status(status, default=rec.status or "candidate")
        if rec.status == new_status:
            return False  # tidak ada perubahan
        rec.status = new_status
        logger.info("Pool set_status: %s -> %s", name, rec.status)
        return True  # status berubah = pool modified

    def top_strategies(
        self,
        status_filter: Optional[str] = "candidate",
        limit: int = 10,
    ) -> List[StrategyRecord]:
        recs = list(self.strategies.values())
        if status_filter:
            recs = [r for r in recs if r.status == status_filter]
        recs.sort(key=lambda r: r.score, reverse=True)
        return recs[:limit]

    def prune(self, max_inactive: int = _MAX_INACTIVE_STRATEGIES, min_family_keep: int = 8) -> int:
        """Remove lowest-scoring inactive strategies beyond the size cap.

        Active and exploratory strategies are never pruned.
        Inactive pruning is family-aware so the pool does not collapse into a
        narrow subset of playbooks after repeated research cycles.
        Returns the number of records removed.
        """
        live = {n: r for n, r in self.strategies.items() if r.status in _LIVE_STATUSES}
        inactive = {n: r for n, r in self.strategies.items() if r.status not in _LIVE_STATUSES}

        if len(inactive) <= max_inactive:
            return 0

        family_buckets: Dict[str, List[tuple[str, StrategyRecord]]] = defaultdict(list)
        for name, rec in inactive.items():
            family_buckets[_family_from_stats(rec.stats)].append((name, rec))

        keep: Dict[str, StrategyRecord] = {}
        for family, items in family_buckets.items():
            ranked = sorted(items, key=lambda kv: kv[1].score, reverse=True)
            for name, rec in ranked[:min(min_family_keep, len(ranked))]:
                keep[name] = rec

        remaining_slots = max(0, max_inactive - len(keep))
        if remaining_slots > 0:
            leftovers: List[tuple[str, StrategyRecord]] = []
            for family, items in family_buckets.items():
                ranked = sorted(items, key=lambda kv: kv[1].score, reverse=True)
                leftovers.extend(ranked[min(min_family_keep, len(ranked)):])
            leftovers.sort(key=lambda kv: kv[1].score, reverse=True)
            for name, rec in leftovers[:remaining_slots]:
                keep[name] = rec

        if len(keep) > max_inactive:
            ranked_keep = sorted(keep.items(), key=lambda kv: kv[1].score, reverse=True)[:max_inactive]
            keep = dict(ranked_keep)

        pruned_names = set(inactive.keys()) - set(keep.keys())
        self.strategies = {**live, **keep}
        self._rebuild_fp_map()

        kept_family_mix = dict(Counter(_family_from_stats(rec.stats) for rec in keep.values()))
        if pruned_names:
            append_pool_audit({
                "event": "prune_inactive",
                "count": len(pruned_names),
                "sample": sorted(pruned_names)[:20],
                "kept_inactive": len(keep),
                "live_count": len(live),
                "inactive_family_mix": kept_family_mix,
            })
        logger.info(
            "Pool pruned %d inactive strategies (kept %d inactive + %d live = %d total) "
            "| inactive_family_mix=%s",
            len(pruned_names), len(keep), len(live), len(self.strategies), kept_family_mix,
        )
        return len(pruned_names)


def load_pool() -> StrategyPool:
    if not POOL_STATE_PATH.exists():
        logger.info("Pool: starting new empty pool")
        return StrategyPool(strategies={})
    try:
        with POOL_STATE_PATH.open("r", encoding="utf-8") as f:
            data = json.load(f)
        pool = StrategyPool.from_dict(data)
        logger.info("Pool loaded: %d strategies", len(pool.strategies))
        return pool
    except json.JSONDecodeError as e:
        logger.error("Pool: pool_state.json corrupt (%s) — starting fresh", e)
        return StrategyPool(strategies={})
    except Exception as e:
        logger.exception("Pool: unexpected error loading pool — starting fresh: %s", e)
        return StrategyPool(strategies={})


def _safe_write_pool_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(payload, indent=2, ensure_ascii=False)
    with NamedTemporaryFile(
        "w", encoding="utf-8", delete=False,
        dir=path.parent, prefix=f".{path.stem}_", suffix=".tmp"
    ) as tmp:
        tmp.write(data)
        tmp_path = Path(tmp.name)
    tmp_path.replace(path)


def save_pool(pool: StrategyPool) -> None:
    _safe_write_pool_json(POOL_STATE_PATH, pool.to_dict())
    logger.info("Pool saved atomically: %d strategies", len(pool.strategies))

    try:
        from .live_manifest import rebuild_runtime_artifacts

        artifacts = rebuild_runtime_artifacts(pool)
        logger.info(
            "Runtime artifacts rebuilt after pool save: manifest=%d index=%d",
            int((artifacts.get("manifest") or {}).get("entry_count", 0) or 0),
            int((artifacts.get("index") or {}).get("entry_count", 0) or 0),
        )
    except Exception as e:
        logger.exception("Failed to rebuild runtime artifacts after pool save: %s", e)