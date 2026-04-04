# Improvement Opportunities – autonomous_trading_ai

## Purpose

This file is a parking lot for **future opportunities**, not the canonical
near-term execution plan.

For current tactical work, prefer:

- `06-M15_IMPROVEMENT_ROADMAP.md`
- `07-ROUTING_LAYER_AUDIT_AND_TASKLIST.md`

Use this document to capture ideas that may be valuable later once the current
MT5 + M15 + specialist-routing stack is stable.

## Principles For This File

- ideas here are **not automatically approved work**
- implemented items should be marked clearly
- speculative ideas should not be described as current architecture
- prefer concise opportunity framing over essay-length speculation

## Opportunity Areas

### 1. Stronger daily/live accounting analytics

Some of this is already implemented:

- closed-deal wiring into daily state
- per-strategy live PnL aggregation
- degradation based on live stats

Future expansion ideas:

- richer attribution by session/regime/news window
- better anomaly flags for live-vs-backtest drift
- cleaner operator summaries for live state transitions
- better operator framing of live decay warning/degrade outcomes

### 2. AI-assisted research tooling

The current project already supports offline AI-assisted review through exports
and research memory.

Future improvements could include:

- compact automated pool-review reports
- AI-generated R&D notes from top/bottom strategy clusters
- guided suggestions for generator-family expansion

Constraint:

- keep it offline/supportive
- do not make live execution depend on LLM judgment

### 3. ML / meta-model overlays

Not current core architecture, but a future avenue:

- meta-rankers for candidate filtering
- lightweight predictive overlays on rule-based strategies
- anomaly/drift detectors
- online adaptation helpers

This should come **after** current routing/governance and execution realism are stronger.

### 4. Session-aware governance refinement

Session hard gates now exist.

Future improvements could include:

- richer session-confidence metrics
- better session-specialist tagging in research outputs
- tighter London/NY differentiation for XAUUSDm M15

### 5. Exit-quality and holding-period diagnostics

Important future area because many weak strategies reveal themselves through
fragile exits rather than obviously bad entries.

Potential work:

- clearer exit archetypes
- time-stop variants
- better holding-period metrics
- penalties for overly fragile exit signatures

### 6. Structured-regime expansion

Structured regime fields are now live in the feature pipeline and routing path.

Future work could extend this further by:

- exposing richer regime hints downstream
- allowing more strategy rules to reference structured regime context
- improving playbook tagging around volatility/event-driven states

### 7. Risk-profile abstraction

A future improvement could be a higher-level risk-profile system that maps to:

- per-trade risk cap
- portfolio DD limit
- daily drawdown / trade caps

This should remain conservative and explicit.

### 8. Live-performance anomaly surfacing

Useful future area:

- detect strategies that materially underperform or outperform their backtests
- mark them for research review
- avoid automatic overreaction while still surfacing signal

### 9. Portfolio intelligence

Still a meaningful longer-term gap.

Potential work:

- clustered exposure control beyond the current light concentration caps
- capital weighting/allocation layer
- portfolio-level simulation
- correlation-aware strategy selection

### 10. Execution robustness / infrastructure hardening

Potential work:

- stronger reconnect behavior
- richer execution error classification
- spread spike / abnormal condition guards
- better data-quality checks before decisions

## Opportunity Prioritization Guidance

If choosing what to pursue next, prefer this order:

1. M15 hardening and specialist governance
2. exit-quality / backtest realism improvements
3. playbook diversity improvements
4. live-performance anomaly tooling
5. portfolio intelligence
6. heavier ML/AI additions

## Changelog (Docs)

- 2026-04-04: Updated opportunity framing to acknowledge live decay governance and current light concentration control as already implemented baselines.
- 2026-03-27: Reframed this file as a future-opportunities parking lot after pass 3, reduced mismatch with current architecture, and clarified priority ordering.