from __future__ import annotations

import json
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Dict, List, Optional, Any
from collections import Counter, defaultdict
from tempfile import NamedTemporaryFile

from ..logging_utils import get_logger
from .base import StrategyDefinition
from ..execution.audit_utils import append_pool_audit

logger = get_logger(__name__)

POOL_DIR = Path(__file__).resolve().parent
POOL_STATE_PATH = POOL_DIR / "pool_state.json"

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


def _family_from_stats(stats: Dict[str, Any]) -> str:
    strategy = (stats or {}).get("strategy") or {}
    params = (strategy.get("params") if isinstance(strategy, dict) else None) or {}
    return str(
        (strategy.get("family") if isinstance(strategy, dict) else None)
        or (strategy.get("playbook_type") if isinstance(strategy, dict) else None)
        or params.get("family")
        or params.get("playbook_type")
        or params.get("long_family")
        or params.get("short_family")
        or (stats or {}).get("family")
        or (stats or {}).get("playbook_type")
        or "unknown"
    )


def _family_from_strategy_payload(strategy_payload: Dict[str, Any]) -> str:
    strategy_payload = strategy_payload or {}
    params = strategy_payload.get("params") or {}
    return str(
        strategy_payload.get("family")
        or strategy_payload.get("playbook_type")
        or params.get("family")
        or params.get("playbook_type")
        or params.get("long_family")
        or params.get("short_family")
        or "unknown"
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
    ])


@dataclass
class StrategyRecord:
    name: str
    symbol: str
    timeframe: str
    status: str  # "candidate", "active", "exploratory", "disabled", "retired"
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
            status=data.get("status", "candidate"),
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
        """Rebuild fingerprint map from stored strategy stats."""
        self._fp_map = {}
        for name, rec in self.strategies.items():
            strat_dict = (rec.stats or {}).get("strategy") or {}
            if strat_dict:
                fp = "|".join([
                    _family_from_strategy_payload(strat_dict),
                    str(strat_dict.get("long_entry_rule", "") or ""),
                    str(strat_dict.get("short_entry_rule", "") or ""),
                    str(strat_dict.get("exit_rule", "") or ""),
                    str(strat_dict.get("sl_atr_mult", "") or ""),
                    str(strat_dict.get("tp_atr_mult", "") or ""),
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

    def upsert_strategy(
        self,
        strategy: StrategyDefinition,
        stats: Dict[str, Any],
        score: float,
        status: str = "candidate",
    ) -> None:
        """Insert or update a strategy, with structural deduplication.

        Tier 2 behaviour:
        - If an existing strategy with identical rules exists in the pool,
          only replace it if the new entry has a better status rank OR a
          higher score at the same rank. Otherwise skip silently.
        - This prevents 42%+ clone rate observed in production (217 active
          → 126 unique after dedup filter in signals.py).
        """
        fp = _structural_fingerprint(strategy)
        existing_name = self._fp_map.get(fp)

        if existing_name and existing_name != strategy.name:
            existing_rec = self.strategies.get(existing_name)
            if existing_rec is not None:
                new_rank = _STATUS_RANK.get(status, 0)
                existing_rank = _STATUS_RANK.get(existing_rec.status, 0)

                if new_rank < existing_rank:
                    # Existing has better status — update score/stats if improved, else skip
                    if score > existing_rec.score:
                        existing_rec.score = score
                        existing_rec.stats = stats
                        logger.debug(
                            "Pool dedup: score update %s (clone=%s) %.3f → %.3f",
                            existing_name, strategy.name, existing_rec.score, score,
                        )
                    else:
                        logger.debug(
                            "Pool dedup: skip clone %s (rules==%s, status=%s, score=%.3f)",
                            strategy.name, existing_name, existing_rec.status, existing_rec.score,
                        )
                    return

                elif new_rank == existing_rank and score <= existing_rec.score:
                    logger.debug(
                        "Pool dedup: skip clone %s (same tier as %s, no improvement)",
                        strategy.name, existing_name,
                    )
                    return

                else:
                    # New entry is strictly better — replace
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

    def set_status(self, name: str, status: str) -> None:
        rec = self.strategies.get(name)
        if not rec:
            logger.warning("Pool set_status: strategy %s not found", name)
            return
        rec.status = status
        logger.info("Pool set_status: %s -> %s", name, status)

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
            "Pool pruned %d inactive strategies (kept %d inactive + %d live = %d total) | inactive_family_mix=%s",
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
    with NamedTemporaryFile("w", encoding="utf-8", delete=False, dir=path.parent, prefix=f".{path.stem}_", suffix=".tmp") as tmp:
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