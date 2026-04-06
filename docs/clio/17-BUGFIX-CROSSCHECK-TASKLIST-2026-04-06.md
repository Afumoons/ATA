# 17 - Bugfix cross-check tasklist (2026-04-06)

## Objective

Cross-check eight externally supplied bug findings against the current codebase, fix every confirmed issue narrowly, add focused regression tests, and record any nuance where the reported symptom is real but the exact location differs.

## Verification matrix

### 1) XAG pip_size wrong in Monte Carlo simulation
- **Status:** confirmed
- **Code reference:** `scheduler/main.py` research MC call used `pip_size=0.01 if "XAU" in canon else 1.0`
- **Why valid:** `backtests/engine.py` and `execution/signals.py` already treat XAG as `pip_size=0.01`, so MC was inconsistent for silver.
- **Fix:** MC now uses `0.01` for both XAU and XAG.

### 2) BTC pip_value_per_lot inconsistency between routing and execution sizing
- **Status:** confirmed
- **Code reference:** `execution/signals.py:_pip_params()` returned `(1.0, 1.0)` for BTC-family symbols, while `execution/engine.py:_DEFAULT_PIP_VALUE_PER_LOT` uses `0.1` for BTC.
- **Why valid:** signal-layer sizing sent a 10x larger pip value than the execution engine default, which suppresses volume by ~10x.
- **Fix:** `_pip_params()` now aligns BTC-family symbols to `pip_value_per_lot=0.1`; XAG was also aligned to `0.5` to match execution defaults.

### 3) Stale `open_positions` snapshot can allow duplicate attempts inside one execution cycle
- **Status:** confirmed (with nuance)
- **Code reference:** `execution/signals.py:execute_signals_for_symbol()` captured `open_positions = mt5.positions_get(symbol=symbol)` once before iterating signals.
- **Why valid:** later iterations were checking against a stale snapshot. `execution/engine.py:execute_trade()` still has its own live guard, so the issue was partially mitigated, but the signal loop itself could still make an unnecessary second attempt within the same cycle.
- **Fix:** refresh the MT5 snapshot after each successful order before processing the next signal.

### 4) `WalkForwardConfig.train_ratio` declared but unused
- **Status:** confirmed
- **Code reference:** `backtests/walkforward.py` declared and threaded `train_ratio`, but `_split_walkforward_indices()` never used it.
- **Why valid:** it was dead configuration and misleading documentation.
- **Fix:** removed `train_ratio` from config/function signatures and cleaned the nearby docstrings/comments so the implementation matches the public surface.

### 5) `same_bar_ambiguity_take_profit_count` never increments
- **Status:** confirmed
- **Code reference:** `backtests/engine.py` incremented `same_bar_ambiguity_count` and `same_bar_ambiguity_stop_loss_count` when both SL and TP were touched in the same candle, but never incremented the TP counter.
- **Why valid:** the metric was always stuck at zero even when TP was touched in ambiguous bars.
- **Fix:** increment the TP ambiguity counter in both long and short same-bar ambiguity branches.

### 6) Evolution fingerprint missing fixed SL/TP pips
- **Status:** confirmed
- **Code reference:** `strategies/evolution.py:_strategy_fingerprint()` omitted `stop_loss_pips` / `take_profit_pips`.
- **Why valid:** static-risk variants with identical entry/exit logic were treated as duplicates.
- **Fix:** added fixed SL/TP pips to the evolution fingerprint.
- **Related hardening:** mirrored the same fix in `strategies/pool.py` structural dedup fingerprints so pool dedup does not keep collapsing those variants later.

### 7) ResearchMemory query cache not invalidated after store
- **Status:** confirmed
- **Code reference:** `vector_memory/research_memory.py:store_strategy_result()` updated Chroma via `upsert()` but left `_query_cache` untouched.
- **Why valid:** repeated queries could keep returning stale neighbors after a write.
- **Fix:** clear `_query_cache` immediately after a successful upsert.

### 8) `_apply_live_degradation` only targets XAUUSDm instead of core universe
- **Status:** confirmed symptom, location nuance
- **Code reference:** the XAU-only hardcoding was found immediately **after** `_apply_live_degradation(pool)` in `scheduler/main.py`, inside the challenger-governance candidate/exploratory protection block (`canonical_symbol(rec.symbol) == "XAUUSDm"`).
- **Why valid:** BTC/XAG challengers were excluded from the same protection/promotion logic.
- **Fix:** broadened that symbol scope to the managed core-universe canonical symbols already represented by `RESEARCH_FAMILY_SUMMARY_SYMBOLS` (`XAUUSDm`, `BTCUSDm`, `XAGUSDm`).

## Implementation tasklist

- [x] Verify each report against code before editing
- [x] Fix confirmed Monte Carlo XAG pip size mismatch
- [x] Align BTC live pip-value sizing with execution engine defaults
- [x] Refresh live open-position snapshot after successful executions
- [x] Remove unused walk-forward `train_ratio` surface and doc drift
- [x] Repair same-bar TP ambiguity accounting
- [x] Extend fingerprint/dedup identity with fixed SL/TP pips
- [x] Invalidate ResearchMemory query cache after writes
- [x] Expand challenger-governance symbol scope across core universe
- [x] Add focused regression tests for the confirmed bugs
- [x] Commit one coherent bugfix batch

## Files expected in patch

- `backtests/engine.py`
- `backtests/walkforward.py`
- `execution/signals.py`
- `scheduler/main.py`
- `strategies/evolution.py`
- `strategies/pool.py`
- `vector_memory/research_memory.py`
- `tests/test_bugfix_batch_20260406.py`
