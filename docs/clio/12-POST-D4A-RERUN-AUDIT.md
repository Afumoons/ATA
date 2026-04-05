# Post-D4a Rerun Audit

Date: 2026-04-05
Owner: Clio Nova

## Scope

This document records the first rerun/audit after the D4a generator-prior repair patch.

Official core-focus universe for this audit:
- `XAUUSDm`
- `BTCUSDm`
- `XAGUSDm`

Primary source of truth for the work order:
- `docs/clio/11-FAMILY-QUALITY-REPAIR-INSTRUCTIONS-AND-TASKLIST.md`

Related prior docs:
- `docs/clio/track-d-d1a-family-stage-instrumentation.md`
- `docs/clio/track-d-d2a-zero-trade-diagnosis.md`
- `docs/clio/track-d-d3a-catastrophic-loss-diagnosis.md`
- `docs/clio/track-d-d4a-generator-prior-repair-patch.md`
- `docs/clio/10-XAU-M15-FAMILY-GOVERNANCE-RESULTS.md`

## What was run

From workspace parent so imports resolve correctly:

```powershell
$env:PYTHONPATH='.'; python -m pytest autonomous_trading_ai/tests/test_hardening_regime_and_generation.py -q
$env:PYTHONPATH='.'; python -c "from autonomous_trading_ai.scheduler.main import job_research_strategies; job_research_strategies(); print('job_research_strategies done')"
```

Validation result:
- `7 passed`

Rerun result:
- `job_research_strategies()` completed successfully
- refreshed family-stage JSON artifacts:
  - `tmp/research_family_stage_summaries/XAUUSDm_M15.json`
  - `tmp/research_family_stage_summaries/XAGUSDm_M15.json`
- baseline snapshots preserved under:
  - `tmp/research_family_stage_summaries/pre_d4a_baseline/`

## Before vs after family-stage observations

Comparison basis:
- before = JSONs snapshotted just before the rerun from the pre-D4a baseline
- after = JSONs produced by the rerun on current HEAD

### XAUUSDm M15

Generated family mix moved from:
- before: `ma_trend 6`, `rsi_range 2`, `pullback_trend 2`, `vol_breakout 2`, `compression_breakout 2`, `session_breakout 2`, `xau_impulse_pullback 2`, `xau_session_continuation 2`
- after: `ma_trend 6`, `rsi_range 2`, `pullback_trend 4`, `vol_breakout 2`, `compression_breakout 2`, `session_breakout 4`

Key takeaways:
- the dedicated XAU specialist families still exist for XAU only conceptually, but they are no longer emitted in this rerun artifact as separate families
- zero-trade cheap-prescreen samples improved from `11/20` to `7/20`
- `pullback_trend` and `session_breakout` both received more generation budget than before
- catastrophic-loss behavior did **not** disappear in the surviving trend/range families
  - examples remain in `ma_trend`, `rsi_range`, and `pullback_trend`
  - representative post-D4a failures still include `dd=98.7%` to `99.2%`

Interpretation:
- D4a helped reduce dead-on-arrival zero-trade generation pressure
- D4a did not yet solve the destructive-family problem for XAU; the bottleneck is still quality, not diversity

### XAGUSDm M15

Generated family mix moved from:
- before: `ma_trend 3`, `rsi_range 3`, `pullback_trend 5`, `vol_breakout 2`, `compression_breakout 3`, `session_breakout 1`, `xau_impulse_pullback 2`, `xau_session_continuation 1`
- after: `ma_trend 2`, `rsi_range 3`, `pullback_trend 5`, `vol_breakout 4`, `compression_breakout 1`, `session_breakout 5`

Key takeaways:
- the XAU-specialist family leakage is gone from the XAG family-stage artifact
- zero-trade cheap-prescreen samples improved from `11/20` to `8/20`
- session and breakout families are now represented much more normally than before
- however, every XAG candidate in the rerun still died at cheap prescreen
- post-D4a XAG still shows catastrophic-loss behavior in the trading families that *do* trigger
  - `ma_trend` remained extremely destructive (`dd≈97.5%–97.7%`)
  - several `rsi_range` / `pullback_trend` variants still lost heavily

Interpretation:
- D4a clearly fixed family leakage and improved family mix quality for XAG
- but XAG is still not surviving past the first acceptance barrier, so the symbol remains strategically unhealthy

## Core-universe coherence check

### 1) Generation surface

**XAUUSDm:** coherent after rerun
- family-stage artifact refreshed successfully
- post-D4a generation no longer showed non-core leakage issues in the new artifact

**BTCUSDm:** partially coherent
- rerun generated fresh `BTCUSDc` family files at `2026-04-05 21:54:21`
- recent BTC generation included normal family set such as:
  - `ma_trend`
  - `rsi_range`
  - `pullback_trend`
  - `compression_breakout`
  - `vol_breakout`
  - `session_breakout`
- importantly, the newest BTC files observed from this rerun did **not** show new `xau_*` specialist-family leakage
- however, Track D family-stage observability is still incomplete for BTC because no BTC family-stage JSON artifact is currently emitted

**XAGUSDm:** generation coherence improved materially
- rerun generated fresh `XAGUSDc` family files at `2026-04-05 21:55:15`
- new XAG generation used the generic family set only
- no post-D4a XAU-specialist leakage was observed in the new rerun batch

### 2) Acceptance / pool surface

Current pool state is not yet coherent with the declared core-focus universe:
- `BTCUSDm` present in pool with statuses:
  - `active: 176`
  - `candidate: 53`
  - `exploratory: 75`
  - `disabled: 61`
- `XAUUSDm` present in pool with statuses:
  - `active: 213`
  - `candidate: 21`
  - `exploratory: 374`
  - `disabled: 65`
- `XAGUSDm` had no comparable pool presence in the current persisted pool snapshot

Interpretation:
- XAU and BTC have functioning acceptance→pool continuity
- XAG still does not have comparable downstream survival, which matches the rerun result where all 20 XAG challengers died at cheap prescreen

### 3) Manifest surface

`strategies/live_manifest.json` rebuilt successfully during the rerun with `32` entries.

Manifest composition after rerun:
- `BTCUSDm`: `16` active entries
- `XAUUSDm`: `16` active entries
- `XAGUSDm`: `0` active entries

Interpretation:
- manifest/runtime surface currently supports only BTC + XAU as live core symbols
- the official core-focus universe is therefore **not yet coherent end-to-end**, because XAG is still absent from manifest despite being part of the intended core set

### 4) Observability surface

Observability state after D4a rerun:
- good for `XAUUSDm` and `XAGUSDm` family-stage diagnostics via JSON artifacts
- incomplete for `BTCUSDm` because Track D family-stage JSON emission still covers only XAU/XAG

Interpretation:
- generation and runtime can touch BTC
- observability does not yet treat BTC as a first-class core symbol in the same way as XAU/XAG

## Net assessment

### What improved
- D4a reduced zero-trade pressure in both audited metals
- D4a removed the most obvious XAU-specialist family leakage from non-XAU rerun output
- BTC/XAU manifest and pool surfaces remain operational
- the rerun itself completed cleanly on current HEAD

### What is still broken
- XAU still has multiple catastrophic-loss family signatures
- XAG still fails to survive cheap prescreen at all in the rerun
- XAG has no live-manifest presence, so the stated core universe is not yet fully coherent
- BTC still lacks parity on family-stage observability artifacts

## Conclusion

Post-D4a status is **improved but not complete**.

The D4a repair batch was directionally correct:
- it improved family mix quality
- it lowered zero-trade incidence
- it stopped the most obvious family-leakage problem

But the official core-focus universe `XAUUSDm / BTCUSDm / XAGUSDm` is **not yet fully coherent across generation, acceptance, pool, manifest, and observability surfaces** because:
- `XAGUSDm` still dies at cheap prescreen and is absent from manifest/pool continuity
- `BTCUSDm` is operational in pool/manifest but not yet first-class in Track D observability artifacts

## Recommended next steps

1. Extend D1-style family-stage artifact emission to `BTCUSDm M15`
2. Run a focused XAG acceptance audit to determine why all 20 post-D4a challengers still fail cheap prescreen
3. Continue catastrophic-loss hardening for `ma_trend`, `rsi_range`, and `pullback_trend`
4. Treat XAG downstream survival as the gating item before calling Track D coherent for the full core universe
