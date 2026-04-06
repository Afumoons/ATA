# Tasklist

## 2026-04-06 - Live BTC risk sizing audit

Completed in this checkpoint:
- [x] audit reported ~10% live BTC risk spike using `execution/open_trades.json`, `execution/trades.log`, `execution/strategy_live_stats.json`, and `logs/system.log`
- [x] confirm BTC live sizing used an incorrect pip-value constant (`0.1` instead of `1.0`), inflating real stop risk by about 10x
- [x] patch BTC/crypto execution pip-value defaults in `execution/engine.py` and `execution/signals.py`
- [x] add regression coverage for BTC pip-value defaults in `tests/test_bugfix_batch_20260406.py`

## 2026-04-06 - Track D next high-impact batch

Completed in this checkpoint:
- [x] audit BTC `low_trade_count` failure mode after the 2026-04-06 coherence audit
- [x] patch inverted BTC challenger research trade floor conservatively
- [x] land XAG viability repair v2 with XAG-only prior changes
- [x] investigate why live manifest families remained mostly `unknown`
- [x] patch live manifest family recovery for legacy rule-only pool records
- [x] run focused tests for the above changes
- [x] rebuild runtime artifacts and verify live manifest `unknown` family count dropped to `0`
- [x] document the batch in `docs/clio/track-d-d5c-btc-gate-xag-v2-and-manifest-family-repair.md`

Completed in this checkpoint:
- [x] cross-check 12 supplied bottleneck/design findings conservatively
- [x] patch duplicated research-memory neighbor queries via shared prefetch in `scheduler/main.py`
- [x] normalize empty-backtest outputs to full zero-trade stats in `backtests/engine.py`
- [x] document fixed/deferred/not-bug verdicts in `docs/clio/18-BOTTLENECK-CROSSCHECK-AUDIT-2026-04-06.md`
- [x] add focused regression tests for the above

Still pending:
- [ ] run a fresh full Track D rerun to measure BTC challenger continuity after the gate fix
- [ ] run a fresh full Track D rerun to measure XAG cheap-prescreen survival after repair v2
- [ ] verify whether any XAG candidates now survive into pool/index/live-manifest continuity
- [ ] design an explicit operator-facing circuit-breaker reset workflow with audit logging and safe manual controls
- [ ] decide whether research should add a catastrophic-backtest early-exit before walk-forward/Monte Carlo, with challenger/bootstrap exemptions defined explicitly
- [ ] profile research runtime before attempting walk-forward parallelization or Chroma write batching
