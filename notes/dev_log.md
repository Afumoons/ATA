## 2026-03-17 20:21 (Asia/Jakarta)

- Phase: Phase 4.1 – ResearchMemory candidate-neighborhood support
- Changes:
  - Extended `vector_memory/ResearchMemory.store_strategy_result` to persist a small set of key backtest/eval stats (`return_pct`, `sharpe_ratio`, `profit_factor`, `max_drawdown_pct`, `num_trades`, `score`) into Chroma metadata under `stat_*` keys, so downstream Phase 4 logic can reason about neighbor quality without re-parsing documents.
  - Added `ResearchMemory.query_similar_strategies(symbol, timeframe, text=None, n_results=10)` as a convenience helper that filters by symbol/timeframe, calls the existing `query_similar`, and returns a normalized list of neighbor dicts including id, distance, basic metadata, and any `stat_*` fields.
- Tests:
  - python -c "import autonomous_trading_ai" (from workspace root) – PASS.
- Notes:
  - This is a small, self-contained Phase 4.1 groundwork change confined to `vector_memory/research_memory.py`; it does not yet alter scheduler behavior or candidate filtering. Future runs can safely plug `query_similar_strategies` into `job_research_strategies` to implement conservative pre-backtest filtering based on clusters of historically poor strategies.

## 2026-03-17 21:23 (Asia/Jakarta)

- Phase: Phase 3 – generator improvements (indicator simplicity)
- Changes:
  - Updated `strategies/generator.random_strategy` so that for non-core markets it now also uses only the lighter MA/RSI-based entry templates, temporarily disabling heavy Ichimoku/Fibonacci-based templates. This aligns generator output with the Phase 3 goal of avoiding indicator soup and focusing on simpler, more interpretable structures.
- Tests:
  - python -c "import autonomous_trading_ai" (from workspace root) – PASS.
- Notes:
  - Heavy Ichimoku/Fibonacci templates remain defined for now but are no longer sampled by the generator for any symbol/timeframe. Future Phase 3 work can still introduce explicit XAUUSD/BTCUSDT 15m trend/range/session families using the existing MA/RSI/ATR features.

## 2026-03-17 22:30 (Asia/Jakarta)

- Phase: Phase 4.2 – memory-guided elite parent selection
- Changes:
  - Updated `scheduler/job_research_strategies` to compute a small `memory_bonus` for each potential parent strategy using `ResearchMemory.query_similar_strategies`, based on the proportion of historically good vs bad neighbors (via `stat_sharpe_ratio`, `stat_profit_factor`, and `stat_return_pct`).
  - Parent candidates for a given symbol/timeframe are now ranked by a hybrid score `rec.score + memory_bonus`, with the bonus capped to a small range ([-0.2, 0.2]) and logged for auditability, so backtest scores remain primary while memory gently nudges selection toward more robust neighborhoods.
- Tests:
  - python -c "import autonomous_trading_ai" (from workspace root) – PASS.
- Notes:
  - This is a conservative Phase 4.2 step: it does not change promotion/demotion thresholds or risk, only which parents are slightly favored during evolution. Future runs can tune the neighbor-quality heuristic or the bonus scale if needed, based on observed effects on pool composition.
