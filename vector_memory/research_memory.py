from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Any, Optional, List

from chromadb import PersistentClient

from ..logging_utils import get_logger

logger = get_logger(__name__)


@dataclass
class ResearchMemoryConfig:
    chroma_path: str = "./chroma_data"
    collection_name: str = "strategy_research"


DEFAULT_CONFIG = ResearchMemoryConfig()


class ResearchMemory:
    def __init__(self, cfg: ResearchMemoryConfig = DEFAULT_CONFIG):
        self.cfg = cfg
        self.client = PersistentClient(path=cfg.chroma_path)
        self.collection = self.client.get_or_create_collection(name=cfg.collection_name)
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
        """Store a strategy result as a Chroma document.

        - stats: dict containing backtest/eval/WF/MC metrics
        - extra: optional additional context (e.g. regime breakdowns)
        """
        doc_id = f"{strategy_name}:{symbol}:{timeframe}"

        text_lines = [
            f"strategy={strategy_name}",
            f"symbol={symbol}",
            f"timeframe={timeframe}",
        ]
        for k, v in stats.items():
            text_lines.append(f"{k}={v}")
        if extra:
            for k, v in extra.items():
                text_lines.append(f"extra_{k}={v}")
        document = "\n".join(text_lines)

        metadata: Dict[str, Any] = {
            "strategy_name": strategy_name,
            "symbol": symbol,
            "timeframe": timeframe,
        }

        key_stats = [
            "return_pct",
            "sharpe_ratio",
            "profit_factor",
            "max_drawdown_pct",
            "num_trades",
            "score",
        ]
        for k in key_stats:
            if k in stats:
                metadata[f"stat_{k}"] = stats[k]

        if extra:
            metadata.update({f"extra_{k}": v for k, v in extra.items()})

        self.collection.add(ids=[doc_id], documents=[document], metadatas=[metadata])
        logger.info("ResearchMemory: stored result for %s", doc_id)

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
        """
        chroma_where: Optional[Dict[str, Any]] = None

        if where:
            # Already a pre-built ChromaDB operator expression — pass through
            if "$and" in where or "$or" in where:
                chroma_where = where
            elif len(where) > 1:
                # Multiple plain key-value pairs — wrap with $and + $eq
                chroma_where = {
                    "$and": [{k: {"$eq": v}} for k, v in where.items()]
                }
            else:
                # Single key-value pair — wrap with $eq
                k, v = next(iter(where.items()))
                chroma_where = {k: {"$eq": v}}

        res = self.collection.query(
            query_texts=[text],
            n_results=n_results,
            **({"where": chroma_where} if chroma_where else {}),
        )
        logger.info(
            "ResearchMemory: query text='%s' -> %d results",
            text,
            len(res.get("ids", [[]])[0]),
        )
        return res

    def query_similar_strategies(
        self,
        symbol: str,
        timeframe: str,
        strategy: Optional[Dict[str, Any]] = None,
        text: Optional[str] = None,
        n_results: int = 10,
    ) -> List[Dict[str, Any]]:
        """Convenience helper for Phase 4 candidate filtering.

        Returns a list of neighbor dicts with basic fields extracted, filtered
        by symbol/timeframe metadata.

        Query text priority:
        1. Explicit ``text`` argument (caller provides full query string)
        2. ``strategy`` dict — builds a rich query from entry/exit rules
        3. Fallback: minimal symbol/timeframe string

        The richer the query text, the more meaningful the similarity search.
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
            # Minimal fallback — less meaningful but avoids errors
            query_text = f"symbol={symbol}\ntimeframe={timeframe}"

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
            neighbor: Dict[str, Any] = {
                "id": ids[i] if i < len(ids) else None,
                "distance": distances[i] if i < len(distances) else None,
                "strategy_name": meta.get("strategy_name"),
                "symbol": meta.get("symbol"),
                "timeframe": meta.get("timeframe"),
            }
            for k, v in meta.items():
                if k.startswith("stat_"):
                    neighbor[k] = v
            neighbors.append(neighbor)

        logger.info(
            "ResearchMemory: query_similar_strategies symbol=%s timeframe=%s -> %d neighbors",
            symbol,
            timeframe,
            len(neighbors),
        )
        return neighbors