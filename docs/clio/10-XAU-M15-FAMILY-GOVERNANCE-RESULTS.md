# XAU/XAG Family Governance Results – After-Run Audit

## Scope

This document captures the after-run audit following the first research cycle executed with the new Family-aware governance patch.

Focus:
- `XAUUSDm M15`
- `XAGUSDm M15`

Questions answered:
1. Did the new governance patch reopen generation diversity?
2. Did that diversity survive into pool/index artifacts?
3. Is the current dominant bottleneck governance or quality?

---

## Executive verdict

## Short answer

### For `XAUUSDm M15`
- **Generation bottleneck:** improved materially
- **Governance bottleneck:** reduced, but not fully manifested in persisted pool this cycle
- **Quality bottleneck:** currently dominant in the observed challenger batch

### For `XAGUSDm M15`
- **Generation bottleneck:** not the main issue
- **Governance bottleneck:** not yet the main issue
- **Quality bottleneck:** dominant and earlier than XAU — challengers died in cheap prescreen

---

## Most important conclusion

The first patched run strongly suggests:

> The old system really did have a governance / representation problem.
> But once the lane was reopened, the next visible bottleneck became strategy quality.

In practical terms:
- the patch succeeded in restoring family diversity at the generation layer
- but the generated challengers in this run mostly did not produce sufficient backtest quality to survive into the persisted pool

So the bottleneck has shifted from:
- **"they cannot get in"**

toward:
- **"many of the new entrants still are not good enough yet"**

---

## Before vs after: key observations

## 1. Persisted XAU pool/index did not change yet

After the run, the persisted artifacts for `XAUUSDm M15` remained:
- index entries: **673**
- visible family in index: **unknown: 673**
- pool entries: **673**
- pool statuses:
  - `exploratory`: 374
  - `active`: 213
  - `disabled`: 65
  - `candidate`: 21
- governance markers observed in pool:
  - `family_governance_protected`: 0
  - `family_governance_promoted`: 0

### Interpretation
This means that in this first patched cycle:
- the governance patch reopened the front door
- but no challenger batch achieved enough viability to alter persisted XAU pool composition yet

So **pool persistence did not improve because candidate quality was still too weak**.

---

## 2. Generation diversity improved dramatically

### XAU generated family mix (`XAUUSDc M15` files on disk)
Observed generated family counts:
- `ma_trend`: 304
- `compression_breakout`: 303
- `pullback_trend`: 300
- `rsi_range`: 300
- `session_breakout`: 297
- `vol_breakout`: 294
- `xau_impulse_pullback`: 156
- `xau_session_continuation`: 156

Total observed generated files: **2110**

### XAG generated family mix (`XAGUSDc M15` files on disk)
Observed generated family counts:
- `xau_session_continuation`: 220
- `pullback_trend`: 208
- `compression_breakout`: 204
- `vol_breakout`: 204
- `xau_impulse_pullback`: 196
- `ma_trend`: 194
- `rsi_range`: 190
- `session_breakout`: 181

Total observed generated files: **1597**

### Interpretation
This is decisive evidence that:
- the patched system is **no longer generation-monoculture-bound**
- family-aware governance successfully restored multi-family generation flow

So **generation diversity is no longer the main bottleneck**.

---

## 3. XAU: challengers were generated, but the sample quality was weak

During the live run, sample XAU challenger backtests showed patterns such as:
- `ma_trend`: one case with `-100%`, another with `0 trades`
- `rsi_range`: roughly `-97%` to `-99%`
- `pullback_trend`: deeply negative or too few trades
- `vol_breakout`: `0 trades`
- `compression_breakout`: `0 trades`
- `session_breakout`: `0 trades`
- `xau_impulse_pullback`: `0 trades`
- `xau_session_continuation`: `0 trades`

At the same time, even several fresh `core15` samples also looked poor:
- negative returns
- weak Sharpe
- non-trivial drawdowns

### Interpretation
This matters because it narrows the diagnosis:
- the issue is not simply “challengers are blocked while incumbents are healthy”
- rather, this run showed **a broad quality weakness in the sampled population**

However, challengers were still weaker in aggregate for actual promotion pressure.

So for XAU:
- governance bottleneck was real historically
- but in this run the active bottleneck was **quality / viability**

---

## 4. XAG: all tested challengers died at cheap prescreen

Run summary for `XAGUSDm M15` ended with:
- `Research skip summary for XAGUSDm M15: counts={'cheap_prescreen': 20}`

### Interpretation
This is a very clean signal.
For the observed XAG batch:
- challengers did not even reach later governance/promotion conflict
- they died at the earliest practical quality gate

That means for XAG, **the current bottleneck is clearly quality-first**, not governance-first.

---

## Bottleneck classification

## XAUUSDm M15

### Governance bottleneck status
**Historically real, but now partially relieved**

Evidence:
- new family generation clearly reopened
- mixed-family handling improved
- challenger lane exists in code

### Quality bottleneck status
**Currently dominant in the first patched run**

Evidence:
- challengers were generated
- challengers mostly failed to show acceptable viability in observed backtests
- no persisted challenger protection/promotion marker ended up materializing in pool

### Final XAU verdict
> XAU is no longer blocked mainly by lack of generation diversity.
> It is now blocked mainly by insufficient challenger quality in the current sampled batch.

Governance still matters, but it is no longer the only or primary active explanation after this run.

---

## XAGUSDm M15

### Governance bottleneck status
**Not the main active bottleneck in this run**

Evidence:
- family generation diversity exists
- candidates never made it past cheap prescreen

### Quality bottleneck status
**Overwhelmingly dominant**

Evidence:
- all 20 observed XAG research attempts were cut at cheap prescreen

### Final XAG verdict
> XAG is presently a pure quality / strategy-construction problem before it is a governance problem.

---

## Strategic interpretation

The family-aware governance patch did its first job correctly:
- restore diversity
- restore visibility
- reopen challenger entry lanes

But it also revealed the next truth:

> Once the access problem is reduced, the system immediately exposes whether the actual generated strategy families are robust enough.

And in this first run:
- many were not

This is good news in one sense:
- the ambiguity is lower now
- the system is now telling a cleaner truth

---

## What the patch succeeded at

The patch **did succeed** at:
- reopening multi-family generation
- making challenger families appear in live research flow
- reducing family-representation collapse
- making the audit surface more honest

The patch **did not yet** succeed at:
- producing challenger persistence in the pool
- changing XAU pool composition in one cycle
- rescuing weak candidate batches from poor actual trading quality

That is not failure.
That is an honest first-pass result.

---

## Recommended next focus

## 1. Shift from governance-only tuning toward family quality tuning

For now, the highest-value work is likely:
- improve candidate construction for challenger families
- reduce obvious zero-trade and catastrophic-loss patterns
- tune archetype parameter ranges by family

Examples:
- better threshold priors for `ma_trend`
- stricter sanity rules for `rsi_range`
- breakout family conditions that do not collapse into zero-trade behavior

---

## 2. Add stage-count reporting by family

Next instrumentation should explicitly log for each family:
- generated count
- cheap prescreen pass count
- backtest pass count
- WF pass count
- MC pass count
- accepted count
- candidate/exploratory/active count

This would make bottleneck diagnosis nearly automatic.

---

## 3. Improve XAG/XAU family templates separately

Do not assume XAU and XAG should share the same family priors.

Current evidence suggests:
- XAU may still support some specialist paths if better parameterized
- XAG currently needs more basic viability tuning before governance matters much

---

## 4. Keep family-aware governance in place

Do **not** revert the governance patch.

Reason:
- it solved a real observability/access issue
- it gave us much better diagnostic truth
- reverting it would return the system to ambiguity and monoculture bias

---

## Final verdict

### If the question is:
> Which bottleneck is more important right now — governance or quality?

### Answer:

#### For XAU M15:
- **Historically:** governance + representation mattered a lot
- **Right now after patch:** **quality is the stronger immediate bottleneck**

#### For XAG M15:
- **Right now:** **quality is overwhelmingly the bottleneck**

### One-line synthesis

> The patch proved the door was partly locked before.
> After unlocking it, we discovered many challengers still cannot walk through on merit yet.
