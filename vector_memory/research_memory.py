from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional
from collections import OrderedDict

from chromadb import PersistentClient

from ..logging_utils import get_logger

logger = get_logger(__name__)

# Base directory for this project (autonomous_trading_ai), so Chroma data
# lives alongside the code regardless of current working directory.
BASE_DIR = Path(__file__).resolve().parents[1]


@dataclass
class ResearchMemoryConfig:
    chroma_path: str = str(BASE_DIR / "chroma_data")
    collection_name: str = "strategy_research"


DEFAULT_CONFIG = ResearchMemoryConfig()

# Stats stored in metadata for fast filtering/aggregation.
# Must all be scalar (str/int/float/bool) — ChromaDB rejects nested types.
_KEY_STATS = [
    "return_pct",
    "sharpe_ratio",
    "profit_factor",
    "max_drawdown_pct",
    "num_trades",
    "score",
    "wf_overall_sharpe",
]

# Keys excluded from document text — large nested dicts that pollute embeddings.
_SKIP_IN_DOCUMENT = {
    "strategy_explain",
    "mc_final_pnl_mean", "mc_final_pnl_p5", "mc_final_pnl_p95",
    "mc_max_dd_mean", "mc_max_dd_p5", "mc_max_dd_p95",
    # Legacy key names before rename
    "mc_final_equity_mean", "mc_final_equity_p5", "mc_final_equity_p95",
}

POSITION_MODE_SINGLE = "single_position"
POSITION_MODE_MULTI = "multi_position"
POSITION_MODE_LEGACY = "legacy_multi_position"


def _safe_scalar(v: Any) -> Optional[Any]:
    """Return v if ChromaDB-compatible scalar, else None."""
    if isinstance(v, (str, int, float, bool)):
        return v
    return None


def _normalise_position_mode(value: Optional[Any]) -> str:
    text = str(value or "").strip().lower()
    if text in {
        POSITION_MODE_SINGLE,
        "single",
        "single_open_position",
        "one_position",
        "one_strategy_one_open_position",
    }:
        return POSITION_MODE_SINGLE
    if text in {POSITION_MODE_MULTI, "multi", "multi_position_legacy"}:
        return POSITION_MODE_MULTI
    if text in {POSITION_MODE_LEGACY, "legacy", "unknown", ""}:
        return POSITION_MODE_LEGACY
    return POSITION_MODE_SINGLE if "single" in text else POSITION_MODE_MULTI


class ResearchMemory:
    def __init__(self, cfg: ResearchMemoryConfig = DEFAULT_CONFIG):
        self.cfg = cfg
        self.client = PersistentClient(path=cfg.chroma_path)
        self.collection = self.client.get_or_create_collection(name=cfg.collection_name)
        self._query_cache: "OrderedDict[str, List[Dict[str, Any]]]" = OrderedDict()
        self._query_cache_max = 256
        logger.info(
            "ResearchMemory initialized: path=%s collection=%s",
            cfg.chroma_path,
            cfg.collection_name,
        )

    def store_strategy_result(
        self,
        strategy_name: str,
        symbol: str,
        timeframe: str,
        stats: Dict[str, Any],
        extra: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Store or update a strategy evaluation result in Chroma.

        Bug fixes:
        - Uses upsert() instead of add() — add() raises DuplicateIDError when
          the same strategy is re-evaluated in subsequent research cycles.
        - strategy_explain and MC stats (nested dicts) are excluded from
          document text. Including them produced Python repr strings of
          thousands of characters that dominated embeddings and broke
          similarity search quality.
        - Metadata values filtered to scalars — ChromaDB rejects nested
          dicts/lists in metadata fields.

        Position-mode note:
        - New research runs default to `single_position` mode.
        - Legacy records can still be tagged explicitly as `multi_position`
          or `legacy_multi_position` for backward compatibility.
        """
        doc_id = f"{strategy_name}:{symbol}:{timeframe}"
        position_mode = _normalise_position_mode(
            (extra or {}).get("position_mode")
            or stats.get("position_mode")
            or POSITION_MODE_SINGLE
        )

        # Document text — scalar stats only, no nested dicts
        text_lines = [
            f"strategy={strategy_name}",
            f"symbol={symbol}",
            f"timeframe={timeframe}",
            f"position_mode={position_mode}",
        ]
        for k, v in stats.items():
            if k in _SKIP_IN_DOCUMENT:
                continue
            scalar = _safe_scalar(v)
            if scalar is not None:
                text_lines.append(f"{k}={scalar}")

        if extra:
            for k, v in extra.items():
                scalar = _safe_scalar(v)
                if scalar is not None:
                    text_lines.append(f"extra_{k}={scalar}")

        document = "\n".join(text_lines)

        # Metadata — key stats as scalars
        metadata: Dict[str, Any] = {
            "strategy_name": strategy_name,
            "symbol": symbol,
            "timeframe": timeframe,
            "position_mode": position_mode,
            "position_mode_rank": 0 if position_mode == POSITION_MODE_SINGLE else 1,
        }
        for k in _KEY_STATS:
            if k in stats:
                scalar = _safe_scalar(stats[k])
                if scalar is not None:
                    metadata[f"stat_{k}"] = scalar

        if extra:
            for k, v in extra.items():
                scalar = _safe_scalar(v)
                if scalar is not None:
                    metadata[f"extra_{k}"] = scalar

        # upsert — idempotent, safe for repeated research cycles
        self.collection.upsert(ids=[doc_id], documents=[document], metadatas=[metadata])
        self._query_cache.clear()
        logger.info(
            "ResearchMemory: upserted result for %s (position_mode=%s, cache_cleared=%s)",
            doc_id,
            position_mode,
            True,
        )

    def query_similar(
        self,
        text: str,
        n_results: int = 5,
        where: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Query for similar strategy research documents by text.

        Handles ChromaDB where-filter syntax:
        - Single key  : {key: {"$eq": value}}
        - Multi key   : {"$and": [{key: {"$eq": value}}, ...]}
        - Pre-built   : pass through as-is if already contains "$and"/"$or"

        Clamps n_results to collection size — ChromaDB throws if n_results
        exceeds the number of documents in the collection.
        """
        chroma_where: Optional[Dict[str, Any]] = None

        if where:
            if "$and" in where or "$or" in where:
                chroma_where = where
            elif len(where) > 1:
                chroma_where = {
                    "$and": [{k: {"$eq": v}} for k, v in where.items()]
                }
            else:
                k, v = next(iter(where.items()))
                chroma_where = {k: {"$eq": v}}

        # Guard: empty collection — return empty result immediately
        count = self.collection.count()
        if count == 0:
            return {"ids": [[]], "documents": [[]], "metadatas": [[]], "distances": [[]]}

        safe_n = max(1, min(n_results, count))

        res = self.collection.query(
            query_texts=[text],
            n_results=safe_n,
            **({"where": chroma_where} if chroma_where else {}),
        )
        logger.info(
            "ResearchMemory: query '%s' -> %d results (collection=%d)",
            text[:60],
            len(res.get("ids", [[]])[0]),
            count,
        )
        return res

    def _cache_get(self, key: str) -> Optional[List[Dict[str, Any]]]:
        val = self._query_cache.get(key)
        if val is None:
            return None
        self._query_cache.move_to_end(key)
        return list(val)

    def _cache_put(self, key: str, value: List[Dict[str, Any]]) -> None:
        self._query_cache[key] = list(value)
        self._query_cache.move_to_end(key)
        while len(self._query_cache) > self._query_cache_max:
            self._query_cache.popitem(last=False)

    def query_similar_strategies(
        self,
        symbol: str,
        timeframe: str,
        strategy: Optional[Dict[str, Any]] = None,
        text: Optional[str] = None,
        n_results: int = 10,
        preferred_position_mode: str = POSITION_MODE_SINGLE,
    ) -> List[Dict[str, Any]]:
        """Convenience helper for candidate filtering and parent scoring.

        Query text priority:
        1. Explicit `text` argument
        2. `strategy` dict — builds rich query from entry/exit rules
        3. Fallback: minimal symbol/timeframe string

        New runs default to preferring `single_position` neighbors. Legacy
        neighbors are still returned, but sorted after preferred-mode results.
        """
        if text:
            query_text = text
        elif strategy:
            query_text = "\n".join([
                f"symbol={symbol}",
                f"timeframe={timeframe}",
                f"long_entry={strategy.get('long_entry_rule', '')}",
                f"short_entry={strategy.get('short_entry_rule', '')}",
                f"exit={strategy.get('exit_rule', '')}",
                f"sl_atr={strategy.get('sl_atr_mult', '')}",
                f"tp_atr={strategy.get('tp_atr_mult', '')}",
                f"regime={strategy.get('params', {}).get('regime_type', '')}",
            ])
        else:
            query_text = f"symbol={symbol}\ntimeframe={timeframe}"

        preferred_mode = _normalise_position_mode(preferred_position_mode)
        cache_key = f"{symbol}|{timeframe}|{preferred_mode}|{n_results}|{query_text}"
        cached = self._cache_get(cache_key)
        if cached is not None:
            logger.info(
                "ResearchMemory: cache hit for %s/%s (preferred_mode=%s, n=%d)",
                symbol,
                timeframe,
                preferred_mode,
                n_results,
            )
            return cached

        res = self.query_similar(
            text=query_text,
            n_results=n_results,
            where={"symbol": symbol, "timeframe": timeframe},
        )

        ids = res.get("ids", [[]])[0] or []
        metadatas = res.get("metadatas", [[]])[0] or []
        distances = res.get("distances", [[]])[0] or []

        neighbors: List[Dict[str, Any]] = []
        for i, meta in enumerate(metadatas):
            raw_mode = meta.get("position_mode")
            position_mode = _normalise_position_mode(raw_mode)
            if raw_mode is None:
                position_mode = POSITION_MODE_LEGACY

            neighbor: Dict[str, Any] = {
                "id": ids[i] if i < len(ids) else None,
                "distance": distances[i] if i < len(distances) else None,
                "strategy_name": meta.get("strategy_name"),
                "symbol": meta.get("symbol"),
                "timeframe": meta.get("timeframe"),
                "position_mode": position_mode,
                "position_mode_preferred": position_mode == preferred_mode,
            }
            for k, v in meta.items():
                if k.startswith("stat_"):
                    neighbor[k] = v
            neighbors.append(neighbor)

        def _neighbor_sort_key(item: Dict[str, Any]) -> tuple[int, float]:
            mode_rank = 0 if item.get("position_mode") == preferred_mode else 1
            distance = item.get("distance")
            try:
                distance_value = float(distance)
            except (TypeError, ValueError):
                distance_value = float("inf")
            return (mode_rank, distance_value)

        neighbors.sort(key=_neighbor_sort_key)

        logger.info(
            "ResearchMemory: query_similar_strategies %s/%s -> %d neighbors (preferred_mode=%s)",
            symbol,
            timeframe,
            len(neighbors),
            preferred_mode,
        )
        self._cache_put(cache_key, neighbors)
        return neighbors
