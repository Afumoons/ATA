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

        # Simple text summary for now; can be expanded later
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

        # Store a small set of key stats in metadata for quick filtering/analysis.
        # This keeps Phase 4 logic simple and avoids having to re-parse documents
        # in downstream candidate filtering.
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

        This uses Chroma's built-in embedding if configured; for more control,
        a custom embedding function could be wired in the future.
        """
        res = self.collection.query(
            query_texts=[text],
            n_results=n_results,
            where=where or {},
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
        text: Optional[str] = None,
        n_results: int = 10,
    ) -> List[Dict[str, Any]]:
        """Convenience helper for Phase 4 candidate filtering.

        Returns a list of neighbor dicts with basic fields extracted, filtered
        by symbol/timeframe metadata. Callers can use the returned
        ``stat_*`` keys to reason about clusters of good/bad strategies
        without re-parsing documents.
        """
        query_text = text or f"symbol={symbol}\ntimeframe={timeframe}"

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
            # Attach any stat_* fields so callers can aggregate/threshold.
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
