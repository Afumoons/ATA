# vector_memory/ – Research Memory (Chroma)

## Purpose

This module provides a **vector-backed memory** for strategy research results
using ChromaDB. It allows the system (and you/Clio) to:

- Persist summaries of backtests/evaluations over time.
- Query for similar strategies based on text descriptions.
- Build AI-assisted research workflows on top of stored results.

It is intentionally lightweight and used only for **research / analysis**;
live trading logic does not depend on it at runtime.

## Key Files

- `research_memory.py`
  - `ResearchMemoryConfig` dataclass:
    - `chroma_path` – filesystem path for Chroma persistent storage
      (default: `"./chroma_data"`, relative to workspace root).
    - `collection_name` – Chroma collection name (default: `"strategy_research"`).
  - `ResearchMemory` class:
    - `__init__(cfg=DEFAULT_CONFIG)`:
      - Creates a `PersistentClient` pointing at `cfg.chroma_path`.
      - Gets/creates a collection named `cfg.collection_name`.
    - `store_strategy_result(strategy_name, symbol, timeframe, stats, extra=None)`:
      - Builds a document id: `"{strategy_name}:{symbol}:{timeframe}"`.
      - Constructs a simple newline-separated text document summarizing:
        - strategy id, symbol, timeframe,
        - all key/value pairs in `stats`,
        - optional extra fields.
      - Builds a metadata dict with `strategy_name`, `symbol`, `timeframe`, plus
        any `extra_` fields.
      - Adds the document + metadata into the Chroma collection via `add(...)`.
    - `query_similar(text, n_results=5, where=None)`:
      - Uses Chroma's `collection.query(...)` with `query_texts=[text]`.
      - Returns the raw Chroma response (ids, documents, metadatas, distances).

## How It’s Used

- `scheduler/job_research_strategies()`:
  - For each evaluated strategy, after computing `eval_result` (which includes
    base stats + robustness + `strategy_explain`):
    - Calls `memory.store_strategy_result(...)` to persist the result in Chroma.
  - This creates a long-lived corpus of strategy behaviors that can be
    searched/analysed later.

- Future AI-assisted research (Level 1/2):
  - Scripts can call `ResearchMemory.query_similar(...)` to:
    - Find strategies with similar performance/regime patterns.
    - Look up "what has worked before" under certain conditions.

## Configuration & Setup

- The default `chroma_path` (`"./chroma_data"`) expects a directory in the
  workspace root. When using Docker, this is typically mounted into a Chroma
  container (see `START_AUTONOMOUS_TRADING.md` and setup docs).
- `collection_name` can be changed if you want multiple independent research
  collections (e.g. per symbol or per project).

## Gotchas / Notes

- This module assumes ChromaDB is installed and available in the Python
  environment used by `autonomous_trading_ai`.
- `store_strategy_result` writes relatively verbose text; for very large-scale
  usage, you may want to prune which fields are serialized or add a compact
  JSON representation.
- Because this is research-only, failures in Chroma should **not** block live
  trading, but they will reduce the richness of future analysis.
