# Routing Layer Audit & Implementation Tasklist – autonomous_trading_ai

## Purpose

This document translates the current routing-layer audit into an implementation-oriented plan.

It is the technical companion to:
- `06-M15_IMPROVEMENT_ROADMAP.md`

Use this file when the goal is to evolve the current system from:
- **score-driven selector with some regime/session awareness**

toward:
- **policy-driven specialist router**

---

## Audit Summary

## Current state in one sentence

The current architecture already contains the foundations of a specialist-routing system, but the routing behavior is still mostly **implicit, score-driven, and coarse** rather than **explicit, policy-driven, and context-disciplined**.

---

## What already works

### 1. Regime-aware filtering already exists

Current code already does all of the following:
- Reads the current regime from the latest feature row.
- Uses `strategy_explain.regime_pnl` to compute a regime-specific edge.
- Filters `active` and `exploratory` strategies by regime edge.
- Applies different risk tiers for `active` vs `exploratory`.

Implication:
- The system is not blind to regime.
- The base specialist-routing idea already exists.

### 2. Session-aware influence already exists

Current code also:
- derives current session (`asia`, `london`, `new_york`),
- computes a hybrid execution score using:
  - walk-forward Sharpe,
  - regime-specific return,
  - session-specific return.

Implication:
- The system already acknowledges that session matters.
- But session is currently used more as a **soft ranking input** than a hard routing policy.

### 3. Strategy explainability already contains useful routing metadata

`backtests/explain.py` already produces:
- `regime_pnl`
- `session_pnl`
- `best_regime`
- `worst_regime`
- `is_trend_follower`
- `is_range_trader`
- risk/stability/news behavior

Implication:
- Much of the raw information needed for a specialist router is already available.
- The problem is more about orchestration than total lack of data.

---

## Main technical gaps

### 1. Routing intent is still implicit, not explicit

Current problem:
- Strategies are routed based on inferred stats at selection time.
- There is no explicit policy layer saying:
  - which regimes a strategy is allowed to trade,
  - which sessions it is allowed to trade,
  - which contexts should block it.

Why it matters:
- A strategy can be a valid specialist, but the system has no durable contract describing its intended deployment zone.

Desired direction:
- Add explicit routing metadata / policy fields, such as:
  - `best_regime`
  - `worst_regime`
  - `allowed_regimes`
  - `blocked_regimes`
  - `best_session`
  - `allowed_sessions`
  - `blocked_sessions`
  - `volatility_preference`
  - `routing_confidence`

---

### 2. Regime mapping is too coarse for specialist deployment

Current problem:
- `high_vol` / `low_vol` are flattened too aggressively.
- `execution/signals.py` still relies on a legacy mapping where:
  - `high_vol` and `low_vol` are effectively treated like `ranging` for routing fallback.

Why it matters:
- This throws away specialist context.
- A high-volatility trend specialist and a quiet range specialist are not equivalent.

Desired direction:
- Use richer routing inputs from structured regime output:
  - `regime_class`
  - `regime_type`
  - `regime_confidence`
  - volatility bucket

---

### 3. Session handling is still mostly soft ranking, not hard gating

Current problem:
- Session performance influences ranking, but does not strongly enforce:
  - only trade in London,
  - avoid New York,
  - block Asia, etc.

Why it matters:
- A specialist strategy can still bleed in the wrong session even if the score system "knows" that session is weaker.

Desired direction:
- Session should be able to become a first-class eligibility gate.
- Strategies should support optional hard deployment rules by session.

---

### 4. Scheduler routing and execution routing are not fully consistent

Current problem:
- `job_execute_signals()` initially builds its execution pool from `active` strategies only.
- `execute_signals_for_symbol()` supports both `active` and `exploratory`.
- In practice, the scheduler-level orchestration can prevent exploratory specialists from even reaching the downstream router.

Why it matters:
- This creates an architecture mismatch.
- It weakens the intended specialist portfolio model.

Desired direction:
- Use a consistent orchestration model for both `active` and `exploratory`.
- Keep risk tiers different, but let the routing layer see both tiers coherently.

---

### 5. Quality gates are global, not specialist-aware

Current problem:
- Execution pool quality gates are strong, but global:
  - minimum WF Sharpe,
  - maximum drawdown,
  - minimum trade count,
  - max consecutive losses.

Why it matters:
- Specialist strategies can be valid with narrower participation profiles.
- Some may naturally have lower trade counts but still be useful in a bounded role.

Desired direction:
- Keep anti-noise discipline.
- But adjust selection/governance so specialists are judged as specialists, not forced into semi-generalist criteria.

---

### 6. “No valid specialist => no trade” is not yet a first-class policy

Current problem:
- There are several skip conditions today (news lockout, daily limits, no edge, no entry), which is good.
- But there is no explicit policy layer for:
  - weak routing confidence,
  - session mismatch,
  - volatility mismatch,
  - insufficient specialist eligibility.

Desired direction:
- Make flat/no-trade behavior an explicit success mode.
- In ambiguous conditions, the router should prefer inaction.

---

## Target design

The intended architecture should evolve toward this model:

```text
[Feature + Regime Context]
        ↓
[Specialist Eligibility Layer]
  - allowed regime?
  - allowed session?
  - volatility fit?
  - confidence high enough?
        ↓
[Rank eligible specialists]
        ↓
[Risk tier application]
  - active risk
  - exploratory risk
        ↓
[Execution]
```

Key principle:
- **Eligibility first, ranking second.**
- A specialist should not merely receive a lower score outside its zone.
- It should often be **ineligible** outside its zone.

---

## Implementation Tasklist

## Phase A1 – Add explicit routing metadata

### Goal
Make routing intent durable and machine-readable.

### Files to review/update
- `backtests/explain.py`
- `scheduler/main.py`
- `strategies/pool.py`
- optionally strategy JSON/stats persistence paths

### Tasks
- [ ] Extend `strategy_explain.meta` with clearer routing fields:
  - [ ] `best_session`
  - [ ] `worst_session`
  - [ ] `allowed_regimes` (derived, heuristic v1)
  - [ ] `blocked_regimes` (derived, heuristic v1)
  - [ ] `allowed_sessions` (derived, heuristic v1)
  - [ ] `blocked_sessions` (derived, heuristic v1)
  - [ ] `routing_confidence`
- [ ] Define simple heuristic rules for v1 derivation, for example:
  - [ ] best regime/session must be meaningfully positive,
  - [ ] blocked regime/session when return is materially negative,
  - [ ] confidence based on trade count + edge separation.
- [ ] Persist these fields into pool stats so the router can consume them directly.

### Output
- Strategies carry explicit routing hints, not just raw PnL tables.

---

## Phase A2 – Make session a first-class routing gate

### Goal
Allow strategies to be hard-blocked outside their intended session.

### Files to review/update
- `scheduler/main.py`
- `execution/signals.py`
- `backtests/explain.py`

### Tasks
- [ ] Add a session eligibility helper used during live routing.
- [ ] Enforce optional hard session gate before ranking/execution.
- [ ] Start with conservative rules, for example:
  - [ ] if `blocked_sessions` contains current session → reject
  - [ ] if `allowed_sessions` exists and current session not in it → reject
- [ ] Log session-based rejections clearly.

### Output
- Session stops being only a soft bonus and becomes optional hard deployment policy.

---

## Phase A3 – Upgrade regime routing to use structured context

### Goal
Stop flattening important context too early.

### Files to review/update
- `research/regime.py`
- `execution/signals.py`
- `scheduler/main.py`

### Tasks
- [ ] Audit which structured regime columns are already available in saved features.
- [ ] Update live routing to consume:
  - [ ] `regime_class`
  - [ ] `regime_type`
  - [ ] `regime_confidence`
  - [ ] `vol_regime`
- [ ] Replace or reduce the coarse fallback where `high_vol` / `low_vol` route as `ranging`.
- [ ] Add confidence-aware eligibility rules.

### Output
- Specialist deployment reflects richer market context.

---

## Phase A4 – Unify active + exploratory orchestration

### Goal
Make the routing path consistent across both live tiers.

### Files to review/update
- `scheduler/main.py`
- `execution/signals.py`

### Tasks
- [ ] Include both `active` and `exploratory` in scheduler-level routing pool construction.
- [ ] Apply the same eligibility logic to both.
- [ ] Preserve different risk tiers after routing passes.
- [ ] Review deduplication behavior so cross-tier clones do not create weird routing artifacts.

### Output
- A coherent specialist portfolio view reaches the router.

---

## Phase A5 – Add explicit “no valid specialist => no trade” policy

### Goal
Make inaction a first-class routing outcome.

### Files to review/update
- `execution/signals.py`
- `scheduler/main.py`
- logs / runbook docs if needed

### Tasks
- [ ] Introduce a clear eligibility summary structure, such as:
  - [ ] blocked by session mismatch
  - [ ] blocked by regime mismatch
  - [ ] blocked by low routing confidence
  - [ ] blocked by volatility mismatch
- [ ] If no eligible specialists survive, exit cleanly and log why.
- [ ] Distinguish “no entry signal” from “no eligible specialist”.

### Output
- The system explicitly knows when flat is the correct action.

---

## Phase A6 – Revisit promotion logic for specialist acceptance

### Goal
Stop implicitly favoring semi-generalists over valid specialists.

### Files to review/update
- `scheduler/main.py`
- possibly `backtests/evaluation.py`

### Tasks
- [ ] Review `_should_promote()` logic under the specialist design philosophy.
- [ ] Reduce accidental bias toward broad-average behavior.
- [ ] Define what makes a specialist eligible for:
  - [ ] `active`
  - [ ] `exploratory`
  - [ ] `candidate`
- [ ] Prefer bounded-role credibility over generic broadness.

### Output
- Promotion rules better match the intended architecture.

---

## Phase A7 – Revisit execution quality gates for specialist-awareness

### Goal
Keep anti-noise discipline without wrongly filtering useful specialists.

### Files to review/update
- `scheduler/main.py`
- maybe docs after tuning

### Tasks
- [ ] Audit current thresholds:
  - [ ] WF Sharpe
  - [ ] max drawdown
  - [ ] min trades
  - [ ] max consecutive losses
- [ ] Decide which thresholds should remain global vs which should become specialist-aware.
- [ ] Keep this conservative; avoid loosening gates blindly.

### Output
- Quality filters stay hard, but become more aligned with specialist deployment.

---

## Recommended order of work

1. **A1 – Add explicit routing metadata**
2. **A2 – Session hard gate**
3. **A3 – Structured regime routing**
4. **A4 – Unify active + exploratory orchestration**
5. **A5 – Explicit no-trade policy**
6. **A6 – Specialist-aware promotion logic**
7. **A7 – Specialist-aware quality-gate review**

Reason:
- Metadata and eligibility must come before more tuning.
- First make routing legible, then make it stricter, then tune acceptance.

---

## Suggested success checks

Use these as validation targets after implementation:

- [ ] Logs clearly show why a strategy was eligible or rejected.
- [ ] Session-specialist strategies stop trading in known bad sessions.
- [ ] High-vol conditions no longer collapse into overly generic routing.
- [ ] Exploratory specialists can participate in routing coherently.
- [ ] “No valid specialist” appears as a normal, explainable outcome.
- [ ] Pool statuses reflect specialist quality, not broadness bias.

---

## Changelog (Docs)

- 2026-03-26: Added routing-layer audit summary and Phase A specialist-router implementation tasklist.