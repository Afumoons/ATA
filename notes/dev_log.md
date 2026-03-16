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
