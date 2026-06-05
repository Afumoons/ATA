# DEVELOPMENT_PLAN.md – autonomous_trading_ai

## Purpose

This document is the high-level development roadmap for the project.

It should answer:

- what has already been implemented
- what pass 3 changed materially
- what the next meaningful improvement areas are
- how future dev work should remain disciplined

For the most current tactical roadmap focused on the live `XAUUSDm M15`
home-field setup, see:

- `06-M15_IMPROVEMENT_ROADMAP.md`
- `07-ROUTING_LAYER_AUDIT_AND_TASKLIST.md`

For the future-state architectural redesign target, see:

- `16-AUTONOMOUS-TRADING-AI-V2-BLUEPRINT-2026-04-06.md`

Treat this file as the **broad roadmap / status ledger**, not the detailed
implementation checklist.

## Development Principles

1. **Safety before ambition**
   - never weaken hard risk controls casually
   - no forced trading just to make the system look active

2. **Specialists over fake universality**
   - prefer credible bounded-role strategies over weak generalists

3. **Eligibility before ranking**
   - live routing should block bad-fit specialists before score comparison

4. **Small coherent changes**
   - changes should be scoped, tested, documented, and committed

5. **Code-doc-runbook alignment**
   - if behavior changes, docs and instructions should change too

## Phase Status Snapshot

### Phase 1 – Exploratory strategy tier + risk tiers

**Status:** implemented

Outcome:

- strategy pool supports `exploratory`
- live execution distinguishes `active` vs `exploratory`
- exploratory exposure is intentionally lower risk

### Phase 2 – Regime-aware live selection

**Status:** implemented and later strengthened

Outcome:

- live selection uses regime-specific edge
- selection became more context-sensitive
- this phase laid the groundwork for the later routing-layer hardening

### Phase 3 – Generator improvements / practical strategy quality

**Status:** implemented

Outcome:

- generator biases toward more practical interpretable templates
- ATR-based SL/TP support exists
- strategy-family metadata is richer
- the pool receives better candidate inputs than earlier versions

### Phase 4 – Memory-guided governance

**Status:** baseline implemented

Outcome:

- research memory is used for soft bonuses/penalties in parent selection
- obviously bad candidate families can be vetoed early
- stored research results now help steer future search, conservatively

## Pass 3 Outcome Summary

Pass 3 is less about adding a single feature and more about maturing the system
into a stronger **specialist-routing architecture**.

Key pass 3 outcomes:

- explicit routing metadata persisted in `strategy_explain.meta`
- session hard gates in live execution
- structured regime-aware routing using richer feature context
- active + exploratory orchestration made more coherent
- explicit “no eligible specialist” outcomes
- specialist-aware promotion logic
- stricter and more legible live state / monitoring artifacts
- broad documentation refresh across root/module/runbook files

## What Is Still Missing / Next Priority Areas

The project is stronger after pass 3, but still has meaningful next-step work.

### 1. M15 hardening continuation

Most immediate work should continue to focus on:

- tighter specialist governance
- sharper session discipline
- stricter execution-quality thresholds
- better backtest realism and diagnostics

This is covered in:

- `06-M15_IMPROVEMENT_ROADMAP.md`

### 2. Exit-quality improvement

A lot of strategies still rely heavily on state-change exits.

Future work should improve:

- exit archetypes
- exit diagnostics
- holding-period interpretability
- fragility detection

### 3. Playbook diversity

The generator is better than before, but still risks generating many close cousins.

Future work should aim for:

- broader playbook families
- clearer intended-market-condition tagging
- less false diversity from near-duplicates

### 4. Live-vs-backtest governance refinement

The degradation loop exists, and the system now also has proactive live decay detection plus concentration controls, but future work can still improve:

- anomaly detection for live outperformers / underperformers
- clearer operator surfacing of unusual live behavior
- stronger distinction between noise and structural change
- better escalation from warning -> degrade -> stronger operator action

### 5. Portfolio intelligence

Still relatively weak compared with the per-strategy/per-symbol pipeline.

Longer-term opportunities include:

- correlation-aware allocation
- portfolio-level backtesting
- clustered exposure control
- smarter capital allocation across specialists

## Recommended Development Order From Here

1. continue M15 hardening work
2. improve exit design and diagnostics
3. improve candidate diversity and playbook tagging
4. strengthen live-feedback interpretation
5. only then consider bigger ML / portfolio intelligence work

## Stage 1 Adaptive ML Shadow Development Tasklist

Stage 1 remains **shadow-only**: it may train models, journal predictions, and label outcomes, but it must not place, modify, or size live trades.

- [x] Safe ML config defaults: disabled by default, `stage = shadow`, explicit stage validation, conservative risk multipliers.
- [x] Feature/label dataset foundation: parquet feature loading, numeric feature inference, future-return labels, train/validation/test split checks.
- [x] Shadow model registry foundation: atomic registry, shadow status bucket, no champion promotion path in Stage 1 training.
- [x] Shadow prediction journal foundation: prediction records include no-trade gate fields and dedupe by symbol/timeframe/model/bar.
- [x] Small batch 2026-06-05: outcome-label records now retain prediction lineage (`symbol`, `timeframe`, `model_id`, `bar_time`, `horizon_bars`, `predicted_action`, `confidence`) so later evaluation can audit every shadow label back to the original prediction.
- [x] Small batch 2026-06-05: aggregate shadow evaluation report from prediction + outcome journals, including overall/model/symbol-timeframe accuracy, pending coverage, quality score, and safety warning if any journal record shows `trade_taken = true`.
- [ ] Add operator-facing runbook commands for safe dry-run/train/predict/label/evaluate cycles.
- [ ] Add scheduler integration for shadow predict/label only after dry-run evidence is stable.

## Dev Workflow Requirements

Any future development run should still follow this loop:

1. inspect current plan / roadmap docs
2. select one small coherent change batch
3. implement conservatively
4. run basic verification/tests
5. update docs if behavior changed
6. commit with a clear message

## Anti-Patterns To Avoid

Do not:

- relax thresholds just to increase trade count
- describe roadmap ideas as already implemented
- broaden scope into many brokers/platforms without finishing current MT5 path
- let documentation drift from real files and behavior
- replace hard risk logic with vague AI judgment

## Changelog (Docs)

- 2026-06-05: Added Stage 1 aggregate shadow evaluation report and CLI output path for prediction/outcome journal review.
- 2026-06-05: Added Stage 1 adaptive ML shadow tasklist and checked off the outcome-label lineage batch.
- 2026-04-04: Updated the broad plan to acknowledge post-audit hardening already completed (live decay detection, concentration control) and narrow remaining priorities more honestly.
- 2026-03-27: Reframed the development plan around implemented phase status, pass 3 outcomes, and next-priority work after specialist-routing hardening.