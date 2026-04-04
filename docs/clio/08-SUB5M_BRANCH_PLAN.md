# Sub-5m Branch Plan – autonomous_trading_ai

## Purpose

This document defines the intended design direction for the new branch focused on
**sub-5-minute trading research**.

Scope includes:

- `M5` as the practical first step
- `M1` as the harder next layer
- later **tick-aware realism research** if the earlier stages justify it

This document exists to keep the branch disciplined.

It is **not** a permission slip to turn the system into a lottery bot.

---

## Core Position

The sub-5m branch should remain aligned with the project’s main design truth:

> Build a portfolio of **specialist strategies** that are strong in specific
> contexts, then use a disciplined routing/governance layer to deploy them only
> where they actually have edge.

That principle does **not** change just because the timeframe is lower.

If anything, it matters **more** below `M5`, because microstructure noise,
slippage, and spread make false edge much easier to hallucinate.

---

## What This Branch Is Not

This branch is **not** intended to be:

- a “$10 → $10,000” lottery-ticket architecture
- a near-certain-ruin compounding experiment by default
- a justification for disabling all risk controls
- a generic one-model-fits-all scalper
- a shortcut around realism, fill quality, and execution friction

We may allow **more aggressive** profiles than the main M15 path, but not a
system whose default philosophy is deliberate self-destruction.

---

## Branch Objective

The real objective is:

1. determine whether the current specialist architecture can survive below `M5`
2. determine whether any **cost-adjusted** edge remains after harsher realism
3. determine what must change in generation, routing, and governance to support
   ultra-short-hold specialists

Success is **not** measured by fantasy compounding claims.

Success is measured by:

- some specialists surviving harsher realism filters
- out-of-sample stability not collapsing immediately
- live probation not failing instantly
- edge surviving after pessimistic spread/slippage assumptions

---

## Design Principles For Sub-5m

### 1. Aggressive is allowed; sloppy is not

Sub-5m can be more aggressive than the current M15 branch.

But that should mean:

- faster turnover
- tighter stop/exit logic
- narrower specialist deployment
- more selective no-trade zones

It should **not** mean:

- turning off drawdown brakes casually
- 20%+ risk-per-trade as the default starting point
- letting compounding logic run ahead of validated edge

### 2. Realism must get harsher as timeframe gets lower

For `M5`, `M1`, and later tick-aware research, the system should become **more**
realism-sensitive, not less.

That means stronger attention to:

- spread pessimism
- slippage stress
- same-bar ambiguity / fill ambiguity
- latency sensitivity
- market-state clustering
- session-specific microstructure

### 3. Specialist philosophy still applies

The target remains:

- specialist for a session
- specialist for a micro-regime
- specialist for a narrow volatility context
- specialist with clear no-trade zones

We are **not** trying to build a heroic generalist that somehow survives all
sub-5m market states.

### 4. No-trade behavior becomes even more important

At lower timeframes, a large fraction of bars should probably be ignored.

If the branch trades too often just because bars arrive faster, that is a sign
of weak governance, not strength.

---

## Recommended Scope Progression

## Phase 0 – Branch Charter / Constraints

Before heavy code changes, keep the branch anchored with the following rules:

- start with **one symbol only** (`XAUUSDm` unless evidence later says otherwise)
- keep position count at **1**
- keep the branch focused on **research + realism first**, not live heroics
- do not disable risk controls globally by default
- do not describe speculative compounding scenarios as engineering goals

Deliverable:

- this design memo exists and is referenced by future branch work

---

## Phase 1 – M5 Baseline First

### Why start with M5

`M5` is the most sensible bridge layer between the existing `M15` branch and
true scalping.

Benefits:

- still fast enough to expose lower-timeframe fragility
- not as brutally noisy as `M1`
- easier to evaluate than tick-first research
- closer to the architecture that already exists

### Design goals for M5

- one symbol (`XAUUSDm`)
- one position max
- faster-hold specialist families
- explicit time-stop support
- harsher spread/slippage assumptions than M15
- stronger Monte Carlo and OOS pressure than the main branch

### Candidate family ideas

Examples:

- pullback continuation after local expansion
- short-horizon breakout continuation
- volatility compression → expansion
- bounded snapback / RSI reversion with session restriction
- short-duration MA / trend-strength impulse specialists

### Exit posture

At `M5`, exits should already bias toward:

- hard time-stop availability
- clean invalidation logic
- fewer vague state-flip exits
- lower tolerance for long hold drift

Deliverable:

- first credible `M5` baseline branch configuration and research loop

---

## Phase 2 – M1 Specialist Layer

Only move here after `M5` proves that the architecture still behaves sanely.

### What changes at M1

- spread/ATR ratio becomes much more dangerous
- slippage hurts much more
- timing noise is higher
- false backtest edge becomes easier to manufacture

### Required design differences for M1

- mandatory or near-mandatory time-stop support
- stricter hold-time expectations
- stronger no-trade filters
- more pessimistic cost assumptions
- even more explicit session restrictions
- stronger live probation before any meaningful risk sizing

### What should *not* happen

Do **not** assume that because the timeframe is smaller, risk-per-trade should
suddenly jump to reckless levels.

Any aggressive sizing should come **after** evidence, not before it.

Deliverable:

- M1-specific research config + generator families + realism policy

---

## Phase 3 – Tick-Aware Realism Research

This is a later stage, not the first move.

Potential research here:

- tick replay audits for selected strategies
- fill quality estimation
- spread-spike stress
- event microstructure diagnostics
- latency sensitivity checks

This phase is primarily about **truth-finding**, not immediate live deployment.

Deliverable:

- supporting tools that tell us whether M1 backtest assumptions are lying

---

## Risk Posture Recommendation

## Default branch posture (recommended)

For the sub-5m branch, a sane starting profile is still bounded.

Suggested initial shape:

- `max_open_positions = 1`
- `daily_limits_enabled = True`
- meaningful daily drawdown cap remains enabled
- meaningful portfolio drawdown cap remains enabled
- initial risk-per-trade should stay in an **experimental but survivable** band

The point is to learn fast **without** defaulting to immediate blow-up.

## What to avoid as the default

Avoid making these the baseline branch identity:

- “never stop” portfolio settings
- effectively disabled daily limits
- 20–25% per-trade default sizing
- branch philosophy built around near-certain ruin

Those may exist later as a **separate explicitly high-risk profile**, but they
should not define the branch itself.

---

## Research / Backtest Requirements

Sub-5m work should demand stronger realism checks than the M15 branch.

Minimum expectations:

- more pessimistic spread assumptions
- more pessimistic slippage assumptions
- same-bar ambiguity awareness remains visible
- Monte Carlo should continue evolving toward scenario-aware stress
- walk-forward pressure should remain meaningful
- post-cost survivability matters more than raw pre-cost return

Important rule:

A strategy that looks amazing before realistic friction but collapses after cost
stress should be treated as **non-viable**, not “promising.”

---

## Generator / Strategy Design Guidance

The branch likely needs distinct lower-timeframe playbook families.

Expected characteristics:

- short hold times
- clear invalidation
- explicit time-stop options
- tighter regime/session restrictions
- avoidance of heavy indicator soup
- market-logic-first design rather than random signal stacking

Possible tags worth promoting:

- `intended_hold_bars`
- `intended_session`
- `micro_volatility_preference`
- `scalp_style`
- `requires_time_stop`

These should help keep lower-timeframe specialists legible and governed.

---

## Governance Changes Likely Needed

Compared with M15, sub-5m work likely needs:

- stricter no-trade defaults
- stronger cost-aware acceptance pressure
- tighter monitoring of degradation after fewer trades
- explicit microstructure warnings in research outputs
- more conservative trust before promotion to `active`

The branch should prefer:

- smaller but more believable pools

over:

- large pools full of noisy apparent edge

---

## What Carries Over From M15

These ideas should remain central:

- specialist over generalist
- eligibility before ranking
- explicit routing metadata
- live decay / degradation governance
- concentration control
- Monte Carlo / walk-forward robustness checks
- no-trade as a valid outcome

So this branch is an **extension** of the main philosophy, not a rejection of it.

---

## What Must Change From M15

The following areas likely need deliberate branch-specific logic:

- timeframe-specific cost assumptions
- lower-timeframe generator families
- faster hold-time expectations
- stronger realism assumptions
- more restrictive session/micro-context rules
- more cautious interpretation of apparent edge

---

## Anti-Patterns To Avoid In This Branch

Do not:

- chase fantasy compounding narratives as engineering requirements
- disable risk brakes just because the branch is “aggressive”
- treat M1 backtest profits as trustworthy without harsher realism checks
- assume Kelly-style sizing is safe before edge is proven live
- force the branch into high trade count just because bars arrive faster
- reward noisy pseudo-generalists over bounded specialists

---

## Immediate Recommended Next Steps

1. create branch-specific roadmap/config notes for `M5` first
2. define sub-5m risk profile defaults conservatively
3. add lower-timeframe playbook family plan
4. add harsher cost/realism assumptions for branch research
5. only after that begin code changes

That order matters.

The branch should begin with **clarity**, not adrenaline.

---

## Relationship To Existing Docs

Use alongside:

- `03-DEVELOPMENT_PLAN.md`
- `06-M15_IMPROVEMENT_ROADMAP.md`
- `07-ROUTING_LAYER_AUDIT_AND_TASKLIST.md`

This file is the dedicated branch memo for the lower-timeframe path.

---

## Changelog (Docs)

- 2026-04-04: Added dedicated sub-5m branch plan to guide M5/M1/tick-aware work toward disciplined specialist scalping rather than lottery-mode risk design.
