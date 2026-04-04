# XAU M15 Acceptance Gate Trace – Actual Repo Findings + Family-Aware Governance Implementation

## Scope

This document records the deeper technical trace performed after the prior strategic memo for:
- project: `autonomous_trading_ai`
- branch/context: `aggressive`
- focus: `XAUUSDm M15`

It includes:
1. actual findings from repo/data inspection
2. diagnosis updates versus the earlier hypothesis
3. implemented changes for **Family-aware governance**

---

## What the deeper trace found

## 1. The current generated population is not the same as the earlier challenger snapshot

A fresh repo/data trace on `strategies/generated` showed:
- `XAUUSDm_M15` generated files currently present: **8872**
- visible family counts from filenames:
  - `core15`: **8338**
  - `ichifib`: **534**
  - `ma_trend`: **0**
  - `compression_breakout`: **0**
  - `pullback_trend`: **0**
  - `session_breakout`: **0**
  - `vol_breakout`: **0**
  - `rsi_range`: **0**

### Interpretation
This means the current on-disk generated population has already drifted from the earlier broader challenger-family snapshot.

So there are now **two truths**:
- historically / earlier snapshot: challenger families existed visibly
- current trace: on-disk XAU M15 generation is now overwhelmingly `core15`, with some `ichifib`

This materially strengthens the incumbent-lock-in hypothesis.

---

## 2. `pool_state.json` for `XAUUSDm M15` is still fully concentrated in one visible family bucket

Direct trace of `strategies/pool_state.json` shows for `XAUUSDm M15`:
- total records traced: **673**
- visible family distribution from persisted stats: **unknown: 673**

However, sample persisted records reveal strategy payloads like:
- name: `core15_XAUUSDm_M15_02f5`
- params include:
  - `long_family: rsi_range`
  - `short_family: ma_trend`
  - `regime_type: mixed`

### Interpretation
The pool was not actually semantically familyless.
It was suffering from a **family extraction / labeling collapse**:
- family-aware tools were reading only `family` / `playbook_type`
- many `core15` records instead encode structure via:
  - `long_family`
  - `short_family`
- therefore the runtime/index/pool view flattened meaningful diversity into `unknown`

This is important:

> The system had more structural diversity than the audit surface was showing,
> but the governance layer was failing to represent it correctly.

That means one part of the earlier “core15 monoculture” diagnosis was real,
but another part was amplified by **metadata collapse**.

---

## 3. Parent-selection + generation path still appears incumbent-heavy

In `scheduler/main.py`, the research loop:
- scores existing pool parents
- takes the top ~20 parent records
- uses them as seed inputs for `evolve_population(...)`

Combined with the current pool concentration, this creates a strong feedback loop:
- incumbent-heavy pool
- incumbent-heavy parents
- incumbent-heavy next population
- incumbent-heavy future pool

This is a classic ecological lock-in mechanism.

---

## 4. Acceptance gates are globally strong before any family-sensitive protection exists

Current research path enforces multiple hard gates before persistence:
- cheap prescreen
- minimum trades
- weak PF / Sharpe rejection
- WF rejection
- Monte Carlo rejection
- exit-signature rejection
- specialist/routing thresholds for `active` / `exploratory`

This confirms the earlier strategic view:
- challengers can die at many stages before durability
- the old system did not explicitly carve out protected room for challengers in `XAUUSDm M15`

---

## 5. `_should_promote()` was not the main current bottleneck surface

A direct search for `_should_promote` in `scheduler/main.py` did not reveal the expected helper in the current path.

Instead, the practical promotion logic for research persistence is happening inline through:
- hard gate rejects
- status assignment to `active` / `exploratory` / `disabled`
- `pool.upsert_strategy(...)`
- family-aware inactive pruning in `pool.prune(...)`

So the real leverage point is not a single promotion helper, but the combined flow of:
- parent ecology
- gate thresholds
- status assignment
- family extraction correctness
- prune survival

---

## Diagnosis update after deeper trace

## Updated conclusion

The stronger, more precise diagnosis now is:

> `XAUUSDm M15` has both a real incumbent-bias problem **and** a family-representation problem.

### The incumbent-bias side
- parent selection is fed by the current pool
- current generation is dominated by `core15`
- research acceptance remains globally strict
- challengers were not granted explicit protected lanes

### The family-representation side
- structural family information was often stored in `long_family` / `short_family`
- but several governance surfaces were collapsing those to `unknown`
- this made the ecosystem look even flatter than it really was

So the earlier “core15 monoculture” diagnosis was directionally right,
but needed refinement:

> It is partly a true ecology problem, and partly an observability/governance-labeling problem.

---

## Implemented changes – Family-aware governance

The following changes have now been implemented.

## 1. Family extraction now understands mixed-family strategies better

Updated in:
- `strategies/pool.py`

### New behavior
Family extraction now:
- prefers `family` / `playbook_type` if present
- otherwise derives from `long_family` / `short_family`
- emits mixed labels such as:
  - `mixed:ma_trend+rsi_range`

### Why this matters
This prevents meaningful structural diversity from being flattened into `unknown`.

That improves:
- pool pruning awareness
- future family mix analysis
- governance observability

---

## 2. Research dead-zone penalty is now less hostile to challengers

Updated in:
- `scheduler/main.py`

### New behavior
- family resolution now uses mixed-family-aware extraction
- challenger families receive a reduced dead-zone penalty multiplier

### Why this matters
Previously, challenger families could be penalized too heavily simply because nearby memory neighborhoods were weak or incumbent-dominated.

Now the penalty is still present, but less likely to suffocate challengers before they accumulate enough signal.

---

## 3. Research family mix logging is now more truthful

Updated in:
- `scheduler/main.py`

### New behavior
Family mix logs now use mixed-family-aware extraction instead of naïvely reading only `params["family"]`.

### Why this matters
This gives a more honest view of what evolution is actually producing.

---

## 4. Family-aware acceptance easing for challengers was added

Updated in:
- `scheduler/main.py`

### New challenger behavior
For recognized challenger families, the system now allows somewhat softer research gates:

- lower base research minimum trades for challengers
- lower PF threshold for challenger survival
- lower Sharpe threshold for challenger survival
- lower WF threshold for challenger survival
- softer path into `exploratory` status

### Why this matters
This does **not** remove discipline.
It simply stops judging every bounded specialist as if it must already look like a mature incumbent.

---

## 5. Challenger-slot bootstrap was added

Updated in:
- `scheduler/main.py`

### New behavior
After research evaluation, before prune:
- top XAU M15 challenger candidates can be marked protected
- if challenger exploratory coverage is below target, the scheduler can promote eligible challenger candidates into `exploratory`
- promotion reason is stored in stats metadata

Key config values added:
- `CHALLENGER_EXPLORATORY_MIN_SLOTS = 2`
- `CHALLENGER_CANDIDATE_MIN_SLOTS = 2`

### Why this matters
This creates the first explicit **challenger lane** inside the governance flow.

That directly addresses the earlier diagnosis that challengers lacked a realistic path into durable pool presence.

---

## What this implementation does **not** claim yet

This implementation does **not** prove that challenger families now outperform incumbents.

It only does the following:
- makes family identity more truthful
- reduces accidental metadata collapse
- softens anti-challenger friction
- creates explicit exploratory room for challengers

That is the correct first step.

The next step is evidence collection.

---

## Remaining high-value technical work

## 1. Build actual gate-failure tables
Still needed:
- sample challenger and incumbent records
- count failures by stage
- verify whether challengers mostly die in:
  - trade count
  - PF / Sharpe
  - WF
  - MC
  - status assignment
  - prune

---

## 2. Rebuild and inspect runtime artifacts after the new family extraction
Still needed:
- regenerate pool/runtime outputs through the normal research path
- inspect whether `strategy_index.json` and manifest now show meaningful family buckets instead of broad `unknown`

---

## 3. Add explicit family governance reporting
Useful next:
- family mix before/after each research cycle
- challenger promotions granted by bootstrap lane
- challenger survival rate through prune
- family concentration warnings for `XAUUSDm M15`

---

## 4. Consider parent-selection diversification
Likely next major leverage point:
- diversify parent selection itself
- avoid feeding evolution only with top incumbent-heavy pool records
- add a family-aware parent sampler for XAU M15

This may matter almost as much as acceptance reform.

---

## Current strategic reading after implementation

The system has now moved one step away from:
- accidental incumbent preservation
- poor family observability

and one step toward:
- explicit family-aware governance
- challenger bootstrap capacity
- more truthful ecosystem measurement

That is the correct direction.

But the job is not done until the next research cycles confirm that:
- challenger families actually survive
- family distribution becomes more legible
- pool composition becomes less path-dependent

---

## Recommended next action

Next best step:
- run the research cycle under the updated governance
- inspect resulting `pool_state.json`, `strategy_index.json`, and generated family mix
- produce a compact **before vs after** audit

Suggested next companion doc:
- `10-XAU-M15-FAMILY-GOVERNANCE-RESULTS.md`

That should report:
- family mix before patch
- family mix after patch
- challenger accepted/promoted counts
- whether XAU M15 pool becomes more diverse in practice
