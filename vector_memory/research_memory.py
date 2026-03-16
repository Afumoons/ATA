from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Any, Optional

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

        metadata = {
            "strategy_name": strategy_name,
            "symbol": symbol,
            "timeframe": timeframe,
        }
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
