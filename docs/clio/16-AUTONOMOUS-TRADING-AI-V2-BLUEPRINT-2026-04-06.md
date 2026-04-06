# autonomous_trading_ai v2.0 Blueprint

Date: 2026-04-06
Owner: Clio Nova
Status: blueprint / not yet implemented

## Purpose

This document is the full blueprint for a future `autonomous_trading_ai v2.0`.

It is **not** a claim that v2 already exists.
It is a design target for how the system should evolve once the current Track D / M15 hardening wave has produced enough clarity.

The intent of v2 is not to throw away every useful part of the current system.
The intent is to keep what already works, while replacing the parts that are now clearly limiting:
- flat strategy generation
- overly binary early-stage filtering
- weak instrument-specific semantics
- insufficient learning from repeated failure signatures
- brittle promotion from research to live usage

---

## Executive summary

### Short version

v2.0 should become:

> a regime-aware, instrument-native, survival-focused specialist research and promotion engine

—not just a random-template generator with increasingly clever filters.

### Core thesis

The current system already proved a few important things:
- specialist strategies are the right direction
- family/stage observability is worth keeping
- symbol-aware tuning is necessary
- broad global loosening is usually the wrong move

But current evidence also shows that the engine still suffers from structural problems:
- too many candidates die immediately at cheap prescreen
- some symbols need fundamentally different semantics, not just different thresholds
- Monte Carlo gating can be too blunt when applied with insufficient context
- the system still learns too slowly from repeated failure patterns

So v2.0 should shift from:
- **generate many, kill many**

toward:
- **generate context-aware candidates, diagnose failures precisely, adapt priors from evidence, and promote only bounded specialists**

---

## Design goals

v2.0 should optimize for:

1. **Instrument-native behavior**
   - BTC, XAU, XAG, and future symbols should not be treated as the same species with different numbers.

2. **Earlier semantic validity**
   - invalid or contradictory strategies should die before expensive evaluation.

3. **Multi-stage viability diagnosis**
   - the system should know whether a candidate failed because it was contradictory, inactive, weak, fragile, or tail-risky.

4. **Evidence-weighted research memory**
   - repeated failures and repeated successes should influence future generation.

5. **Specialist-first promotion**
   - survival should not mean “universally good.”
   - survival should mean “credible in a bounded role.”

6. **Legible operator control**
   - the system should be inspectable, auditable, and difficult to fool with superficial pass-rate improvements.

7. **Conservative live deployment**
   - research should become richer and more adaptive without making live deployment looser or less safe.

---

## What v2 keeps from the current system

v2.0 should preserve these strong current ideas:

### 1. Specialist philosophy
The system should still prefer bounded specialists over fake universal strategies.

### 2. Family/stage observability
The Track D work proved that family-aware stage counts and failure summaries create real leverage.
This should remain a permanent subsystem.

### 3. Symbol-aware treatment
Recent XAU/XAG/BTC work showed clearly that symbol-level handling is mandatory.
That principle should be elevated from patch habit to architecture.

### 4. Research vs live separation
Current separation is imperfect but directionally correct.
v2 should strengthen it, not collapse it.

### 5. Documentation + audit discipline
The current docs/audit/checkpoint style is a real asset.
v2 should continue using dated audit docs, trackers, and coherent change batches.

---

## Main architectural shift

## From flat generation -> hierarchical generation

### Current problem
A lot of generation still effectively behaves like:
- pick a family
- sample parameters
- test it
- reject most of it

That wastes compute, floods cheap prescreen with obvious junk, and hides structural mismatch behind pass/fail aggregates.

### v2 model
Generation should become hierarchical:

1. **Market archetype layer**
   - trend continuation
   - pullback continuation
   - range mean reversion
   - compression -> expansion
   - session breakout
   - session continuation
   - volatile mixed regime

2. **Instrument profile layer**
   - BTC profile
   - XAU profile
   - XAG profile
   - future symbol profiles

3. **Playbook family layer**
   - e.g. `ma_trend`, `pullback_trend`, `rsi_range`, `session_breakout`, `compression_breakout`

4. **Parameter sampler layer**
   - thresholds
   - ATR/volatility gates
   - session windows
   - SL/TP / exit structure
   - time stop

5. **Repair / mutation layer**
   - only after the parent context is clear

### Why this matters
This means a strategy is born with a declared intended habitat.
It is not merely “a family with some numbers.”
It is:
- a breakout strategy
- for XAG
- under a certain volatility/session logic
- with a bounded intended role

That improves both generation quality and diagnostic clarity.

---

## Core v2 subsystems

## 1. Instrument Profile Registry

### Role
A dedicated registry that defines symbol-native research behavior.

### Each instrument profile should contain
- canonical symbol aliases
- session behavior assumptions
- volatility scale assumptions
- realistic holding-period expectations
- cost/slippage realism defaults
- preferred / discouraged playbook families
- family priors by timeframe
- Monte Carlo interpretation hints
- deployment temperament

### Example
#### BTC profile
- allows stronger trend/expansion playbooks
- expects fatter tails
- accepts some non-smooth equity if tail risk remains bounded
- may use conditional MC relief for specific proven families

#### XAU profile
- prefers London-centric and impulse/continuation logic
- requires tighter session discipline
- may tolerate lower family diversity if specialists are credible

#### XAG profile
- requires stricter semantic validation around session/breakout logic
- needs volatility thresholds scaled to actual XAG feature ranges
- should treat inactivity / 0-trade patterns as a top-priority defect class

### Benefit
This turns symbol-specific behavior from scattered patches into a first-class module.

---

## 2. Archetype + Playbook Registry

### Role
Explicitly define the market logic families the system is allowed to generate.

### Current issue
Parameter variation currently exceeds true playbook variation.

### v2 approach
Each playbook should have:
- intended market condition
- intended session behavior
- intended volatility environment
- expected holding style
- preferred exit archetypes
- valid symbols/timeframes
- anti-pattern constraints

### Example fields
- `playbook_type`
- `archetype`
- `valid_symbols`
- `preferred_sessions`
- `blocked_sessions`
- `volatility_shape`
- `entry_logic_class`
- `exit_logic_class`
- `time_horizon`
- `anti_patterns`

### Benefit
This gives generation a semantic contract before backtesting begins.

---

## 3. Multi-Stage Viability Pipeline

### Role
Replace the current overly binary early funnel with a staged diagnostic ladder.

### Proposed pipeline

#### Stage 0 — Semantic validity
Checks such as:
- contradictory rule combinations
- impossible or incoherent threshold combinations
- invalid family/instrument pairing
- unrealistic session constraints
- clearly malformed exit structure

Outputs:
- `invalid_semantics`
- `context_mismatch`
- `repairable_semantics`

#### Stage 1 — Activity viability
Checks such as:
- non-zero trade activity
- minimum plausible activity
- not pathologically rare
- not degenerate overtrade behavior

Outputs:
- `inactive_zero_trade`
- `inactive_low_trade`
- `degenerate_overtrade`
- `activity_viable`

#### Stage 2 — Basic quality sanity
Checks such as:
- PF floor
- Sharpe floor
- DD cap
- weak expectancy rejection

Outputs:
- `weak_perf`
- `high_dd`
- `quality_viable`

#### Stage 3 — Structural robustness
Checks such as:
- walk-forward behavior
- exit fragility
- hold-pattern sanity
- trade distribution sanity

Outputs:
- `wf_fail`
- `exit_fragile`
- `unstable_distribution`
- `robust_candidate`

#### Stage 4 — Tail-risk / scenario robustness
Checks such as:
- Monte Carlo loss tail
- loss probability
- DD stress
- scenario/regime stress where available

Outputs:
- `mc_tail_fail`
- `stress_fail`
- `tail_robust`

#### Stage 5 — Promotion readiness
Checks such as:
- specialist boundedness
- role clarity
- pool fit
- concentration fit
- live readiness

Outputs:
- `research_only`
- `candidate`
- `exploratory`
- `promotion_ready`

### Benefit
Now the system knows **where** and **why** a strategy dies.
That is much more useful than a single cheap-prescreen graveyard.

---

## 4. Research Memory 2.0

### Role
Turn repeated outcomes into adaptive future behavior.

### Current issue
The current system has memory-like behavior, but it still relies too much on manual interpretation and patching after repeated failure patterns.

### v2 memory layers

#### a. Failure memory
Store recurring bad signatures such as:
- symbol/family combinations with chronic `0 trades`
- parameter bands that repeatedly fail activity viability
- exit structures associated with catastrophic loss
- Monte Carlo failure signatures by symbol/family
- session constraints that chronically over-constrain a playbook

#### b. Success memory
Store recurring strong signatures such as:
- family/parameter bands with repeated robust survival
- symbol/session/regime combinations with credible edge
- durable exit patterns that survive friction and WF

#### c. Repair memory
Track whether prior repairs actually worked.
This prevents cycling through the same “fix” repeatedly.

#### d. Parent-selection memory
Use memory to bias lineage selection toward productive families and away from repeatedly toxic branches.

### Output behavior
Memory should influence:
- family weights
- parameter priors
- banned combinations
- repair suggestions
- promotion skepticism or confidence

### Guardrail
This should remain evidence-weighted and conservative, not become a self-justifying black box.

---

## 5. Promotion Ladder

### Role
Replace harsh binary survival with a structured maturity model.

### Proposed states
- `invalid`
- `inactive`
- `weak`
- `promising`
- `robust`
- `deployment_candidate`
- `live_incubation`
- `active_core`
- `degraded`
- `retired`

### Why this matters
A candidate that is not ready for live trading may still be useful:
- as a parent template
- as a family signal
- as a bounded exploratory candidate

That reduces wasted research signal.

---

## 6. Monte Carlo / Stress Layer v2

### Role
Make tail-risk evaluation smarter and more instrument-aware.

### Current issue
Some BTC candidates can look structurally decent through backtest + WF, yet fail MC under a too-blunt acceptance rule.
At the same time, broad loosening would be dangerous.

### v2 design
Use a tiered judgment model:

#### Tier A — strict baseline
Applies to all candidates by default.

#### Tier B — conditional relief
Allowed only when all are true:
- symbol/instrument profile explicitly permits it
- family is known and bounded
- backtest/WF quality is strong enough
- failure shape looks like a narrow tail issue, not broad structural weakness
- DD stress and loss probability remain bounded

#### Tier C — hard reject
Used when tails or stress patterns imply structural danger.

### Future extension
Add scenario-aware stress layers, not just generic sequence reshuffling:
- regime-cluster stress
- spread/slippage stress
- session-specific degradation stress
- event-like burst stress

### Benefit
Monte Carlo becomes a risk-classification layer, not just a single blunt gate.

---

## 7. Exit Engine v2

### Role
Make exit logic more explicit, inspectable, and robust.

### Current issue
Many strategies still appear too dependent on generic state-change exits.
That creates fragility and interpretability problems.

### v2 exit archetypes
- target-driven
- invalidation-driven
- session-end
- time-stop
- volatility-collapse exit
- hybrid bounded exits

### Each playbook should prefer certain exit classes
Example:
- breakout continuation -> target/invalidation/time-stop
- range mean reversion -> target + strict invalidation
- session breakout -> session-boundary aware exit discipline

### Benefit
Exit behavior becomes a first-class source of edge quality, not an afterthought.

---

## 8. Research World vs Live World

### Role
Strengthen the boundary between experimental research and real capital deployment.

### Research world
- high candidate throughput
- rich diagnosis
- aggressive rejection
- family/repair experimentation
- promotion labeling

### Live world
- only bounded specialists
- explicit role assignment
- concentration-aware deployment
- decays, degrade states, and retirement logic
- provenance and audit trail for every promoted strategy

### Deployment ladder
A strategy should not jump from “looks okay” to “core live” immediately.
Proposed path:
- robust candidate
- deployment candidate
- live incubation
- active core

### Benefit
Safer deployment and better trust in what is actually holding risk.

---

## 9. Observability and operator UX

### v2 should expose
- stage counts by symbol/timeframe/family
- top failure signatures
- family heatmaps
- promotion ladder counts
- live-vs-research drift
- family lineage and ancestry
- why a strategy was promoted, degraded, or retired

### Required artifacts
- per-symbol research summary
- per-family failure summary
- promotion ledger
- live incubation report
- degradation / retirement audit

### Benefit
Operator judgment becomes faster and less dependent on log archaeology.

---

## 10. Governance and safety boundaries

v2 should keep several hard principles:

1. do not loosen gates globally just to make the system look active
2. do not treat pass-rate increases as proof of improvement
3. do not collapse BTC/XAU/XAG into one generic logic stack
4. do not let AI/LLM judgment control live execution directly
5. do not let research convenience weaken live deployment conservatism
6. do not hide failure modes behind aggregate metrics only

---

## Proposed module layout

A possible v2-oriented layout:

- `profiles/`
  - instrument profiles
  - symbol aliases
  - volatility/session/cost assumptions

- `playbooks/`
  - archetype registry
  - family definitions
  - allowed contexts
  - preferred exits

- `research/generation/`
  - hierarchical candidate generation
  - mutation/repair logic

- `research/viability/`
  - semantic validity stage
  - activity stage
  - quality stage
  - robustness stage
  - stress stage

- `research/memory/`
  - failure memory
  - success memory
  - repair memory
  - lineage memory

- `research/promotion/`
  - promotion ladder
  - candidate classification
  - pool admission logic

- `execution/live/`
  - live routing
  - incubation handling
  - active-core promotion
  - degrade/retire logic

- `docs/clio/`
  - audit trail
  - migration notes
  - operator runbooks

This does not have to become the exact filesystem immediately, but it is the architectural direction.

---

## Symbol-specific v2 design notes

## BTC v2

### Intended identity
A directional / expansion-capable instrument with fatter tails and stronger need for tail-aware acceptance logic.

### Priorities
- preserve momentum/continuation strengths
- allow bounded conditional MC relief only when evidence justifies it
- improve tail classification rather than just trade-count gating
- keep lineage of BTC mixed-family survivors explicit

### Likely strong playbooks
- trend continuation
- pullback continuation
- compression -> expansion
- bounded mixed trend/range hybrids when empirically justified

---

## XAU v2

### Intended identity
A session-sensitive, specialist-heavy instrument where challenger refresh matters more than fake diversity.

### Priorities
- stronger London/session-native routing
- improve challenger refresh continuity
- maintain specialist discipline
- sharpen session and regime compatibility

### Likely strong playbooks
- impulse pullback
- session continuation
- controlled breakout continuation

---

## XAG v2

### Intended identity
A more fragile and semantically sensitive instrument where prior scale realism and session/activity semantics matter heavily.

### Priorities
- solve activity semantics first
- explicitly audit session context and regime availability
- keep volatility-scale assumptions realistic
- treat chronic 0-trade behavior as a design defect, not normal noise

### Likely strong playbooks
- lighter breakout forms
- carefully scoped session expansion
- selective compression->expansion variants

### Warning
XAG currently looks like the clearest case where parameter tweaking alone is not enough.
Its v2 path likely requires context-semantic repair, not only tighter priors.

---

## Migration strategy from current system

v2 should be built incrementally, not as a reckless rewrite.

## Phase 1 — Observability refactor

### Goal
Keep current engine, but improve diagnostic structure.

### Deliverables
- split cheap prescreen into sub-stages conceptually or in code
- richer failure taxonomy
- promotion ladder labels in research artifacts
- stronger per-family/per-symbol failure summaries

### Why first
This creates visibility before heavier architecture changes.

---

## Phase 2 — Instrument profile extraction

### Goal
Pull symbol-native behavior into explicit profile modules.

### Deliverables
- BTC/XAU/XAG profiles
- centralized volatility/session/cost assumptions
- profile-driven family compatibility rules

### Why second
This replaces scattered symbol patches with one coherent layer.

---

## Phase 3 — Playbook registry + hierarchical generation

### Goal
Refactor strategy birth process around archetype -> instrument -> family -> params.

### Deliverables
- explicit archetype registry
- family contracts
- hierarchical candidate generator
- semantic validity stage

---

## Phase 4 — Research memory 2.0

### Goal
Use repeated outcomes to adapt future search.

### Deliverables
- failure memory
- success memory
- repair memory
- adaptive family weighting

---

## Phase 5 — Monte Carlo / stress redesign

### Goal
Replace blunt tail gating with tiered and profile-aware logic.

### Deliverables
- strict baseline
- conditional relief framework
- hard reject framework
- optional scenario-aware stress extensions

---

## Phase 6 — Promotion ladder + incubation lane

### Goal
Create a disciplined bridge from research to live.

### Deliverables
- promotion state machine
- incubation inventory
- better provenance
- stronger degrade/retire audits

---

## Success criteria for v2

v2 should only be called successful when most of these become true:

1. cheap-prescreen failures become more informative and less mass-opaque
2. BTC/XAU/XAG each behave like intentionally different research tracks
3. repeated chronic failure signatures automatically influence future generation
4. research output contains meaningful maturity states, not just pass/fail
5. Monte Carlo decisions become more context-aware without becoming looser by default
6. live promotion becomes slower, more legible, and more trustworthy
7. operator understanding improves without needing deep log spelunking

---

## Anti-goals

v2 is **not** trying to:
- maximize candidate count for its own sake
- maximize trade count for optics
- replace rule logic with black-box ML first
- push the system toward over-automation without evidence
- weaken live risk controls in order to show activity
- pretend all symbols should converge to the same architecture

---

## Recommended first blueprint follow-up docs

If this blueprint is accepted, the best companion docs would be:

1. **v2 migration tasklist**
   - explicit tasks / phases / checkboxes

2. **instrument profiles spec**
   - what a BTC/XAU/XAG profile must contain

3. **promotion ladder spec**
   - exact states and transitions

4. **viability taxonomy spec**
   - exact failure classes / stage labels / artifact schema

5. **research memory spec**
   - what gets remembered, how long, and how it affects sampling

---

## Final judgment

The current system is still worth continuing.
It has real strengths and recent work materially improved observability, symbol-awareness, and targeted hardening.

But the current evidence also says clearly:
- further progress will become slower and uglier if the system stays patch-first forever
- the next real jump in quality likely requires architectural re-foundation, not just more family-level tuning

That is what this v2.0 blueprint is for.
