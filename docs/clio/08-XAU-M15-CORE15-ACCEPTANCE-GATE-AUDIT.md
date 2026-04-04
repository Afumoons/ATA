# XAU M15 `core15` Acceptance Gate Audit – Strategic + Technical Memo

## Purpose

This memo captures the current audit conclusion for `autonomous_trading_ai` on:
- branch/context: `aggressive`
- symbol: `XAUUSDm`
- timeframe: `M15`

It combines:
1. **strategic interpretation** of the current pool structure
2. **technical audit framing** for the next deep trace

The goal is to preserve the current reasoning chain so it is not lost across session interruption, channel disconnects, or context resets.

---

## Executive conclusion

Current evidence indicates that for `XAUUSDm M15` the problem is **not** simply that challenger families are absent or intrinsically poor.

The sharper conclusion is:

> New families are being generated, but they are not entering the final pool.
> Therefore the key bottleneck is likely in the **acceptance / promotion / persistence path**, not in generation alone.

At the moment, `pool_state.json` for `XAUUSDm M15` remains heavily dominated by `core15`, while newly generated challenger families do not appear in the persisted pool.

This strongly suggests one or more of the following:
- acceptance pressure is too severe before persistence
- promotion logic is too conservative for challengers
- pruning/incumbency dynamics preserve legacy `core15` dominance
- branch ecology has become structurally biased toward incumbent continuation

---

## Snapshot of the observed pattern

### Generated family presence exists
Observed generated families for `XAUUSDm M15` included:
- `ma_trend`
- `vol_breakout`
- `pullback_trend`
- `rsi_range`
- `session_breakout`
- `compression_breakout`
- many `unknown` entries

### Persisted pool remains `core15`-dominated
In `pool_state.json` for `XAUUSDm M15`, the visible family structure is:
- `core15`: dominant
- challenger families: effectively absent

### Interpretation
This means challenger families are:
- not merely losing rank inside an already-diverse pool
- but rather **failing to become part of the persisted ecosystem at all**

That is a materially different diagnosis.

---

## Strategic interpretation

## 1. The current issue is probably not “lack of ideas”

The system is already producing challenger hypotheses. The issue is not simply low idea generation throughput.

If multiple named families are generated but none survive into the pool, then the system’s limiting factor is more likely:
- candidate filtration
- specialist acceptance thresholds
- promotion logic
- pool replacement dynamics

rather than creative search alone.

---

## 2. `core15` dominance may represent structural incumbent lock-in

The strongest strategic hypothesis right now is:

> `XAUUSDm M15` in the current `aggressive` branch behaves like a legacy-heavy ecosystem where incumbents have a substantial survival advantage over challengers.

This can happen even if challengers are directionally promising.

Possible mechanisms:
- incumbents are used as parent anchors more often
- incumbents already occupy most survivable pool slots
- prune logic protects existing family concentration indirectly
- challenger families are forced to beat mature incumbents by too large a margin before receiving a durable slot

This is classic **incumbent lock-in** behavior.

---

## 3. Acceptance pressure may be overly harsh for specialists

A second major hypothesis is that quality gates are currently too hard for narrower specialist families.

Potential examples:
- minimum trade count too high for legitimate niche specialists
- walk-forward thresholds too strict for regime/session specialists
- Monte Carlo requirements penalize narrower but still valid playbooks
- acceptance logic implicitly rewards broader-average profiles over bounded specialists

If so, the system may be unintentionally selecting for:
- incumbent continuity
- generalist-like robustness signatures
- already-known family structures

while rejecting strategically useful specialists before they can accumulate evidence.

---

## 4. This is likely a governance problem as much as a generation problem

The framing should shift from:

> “Why don’t new families work?”

To:

> “Why are new families not getting accepted, promoted, and retained into the pool?”

That is the more operationally correct question.

---

## Strategic implications

If the diagnosis above is confirmed, then the best next interventions are **not** simply:
- generate more families
- widen random search
- run more of the same evolution cycles

Instead, the likely high-value intervention areas are:

### A. Acceptance-gate reform
Examples:
- review `EXEC_MIN_TRADES`
- review specialist-specific minimum evidence logic
- soften thresholds for bounded specialists without opening the floodgates to noise

### B. Challenger bootstrap lane
Examples:
- reserve exploratory slots for non-incumbent families
- enforce minimum family diversity in exploratory pool
- require challenger exposure before full rejection

### C. Promotion / pruning reform
Examples:
- reduce incumbent protection effects
- prevent a single family from saturating the pool ecosystem
- give challengers a minimum survival window before prune-out

### D. Family-aware governance
Examples:
- governance based on strategic role, not only raw global score
- specialist judged as specialist, not as failed generalist

---

## Technical hypothesis tree

The current likely failure zones are:

1. **cheap prescreen / early evaluation**
   - challengers die before expensive evaluation

2. **walk-forward**
   - challengers fail robustness gates more often than `core15`

3. **Monte Carlo**
   - challengers fail sequence-fragility / DD stability tests

4. **accepted flag / final evaluation outcome**
   - challengers reach evaluation but are explicitly rejected

5. **promotion / status assignment**
   - challengers may be accepted but not promoted into `candidate`, `exploratory`, or `active`

6. **pool persistence / merge / prune logic**
   - challengers may briefly qualify but fail to survive merge/prune steps

7. **incumbent-biased orchestration effects**
   - parent selection and branch ecology keep regenerating/refining `core15` dominance

---

## Technical audit objective

The next audit should answer a narrow question with hard evidence:

> At which exact stage do challenger families die relative to `core15` on `XAUUSDm M15`?

This should be done as a **comparative gate-failure audit**, not as a generic code skim.

---

## Proposed technical audit design

### 1. Sample both incumbents and challengers

Build a comparison set such as:
- `core15`: 10–20 examples
- `ma_trend`: 10–20 examples
- `compression_breakout`: 10–20 examples
- `pullback_trend`: 10–20 examples
- `session_breakout`: 10–20 examples
- `vol_breakout`: 10–20 examples

Where possible, prefer the same symbol/timeframe context:
- `XAUUSDm`
- `M15`

---

### 2. For each sampled strategy, trace these fields

For each strategy record or evaluation artifact, capture:
- family
- symbol
- timeframe
- trade count
- PF / Sharpe / DD
- walk-forward metrics
- Monte Carlo metrics
- accepted flag
- final status (`candidate` / `exploratory` / `active` / dropped)
- whether it was written to pool state
- whether it was later pruned

Goal:
- produce a stage-by-stage failure distribution by family

---

### 3. Compare family-level death zones

Target output format:
- `ma_trend`: mostly dies at min trades
- `compression_breakout`: mostly dies at WF Sharpe
- `session_breakout`: reaches accepted but dies at promotion
- `vol_breakout`: reaches exploratory then gets pruned
- `core15`: survives across all gates with much higher persistence rate

This is the evidence needed to separate:
- threshold issue
- promotion issue
- prune issue
- ecosystem lock-in issue

---

## Code-path audit priority

The most suspicious areas to inspect next are:

- `scheduler/main.py`
  - candidate bootstrap logic
  - cheap prescreen
  - evaluation orchestration
  - acceptance / promotion flow
  - status assignment

- promotion-related helpers such as:
  - `_should_promote()`
  - related score / governance checks

- pool merge / retention logic
  - persistence path
  - family extraction path
  - prune behavior

- pruning settings and dynamics
  - e.g. `pool.prune(max_inactive=200, min_family_keep=8)`

The key question for code review is not merely “what thresholds exist?” but:

> Which thresholds and structural rules disproportionately preserve `core15` incumbency while starving challenger persistence?

---

## Working diagnosis ranking

Current ranked hypotheses:

### Hypothesis 1 — Structural incumbent lock-in
**Confidence: high**

Evidence:
- generated families exist
- pool remains `core15`-concentrated
- challenger absence is systematic, not anecdotal

### Hypothesis 2 — Specialist acceptance pressure too hard
**Confidence: medium-high**

Evidence:
- likely narrow specialists are being generated
- no non-`core15` family breaks through into persistent pool structure

### Hypothesis 3 — Promotion/prune path is challenger-hostile
**Confidence: medium-high**

Evidence:
- plausible if some challengers are acceptable but never durable
- consistent with legacy-heavy branch ecology

### Hypothesis 4 — Family metadata labeling is the main root cause
**Confidence: lower than above, but still relevant historically**

Reason:
- `unknown` generated population is notable
- but even clearly named challenger families are also absent from the pool
- therefore labeling alone does not explain the full pattern

---

## Recommended next decision path

If the Acceptance Gate Audit confirms most challengers die **before accepted**, prioritize:
- threshold / specialist-governance reform

If challengers are accepted but not promoted/persisted, prioritize:
- promotion + pool persistence + prune reform

If challengers briefly enter but disappear rapidly, prioritize:
- anti-monoculture pool governance
- challenger survival window
- family diversity preservation

---

## Practical design direction if confirmed

If current diagnosis holds, the strategic direction should be:

> Move from incumbent-heavy pool preservation toward a more deliberate specialist-governance model for `XAUUSDm M15`.

That likely means some combination of:
- explicit challenger lanes
- diversity-aware exploratory governance
- specialist-aware acceptance rules
- less accidental dependence on legacy `core15`

The objective is **not** to weaken standards recklessly.
The objective is to ensure valid challenger specialists receive a real path to prove themselves.

---

## Documentation intent

This memo is intentionally written as both:
- a strategic checkpoint
- a handoff note for the next deeper technical trace

It should be treated as the preserved reasoning baseline for the next audit pass.

---

## Suggested follow-up artifact

After the next deeper repo trace, create a companion file such as:
- `09-XAU-M15-ACCEPTANCE-GATE-TRACE.md`

with concrete evidence tables:
- sampled strategies
- gate-failure counts
- exact code-path findings
- recommended code changes ranked by expected impact
