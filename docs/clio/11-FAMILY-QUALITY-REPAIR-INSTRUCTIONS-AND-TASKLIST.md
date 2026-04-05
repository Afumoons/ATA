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
- [x] Add per-family counters inside `job_research_strategies()`
- [x] Capture skip reasons grouped by family
- [x] Emit compact family-stage summaries for `XAUUSDm M15`
- [x] Emit compact family-stage summaries for `XAGUSDm M15`
- [x] Decide where to persist these summaries (log only vs JSON artifact)
- [x] Document the artifact/log format

### Progress notes
- Status: implemented
- Owner: Clio Nova
- 2026-04-05: Added family-stage counters + family-grouped skip reasons in `scheduler/main.py`.
- 2026-04-05: Family-stage summaries now log for all symbols; JSON artifacts are persisted for `XAUUSDm` and `XAGUSDm` under `tmp/research_family_stage_summaries/`.
- 2026-04-05: Artifact/log format documented in `docs/clio/track-d-d1a-family-stage-instrumentation.md`.

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
- [x] Sample generated strategies per zero-trade family
- [x] Compare rule structure and parameter ranges
- [x] Identify the top recurring causes of `0 trades`
- [x] Propose family-specific generator constraints
- [x] Implement the first batch of zero-trade mitigations
- [x] Re-run research and compare zero-trade counts before vs after

### Progress notes
- Status: rerun comparison complete
- Owner: Clio Nova
- 2026-04-05: D1a instrumentation landed first so zero-trade diagnosis can use family-stage artifacts instead of raw log scraping.
- 2026-04-05: Completed D2a diagnosis and wrote `docs/clio/track-d-d2a-zero-trade-diagnosis.md`.
- 2026-04-05: Diagnosis conclusion: the dominant issue is generator-side conjunction overload (session + vol + trend + confirmation stacking), not merely cheap-prescreen strictness.
- 2026-04-05: Post-D4a rerun completed. Zero-trade cheap-prescreen samples improved from 11/20 -> 7/20 for `XAUUSDm M15` and from 11/20 -> 8/20 for `XAGUSDm M15`.

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
- [x] Sample worst challenger backtests from the last run
- [x] Group failures by family archetype
- [x] Identify recurring catastrophic-loss signatures
- [x] Add family-level sanity filters / priors
- [x] Re-test after the first patch batch

### Progress notes
- Status: diagnosis complete, implementation pending
- Owner: Clio Nova
- 2026-04-05: D1a instrumentation landed first so catastrophic-loss diagnosis can sample failures by family/stage from a stable artifact.
- 2026-04-05: Completed D3a diagnosis and wrote `docs/clio/track-d-d3a-catastrophic-loss-diagnosis.md`.
- 2026-04-05: Diagnosis conclusion: destructive families are mainly suffering from over-permissive entries plus weak exit-family coherence, not just bad luck.

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
- [x] Audit current generator parameter ranges by family
- [x] Create a first patch batch of family priors
- [x] Keep changes explicit and documented
- [x] Re-run research cycle
- [x] Compare family-stage counts after the patch

### Progress notes
- Status: first conservative patch landed and first rerun audited
- Owner: Clio Nova
- 2026-04-05: First generator-prior patch intentionally deferred until D2/D3 evidence is captured from the new family-stage summaries.
- 2026-04-05: Implemented D4a conservative generator repair batch in `strategies/generator.py` and documented it in `docs/clio/track-d-d4a-generator-prior-repair-patch.md`.
- 2026-04-05: Landed zero-trade entry simplifications, family-specific exit pools, tighter catastrophic-loss family priors, and a guard preventing XAU-specialist families from leaking into non-XAU generation.
- 2026-04-05: Focused validation passed with `python -m pytest tests/test_hardening_regime_and_generation.py -q` (`7 passed`) using workspace `PYTHONPATH`.
- 2026-04-05: Post-D4a rerun completed and audited in `docs/clio/12-POST-D4A-RERUN-AUDIT.md`. Result: zero-trade pressure improved, XAU-specialist leakage into XAG/BTC rerun output appears fixed, but catastrophic-loss families still persist and `XAGUSDm` still failed to survive cheap prescreen.

---

## D5 — Improve XAU vs XAG family separation

### Goal
Stop assuming XAU and XAG should share the same practical priors.

### Why
The after-run audit suggests:
- `XAU` may still be partly governance/history-sensitive
- `XAG` is currently failing even earlier at cheap prescreen

### Tasks
- [x] Verify symbol canonicalization and feature-path consistency for XAG
- [x] Compare XAU vs XAG generated family behavior
- [ ] Identify families that need different XAU/XAG parameter priors
- [ ] Implement the first market-specific family prior split
- [x] Re-run and compare outcomes across both metals

### Progress notes
- Status: first rerun audit complete; prior split still pending
- Owner: Clio Nova
- 2026-04-05: No XAU/XAG separation changes yet; holding until D2/D3 findings identify where priors and playbooks are still leaking across metals.
- 2026-04-05: Post-D4a rerun confirmed XAU-specialist families are no longer leaking into the new `XAGUSDm` generation batch, and XAU/XAG family mix behavior can now be compared cleanly from the family-stage artifacts. `XAGUSDm` still dies at cheap prescreen, so a market-specific prior split remains justified.

---

## D6 — Preserve operator legibility

### Goal
Keep Afu able to inspect progress without digging through logs.

### Tasks
- [x] Update this file with checkmarks as work progresses
- [x] Write short dated progress notes into this file or companion docs
- [x] Create a compact results doc after each major rerun
- [ ] Commit every coherent batch with clear commit messages

### Progress notes
- Status: in progress
- Owner: Clio Nova

---

# Immediate execution order

## Batch D1a — Instrumentation first
- [x] Add family stage counters
- [x] Add per-family skip-reason summaries
- [x] Save/report the summaries

## Batch D2a — Zero-trade diagnosis
- [x] Inspect zero-trade family samples
- [x] identify rule/threshold contradictions
- [x] write findings to a doc

## Batch D3a — Catastrophic-loss diagnosis
- [x] Inspect worst-loss family samples
- [x] identify recurring broken patterns
- [x] write findings to a doc

## Batch D4a — First generator-prior repair patch
- [x] Implement a conservative first batch of family-specific fixes
- [x] rerun research
- [x] compare before vs after

## Batch D5a — XAU vs XAG separation
- [x] verify symbol/canonical handling
- [ ] split the first family priors by metal where justified

---

# Progress log

## 2026-04-05
- [x] Created this instruction + tasklist file.
- [x] Confirmed current post-governance diagnosis: quality is now the dominant active bottleneck.
- [x] Completed D1a instrumentation.
- [x] Completed D2a zero-trade diagnosis and documented generator-side trigger-overconstraint patterns.
- [x] Completed D3a catastrophic-loss diagnosis and documented over-permissive entry / generic-exit failure signatures.
- [x] Started D4a first generator-prior repair patch and documented the landed batch.
- [x] Reran Track D research and compared family-stage summaries before vs after D4a.
- [x] Wrote the companion rerun results doc: `docs/clio/12-POST-D4A-RERUN-AUDIT.md`.
- [ ] Next live implementation batch: extend family-stage observability to `BTCUSDm` and push the next XAG-specific prior/acceptance repair batch.

---

# Notes for Clio Nova

When resuming this track after interruption:
1. read this file first
2. read `10-XAU-M15-FAMILY-GOVERNANCE-RESULTS.md`
3. continue with the next unchecked item in the immediate execution order
4. update this file before claiming progress
5. commit coherent batches
