# vector_memory/ – Research Memory (Chroma)

## Purpose

This module provides a Chroma-backed **research memory** for the trading system.

It is used to:

- persist research results over time
- query for similar historical strategies
- guide candidate generation and parent selection
- support offline analysis and AI-assisted strategy review

It is intentionally a **research support layer**, not a hard dependency for
real-time trade execution.

## Key File

### `research_memory.py`

Defines:

- `ResearchMemoryConfig`
- `ResearchMemory`

Important capabilities include:

- connecting to persistent Chroma storage
- getting/creating the configured collection
- storing strategy result summaries as text + metadata
- querying similar documents with metadata filters
- extracting strategy-oriented neighbor summaries for research jobs

Key methods:

- `store_strategy_result(...)`
- `query_similar(...)`
- `query_similar_strategies(...)`

## What Gets Stored

Each stored item generally represents an evaluated strategy result, including:

- strategy identity
- symbol
- timeframe
- stats-derived fields
- optional extra metadata

The document body is stored as readable text, while key fields also live in
metadata so they can be filtered/queried more effectively.

## Pass 3 Role

Pass 3 keeps vector memory in the “soft guidance” category, but its practical
importance increases because the scheduler now uses it to support a more mature
research loop.

Typical uses include:

- small bonus/penalty adjustments for parent ranking
- early veto of obviously bad pattern families
- preference for more comparable neighbors when multiple execution/research
  modes exist
- richer operator/AI review of what has historically worked in similar contexts

The key point is that vector memory helps the system remember **research
experience**, not live authority.

## How It’s Used

### `scheduler.job_research_strategies()`

- stores fresh evaluation results after each research cycle
- queries similar strategies to help rank parents
- queries similar strategies to help skip clearly bad candidate families

### Support / analysis workflows

Scripts or AI-assisted workflows can use the same store to ask:

- what patterns have worked on this symbol/timeframe?
- what tends to fail?
- are there historically similar strategies with better/worse robustness?

## Configuration

Main configuration surface:

- `chroma_path`
- `collection_name`

Defaults typically point to a workspace-local persistent store such as:

- `./chroma_data`
- collection: `strategy_research`

## Design Notes

### Research-only dependency

Trading should continue even if Chroma is unavailable. Losing vector memory is
bad for research quality, but it should not stop the live stack from enforcing
risk and routing decisions based on already persisted pool state.

### Text + metadata approach

The module stores readable summaries plus machine-filterable metadata. This is a
simple design that works well enough for research without overcomplicating the
storage layer.

## Gotchas / Notes

- ChromaDB must be installed and reachable in the project environment.
- If the collection gets too noisy or stale, maintenance scripts may be needed
  to reset or backfill memory cleanly.
- Similarity search is advisory. It should influence search direction, not act
  as a rigid decision oracle.

## Changelog (Docs)

- 2026-03-21: Documented core Chroma usage for storing and querying strategy
  research results.
- 2026-03-27: Refreshed for pass 3 to emphasize the memory layer as soft
  research guidance for a more mature candidate-selection loop.