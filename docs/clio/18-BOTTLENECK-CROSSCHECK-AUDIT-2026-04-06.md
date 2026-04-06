# 18 - Bottleneck / design cross-check audit (2026-04-06)

## Objective

Cross-check the 12 supplied bottleneck / design / code-quality findings against the current codebase, fix only low-regret items, and record the rest with exact rationale.

## Verdict matrix

### 1) Walk-forward sequential bottleneck / potential parallelization
- **Verdict:** deferred
- **Code reference:** `scheduler/main.py:914` runs `walk_forward_test(...)` inline per surviving candidate.
- **Assessment:** real throughput bottleneck in larger research batches, but safe parallelization is not a one-line patch because current research flow also mutates shared counters, logs, memory decisions, and pool updates in the same loop.
- **Action in this batch:** no code change.
- **Next recommendation:** parallelize only after isolating candidate evaluation into side-effect-light workers and merging results deterministically.

### 2) Ticket map `stat()` call per strategy
- **Verdict:** not-bug / low value
- **Code reference:** `execution/signals.py:_load_ticket_map()`.
- **Assessment:** it already caches the parsed map and only re-reads when `(ticket_map_mtime, trades_log_mtime)` changes. The remaining `Path.stat()` calls are tiny compared with MT5 I/O and signal execution.
- **Action in this batch:** no code change.
- **Next recommendation:** only add TTL caching if profiling later shows filesystem latency on the deployment host.

### 3) Strategy JSON opened one-by-one during execution
- **Verdict:** mostly not-bug, documented nuance
- **Code reference:** `execution/signals.py:_load_strats()`.
- **Assessment:** the hot path already prefers embedded manifest payloads from `rec.stats["strategy"]`; JSON fallback is only used for older records missing embedded strategy payloads. A preload cache would help only the fallback path and adds invalidation complexity.
- **Action in this batch:** no code change.
- **Next recommendation:** continue migrating records toward embedded manifest payloads; only add a file cache if fallback frequency becomes material in profiling.

### 4) ChromaDB synchronous per-candidate upsert
- **Verdict:** deferred
- **Code reference:** `vector_memory/research_memory.py:store_strategy_result()` and `scheduler/main.py:1107`.
- **Assessment:** synchronous single-record upserts are real write overhead, but batching would alter failure semantics and complicate durability / partial-write behavior during long research runs.
- **Action in this batch:** no code change.
- **Next recommendation:** if research throughput becomes memory-write bound, batch only accepted/finalized results behind an explicit flush boundary.

### 5) No early-exit before WF for very negative backtest score
- **Verdict:** deferred
- **Code reference:** `scheduler/main.py:851-914`.
- **Assessment:** plausible optimization, but the safe threshold is policy-sensitive because challenger / bootstrap flows deliberately allow weaker backtest metrics through some later gates. A rushed cutoff could quietly suppress intended exploratory families.
- **Action in this batch:** no code change.
- **Next recommendation:** introduce only after defining a clearly catastrophic backtest floor that is explicitly exempt-aware.

### 6) Cheap prescreen DD sign convention consistency
- **Verdict:** not-bug
- **Code reference:** `scheduler/main.py:_passes_cheap_prescreen()` uses `abs(max_drawdown_pct)`; `backtests/evaluation.py:_abs_drawdown()` does the same.
- **Assessment:** storage uses signed drawdown in several places, but gating logic intentionally normalizes to absolute drawdown. This is internally consistent.
- **Action in this batch:** no code change.

### 7) `pool.save()` double-builds live manifest via `rebuild_runtime_artifacts` / `build_strategy_index`
- **Verdict:** not-bug
- **Code reference:** `strategies/pool.py:save_pool()` and `strategies/live_manifest.py:rebuild_runtime_artifacts()`.
- **Assessment:** `save_pool()` calls `rebuild_runtime_artifacts()` once, and that helper intentionally builds manifest once plus index once. No duplicate rebuild path was found in the save flow itself.
- **Action in this batch:** no code change.

### 8) No circuit breaker reset mechanism
- **Verdict:** real operational gap, deferred
- **Code reference:** `execution/live_monitor.py:update_live_stats()` disables live-tier strategies when breached; no explicit reset job exists.
- **Assessment:** the reset path is genuinely missing as an operator-facing workflow, but adding an automatic reset in the same batch would change safety behavior materially.
- **Action in this batch:** no code change.
- **Next recommendation:** add a separate explicit/manual reset workflow with audit logging and clear eligibility rules.

### 9) Duplicate news lockout checks / logging
- **Verdict:** not-bug
- **Code reference:** `scheduler/main.py:1222` and `execution/signals.py:422`.
- **Assessment:** duplication is intentional defense-in-depth. Scheduler skips early to save work; execution re-checks in case another caller bypasses the scheduler path. The extra log noise is minor.
- **Action in this batch:** no code change.

### 10) `_challenger_research_min_trades` XAU challenger floor not actually softened
- **Verdict:** not-bug
- **Code reference:** `scheduler/main.py:_challenger_research_min_trades()` returns `min(base, 60)` for XAU while `_base_research_min_trades()` already returns `60`.
- **Assessment:** XAU is intentionally left unchanged there; only BTC and XAG are softened. The function is awkward, but behavior matches the current policy/tests.
- **Action in this batch:** no code change.

### 11) `_memory_is_clearly_bad` and `_memory_dead_zone_penalty` duplicate similar Chroma queries with different `n_results`
- **Verdict:** confirmed, fixed
- **Code reference:** `scheduler/main.py`.
- **Assessment:** both checks built essentially the same query text and hit Chroma separately for the same candidate. Because `ResearchMemory` cache keys include `n_results`, those calls did not share cache entries.
- **Fix:** added `_memory_query_text(...)` / `_memory_neighbors(...)`, prefetched one 12-neighbor result per candidate, reused it for both memory veto and dead-zone scoring, and sliced to 10 neighbors where the veto logic expects that smaller sample.
- **Why low-regret:** behavior remains equivalent while removing one duplicate semantic-memory query per candidate.

### 12) Backtest engine sparse stats on `df.empty`
- **Verdict:** confirmed, fixed
- **Code reference:** `backtests/engine.py:run_backtest()` empty-dataframe branch.
- **Assessment:** the old branch returned only `initial_equity`, `final_equity`, and `num_trades`, which made empty-dataframe results structurally inconsistent with normal backtests.
- **Fix:** empty inputs now log explicitly and return a full zero-trade stats payload via `_compute_basic_stats(...)`.
- **Why low-regret:** consumers now receive the same metric surface without changing economic behavior.

## Code changes landed

- `scheduler/main.py`
  - added reusable memory-query helpers
  - prefetched one Chroma neighbor set per candidate and reused it for both veto + dead-zone logic
- `backtests/engine.py`
  - normalized empty-dataframe return stats to the full zero-trade schema
- `tests/test_bugfix_batch_20260406.py`
  - added regression coverage for shared memory-neighbor reuse
  - added regression coverage for empty-backtest stats consistency

## Focused tests

- `pytest tests/test_bugfix_batch_20260406.py`
- `pytest tests/test_live_manifest.py tests/test_hardening_regime_and_generation.py`

## Recommended next batch

1. design an explicit circuit-breaker reset workflow with auditability
2. decide whether catastrophic-backtest early-exit rules should exist for research, with bootstrap/challenger exemptions defined up front
3. profile research runtime before attempting walk-forward parallelization or Chroma batching
