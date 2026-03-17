## 2026-03-17 06:06 (Asia/Jakarta)

- Phase: Phase 3 – generator improvements (hard filters)
- Changes:
  - Tightened the research hard filter in `scheduler.job_research_strategies` so that strategies with `num_trades < 50` in backtests are now discarded outright (logged as a Phase 3 minimum-trade floor), aligning with the Phase 3 guidance to require a more meaningful activity level before considering candidates for `candidate` / `exploratory` / `active` tiers.
  - Updated `dev_notes/phase3_generator_improvements.md` to the newer, more focused version that emphasizes practical XAUUSD/BTCUSDT 15m templates, regime metadata, and explicit hard filters; this matches the current development plan used by the dev agent.
- Tests:
  - python -c "import autonomous_trading_ai" (from workspace root) – PASS.
- Notes:
  - This is a small Phase 3 safety/quality step focused purely on filtering; it does not change risk per trade or live execution wiring. Future Phase 3 work can build on this by adding the new XAU/BTC 15m templates and additional performance floors once more research/live data is available.

## 2026-03-17 06:36 (Asia/Jakarta)

- Phase: Phase 3 – generator improvements (template bias)
- Changes:
  - Updated `strategies/generator.py` so that for core 15m markets (XAUUSDm and BTCUSDm), the generator now prefers simpler MA/RSI-based templates (`ma_short`/`ma_long` trend continuation and RSI range-mean-reversion) and avoids heavy Ichimoku/Fibonacci templates. Other markets still have access to the full template set but are biased toward the lighter templates.
  - Added lightweight family/regime metadata to generated strategies via `params` (`long_family`, `short_family`, `regime_type_long`, `regime_type_short`) to support future Phase 3/4 governance and regime-aware tooling.
- Tests:
  - python -m compileall autonomous_trading_ai (from workspace root) – RUN (non-zero exit due to third-party packages under `.venv`, but project package modules compiled without reported syntax errors).
  - python -c "import autonomous_trading_ai" (from workspace root) – PASS.
- Notes:
  - This is a small, safe Phase 3 step that only affects how new strategies are generated; it does not change risk per trade, live execution routing, or status promotion logic. Existing strategies in the pool are untouched. Future Phase 3 work can introduce richer XAU/BTC-specific templates and optional ATR-based SL/TP once more data is available.

## 2026-03-17 07:36 (Asia/Jakarta)

- Phase: Phase 3 – generator improvements (performance floors)
- Changes:
  - Extended `scheduler.job_research_strategies` to apply conservative Phase 3 performance floors for backtest results after the existing `num_trades >= 50` filter. Candidates with `profit_factor < 1.15` or `sharpe_ratio < 0.2` are now discarded with a clear log message, raising the baseline quality of what can reach `candidate` / `exploratory` / `active`.
- Tests:
  - python -m compileall . (from repo root) – RUN (non-zero exit due to `.venv`/third-party packages, but project modules including `scheduler/main.py` compiled without reported syntax errors).
- Notes:
  - This is a small, safety-oriented Phase 3 step that only tightens research-time selection; it does not change live risk percentages, execution routing, or status promotion thresholds beyond skipping weak candidates earlier.

## 2026-03-17 13:07 (Asia/Jakarta)

- Phase: Phase 3 – generator improvements (ATR SL/TP wiring)
- Changes:
  - Extended `StrategyDefinition` to carry optional `sl_atr_mult` and `tp_atr_mult` fields (with serialization in `to_dict`/`from_dict`), enabling the backtest engine’s existing ATR-based SL/TP support to be used by generated strategies in a structured way.
  - Updated `strategies/generator.random_strategy` so that for core 15m markets (XAUUSDm and BTCUSDm), newly generated strategies now sample conservative ATR-based SL/TP multiples (e.g. SL 1.5–2.5 × ATR, TP 2–4 × ATR) and store them in both `params` and the new dataclass fields; other markets continue to use the existing fixed pip distances only.
- Tests:
  - python -c "import autonomous_trading_ai" (from workspace root) – PASS.
- Notes:
  - This is a contained Phase 3 step that only affects how new strategies define SL/TP during backtests; live execution still uses pip-based distances, and no risk percentages or live routing logic were changed. Existing saved strategies without ATR metadata remain compatible via the default `None` values.
