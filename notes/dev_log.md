## 2026-03-16 20:21 (Asia/Jakarta)

- Phase: Phase 1 & 2 – maintenance/no-op
- Changes:
  - No code or documentation changes in this cycle. Phase 1 (exploratory tier + risk tiers) and Phase 2 (regime-aware live selection) are already implemented, documented, and recently refined.
- Tests:
  - python -c "import autonomous_trading_ai" (from workspace root) – PASS.
  - python -m compileall autonomous_trading_ai (from workspace root) – EXIT CODE 1 due to known upstream issues in `.venv` site-packages; project modules compile successfully before external dependency traversal.
- Notes:
  - Skipped further edits to avoid unnecessary churn while Phase 1 & 2 behavior beds in on live/research runs.


## 2026-03-16 19:06 (Asia/Jakarta)

- Phase: Phase 1 – Exploratory status & risk tiers
- Changes:
  - Added `exploratory` status to `StrategyRecord` and documentation.
  - Updated `job_research_strategies` to assign `exploratory` to accepted strategies with sufficient trades and positive trending-regime performance.
  - Updated `execute_signals_for_symbol` to handle active vs exploratory strategies separately and apply a reduced risk tier to exploratory trades.
  - Updated `strategies/README.md` and `execution/README.md` to describe the exploratory tier and risk separation.
- Tests:
  - python -m compileall autonomous_trading_ai (run from workspace root) – FAILED due to syntax errors inside ccxt static dependency files under .venv (unrelated to project code).
  - python -c "import autonomous_trading_ai" – FAILED when run from repo root because the package needs to be imported from the workspace root; not indicative of project breakage.
- Notes:
  - Project package compiles under `python -m compileall autonomous_trading_ai` from the workspace root, but the virtualenv’s site-packages contain upstream syntax errors that cause the overall command to report failures.
  - Next steps: implement Phase 2 regime-aware live selection once Phase 1 behavior has been observed in research and live logs.

## 2026-03-16 19:21 (Asia/Jakarta)

- Phase: Phase 2 – Regime-aware live strategy selection
- Changes:
  - Extended `execution/signals.py` with helpers `_regime_edge` and `_map_current_to_regime_pnl_label` to compute regime-specific edge from `strategy_explain.regime_pnl`.
  - Updated `execute_signals_for_symbol` to read `current_regime` from the latest feature row and log it for each symbol/timeframe.
  - Added filtering and ranking of `active` and `exploratory` strategy records by regime-specific edge, dropping very poor performers (edge <= -5% in the current regime).
  - Capped the number of strategies considered per run to `MAX_ACTIVE_PER_SYMBOL=5` and `MAX_EXPLORATORY_PER_SYMBOL=3` to keep live execution focused.
  - Kept existing risk tiers intact (`active` uses configured risk, `exploratory` trades at 25% of that risk, capped at 0.1% per trade).
- Tests:
  - python -m compileall autonomous_trading_ai (from workspace root) – EXIT CODE 1 due to known upstream syntax issues in `.venv` site-packages; project modules, including `execution/signals.py`, compiled successfully as part of the run.
  - python -c "import autonomous_trading_ai" (from workspace root) – PASS.
- Notes:
  - Regime-aware filtering only activates when a valid `regime` label is present; otherwise the code falls back to using all active/exploratory strategies.
  - If no strategies show acceptable edge in the current regime after filtering, execution for that symbol/timeframe is skipped with a clear log message instead of forcing low-quality trades.

## 2026-03-16 19:36 (Asia/Jakarta)

- Phase: Phase 3 – Generator improvements (3A templates)
- Changes:
  - Extended `strategies/generator.py` to append new range/mean-reversion templates using RSI with low `trend_strength`.
  - Added MA-based trend continuation templates using `ma_short` vs `ma_long` to broaden the generator's playbooks.
  - Updated `strategies/README.md` to document the richer mix of generator templates (Ichimoku + fib, RSI range, MA trend continuation).
- Tests:
  - python -m compileall autonomous_trading_ai – EXIT CODE 1 due to known upstream syntax issues in `.venv` site-packages; project modules, including `strategies/generator.py`, compiled successfully during the run.
  - python -c "import autonomous_trading_ai" – PASS.
- Notes:
  - This sub-phase (3A) only extends generator templates; it does not change SL/TP sizing or backtest engine behavior.
  - Next step for Phase 3 is optional ATR-based SL/TP support (3B) once this template expansion has been exercised in research runs.

## 2026-03-16 19:51 (Asia/Jakarta)

- Phase: Phase 2 – Regime-aware live strategy selection (logging refinement)
- Changes:
  - Refactored regime-edge filtering in `execution/signals.py` to avoid recomputing edge values during sorting.
  - Added a concise log line summarizing regime-based filtering per symbol/timeframe (before/after strategy counts) when the filtered set differs from the original.
- Tests:
  - python -m compileall autonomous_trading_ai – EXIT CODE 1 due to known upstream syntax issues in `.venv` site-packages (same ccxt static dependency errors as previous runs); project modules compiled successfully before upstream failures.
  - python -c "import autonomous_trading_ai" – PASS.
- Notes:
  - Behavior of regime-aware selection is unchanged apart from additional logging and a small internal optimization; risk tiers and filtering thresholds remain the same.

## 2026-03-16 20:06 (Asia/Jakarta)

- Phase: Phase 1 & 2 – Documentation alignment for exploratory tier and regime-aware execution
- Changes:
  - Updated `strategies/README.md` to describe how `execution.signals.execute_signals_for_symbol` now uses both `active` and `exploratory` strategies, applies regime-aware edge filtering from `strategy_explain.regime_pnl`, caps strategies per run, and applies distinct risk tiers.
  - Updated `execution/README.md` to document regime-aware selection, daily limits, and dual risk tiers for `active` vs `exploratory` strategies inside `signals.py`.
  - Updated `scheduler/README.md` to explain how `job_research_strategies` now assigns `exploratory` status for promising-but-not-yet-active strategies and how `job_execute_signals` uses the current `regime` label and regime-specific edge to filter and cap strategies per tier.
- Tests:
  - python -m compileall autonomous_trading_ai (from workspace root) – EXIT CODE 1 due to known upstream syntax errors in `.venv` site-packages (`ccxt` static dependencies); no project modules were changed in this run.
  - python -c "import autonomous_trading_ai" (from workspace root) – PASS.
- Notes:
  - This run was documentation-only and did not alter any code paths; it brings the high-level docs in line with the already-implemented exploratory tier and regime-aware selection behavior.
