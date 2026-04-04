# Family Quality Repair – Instructions & Tasklist

## Purpose

This file is the active working instruction + progress tracker for the next improvement wave after the first Family-aware governance audit.

Use it for:
- clear execution order
- visible checkmarks
- preserving current intent across context loss
- giving Afu a simple place to inspect progress

Related context:
- `08-XAU-M15-CORE15-ACCEPTANCE-GATE-AUDIT.md`
- `09-XAU-M15-ACCEPTANCE-GATE-TRACE.md`
- `10-XAU-M15-FAMILY-GOVERNANCE-RESULTS.md`
- `06-M15_IMPROVEMENT_ROADMAP.md`
- `07-ROUTING_LAYER_AUDIT_AND_TASKLIST.md`

---

## Current strategic conclusion

The latest after-run audit shows:

- family-aware governance was worth doing
- generation diversity is no longer the main bottleneck
- the dominant bottleneck has shifted toward **strategy quality**, especially:
  - zero-trade families
  - catastrophic-loss families
  - family templates that fail cheap prescreen too often

So this wave is **not** mainly about reopening governance further.
It is mainly about:

> making challenger families produce more viable candidates before they even reach later pool competition.

---

## Operating principles for this wave

1. **Do not revert family-aware governance**
   - it solved a real access / observability problem

2. **Treat zero-trade as a first-class failure mode**
   - a family that does not trade is not viable just because it avoids losses

3. **Treat catastrophic loss as a template failure, not just bad luck**
   - especially repeated `-90%` to `-100%` style outcomes

4. **Tune by family, not by vague global optimism**
   - different families need different priors and guardrails

5. **Instrument before over-tuning**
   - make it easy to see where each family dies:
     - generated
     - cheap prescreen
     - backtest
     - walk-forward
     - Monte Carlo
     - accepted / candidate / exploratory / active

6. **Prefer clean bounded improvements**
   - reduce obvious junk generation before adding more complexity

---

## Track name

**Track D — Family Quality Repair & Acceptance Diagnostics**

This follows Afu’s naming preference to avoid ambiguous “phase” references.

---

## Definition of done for Track D

Track D is only "done" when most of these are true:

- challenger family stage counts are visible in logs/artifacts
- zero-trade patterns are materially reduced for at least key families
- catastrophic-loss families have tighter generation priors / sanity checks
- `XAUUSDm M15` shows more credible challenger survival than before
- `XAGUSDm M15` stops dying almost entirely at cheap prescreen
- docs are updated and committed

---

# Tasklist

## D1 — Build family stage-count instrumentation

### Goal
Make bottleneck diagnosis near-automatic by logging where each family dies.

### Deliverable
Per symbol/timeframe/family counts for:
- generated
- cheap prescreen pass/fail
- backtest pass/fail
- WF pass/fail
- MC pass/fail
- accepted
- candidate
- exploratory
- active

### Tasks
- [ ] Add per-family counters inside `job_research_strategies()`
- [ ] Capture skip reasons grouped by family
- [ ] Emit compact family-stage summaries for `XAUUSDm M15`
- [ ] Emit compact family-stage summaries for `XAGUSDm M15`
- [ ] Decide where to persist these summaries (log only vs JSON artifact)
- [ ] Document the artifact/log format

### Progress notes
- Status: not started
- Owner: Clio Nova

---

## D2 — Diagnose zero-trade families

### Goal
Identify why certain families repeatedly produce `0 trades`.

### Focus families
- `vol_breakout`
- `compression_breakout`
- `session_breakout`
- `xau_impulse_pullback`
- `xau_session_continuation`
- any other family with strong zero-trade tendency in current logs

### Questions to answer
- Are entry conditions too strict?
- Are thresholds contradictory?
- Are session filters too narrow?
- Are symbol/session priors mismatched?
- Are volatility bands unrealistic for current feature scales?

### Tasks
- [ ] Sample generated strategies per zero-trade family
- [ ] Compare rule structure and parameter ranges
- [ ] Identify the top recurring causes of `0 trades`
- [ ] Propose family-specific generator constraints
- [ ] Implement the first batch of zero-trade mitigations
- [ ] Re-run research and compare zero-trade counts before vs after

### Progress notes
- Status: not started
- Owner: Clio Nova

---

## D3 — Diagnose catastrophic-loss families

### Goal
Identify families that do trade, but in structurally broken ways.

### Focus families
- `ma_trend`
- `rsi_range`
- `pullback_trend`
- any family showing repeated extreme drawdown or near-total equity collapse

### Questions to answer
- Are SL/TP ratios structurally bad?
- Are trend/range thresholds inverted or too permissive?
- Are exits too weak relative to entries?
- Are some families overfitting to impossible bar assumptions?

### Tasks
- [ ] Sample worst challenger backtests from the last run
- [ ] Group failures by family archetype
- [ ] Identify recurring catastrophic-loss signatures
- [ ] Add family-level sanity filters / priors
- [ ] Re-test after the first patch batch

### Progress notes
- Status: not started
- Owner: Clio Nova

---

## D4 — Tighten family-specific generator priors

### Goal
Use family-aware priors to reduce junk before evaluation.

### Examples of likely changes
- `ma_trend`
  - stronger trend coherence requirements
  - avoid hyper-reactive thresholds that overtrade into destruction
- `rsi_range`
  - prevent range logic from fighting strong directional conditions
- breakout families
  - reduce impossible volatility/session combinations
  - avoid conditions that nearly never trigger
- continuation families
  - align session conditions with realistic liquidity windows

### Tasks
- [ ] Audit current generator parameter ranges by family
- [ ] Create a first patch batch of family priors
- [ ] Keep changes explicit and documented
- [ ] Re-run research cycle
- [ ] Compare family-stage counts after the patch

### Progress notes
- Status: not started
- Owner: Clio Nova

---

## D5 — Improve XAU vs XAG family separation

### Goal
Stop assuming XAU and XAG should share the same practical priors.

### Why
The after-run audit suggests:
- `XAU` may still be partly governance/history-sensitive
- `XAG` is currently failing even earlier at cheap prescreen

### Tasks
- [ ] Verify symbol canonicalization and feature-path consistency for XAG
- [ ] Compare XAU vs XAG generated family behavior
- [ ] Identify families that need different XAU/XAG parameter priors
- [ ] Implement the first market-specific family prior split
- [ ] Re-run and compare outcomes across both metals

### Progress notes
- Status: not started
- Owner: Clio Nova

---

## D6 — Preserve operator legibility

### Goal
Keep Afu able to inspect progress without digging through logs.

### Tasks
- [ ] Update this file with checkmarks as work progresses
- [ ] Write short dated progress notes into this file or companion docs
- [ ] Create a compact results doc after each major rerun
- [ ] Commit every coherent batch with clear commit messages

### Progress notes
- Status: in progress
- Owner: Clio Nova

---

# Immediate execution order

## Batch D1a — Instrumentation first
- [ ] Add family stage counters
- [ ] Add per-family skip-reason summaries
- [ ] Save/report the summaries

## Batch D2a — Zero-trade diagnosis
- [ ] Inspect zero-trade family samples
- [ ] identify rule/threshold contradictions
- [ ] write findings to a doc

## Batch D3a — Catastrophic-loss diagnosis
- [ ] Inspect worst-loss family samples
- [ ] identify recurring broken patterns
- [ ] write findings to a doc

## Batch D4a — First generator-prior repair patch
- [ ] Implement a conservative first batch of family-specific fixes
- [ ] rerun research
- [ ] compare before vs after

## Batch D5a — XAU vs XAG separation
- [ ] verify symbol/canonical handling
- [ ] split the first family priors by metal where justified

---

# Progress log

## 2026-04-05
- [x] Created this instruction + tasklist file.
- [x] Confirmed current post-governance diagnosis: quality is now the dominant active bottleneck.
- [ ] Next live implementation batch: D1a instrumentation.

---

# Notes for Clio Nova

When resuming this track after interruption:
1. read this file first
2. read `10-XAU-M15-FAMILY-GOVERNANCE-RESULTS.md`
3. continue with the next unchecked item in the immediate execution order
4. update this file before claiming progress
5. commit coherent batches
