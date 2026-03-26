# M15 Improvement Roadmap – autonomous_trading_ai

## Purpose

This document captures the current assessment of the system's **largest M15 bottlenecks** and turns them into a practical improvement roadmap.

Scope:
- Focus on the **current home-field configuration**: primarily `XAUUSDm` on `M15`.
- Improve **robustness, selection quality, and execution realism** before expanding to lower timeframes.
- Keep risk controls conservative.

Out of scope for this roadmap:
- Migrating the system to `M5` / `M1`.
- Major ML-first redesign.
- Relaxing risk limits to force more trades.

---

## Current M15 Assessment

### What is working

- The architecture is already strong enough to support:
  - data ingestion,
  - feature computation,
  - regime detection,
  - strategy generation/evolution,
  - backtesting,
  - risk-aware execution,
  - live monitoring,
  - research memory.
- The system is already **most aligned with M15**, both in configuration and in the current strategy pool.
- The strongest live/research candidates are currently concentrated around `XAUUSDm M15`.

### Core conclusion

The system does **not** primarily suffer from a lack of strategies.

The main issue is:

> The current M15 system still lacks **robust edge across regimes and sessions**.

In practice, many strategies appear good only under a subset of conditions (often specific regimes or sessions), and the current pipeline still lets too many fragile or thin-edge strategies survive into the pool.

---

## Biggest M15 Bottlenecks

### 1. Regime robustness is still weak

Observed pattern:
- Many strategies are strongest in `trending_down`.
- Several degrade badly in `high_vol` and some `ranging` conditions.
- Some strategies are only attractive because one regime dominates the sample.

Why this matters:
- This creates conditional profitability rather than broad resilience.
- Live performance can degrade quickly when market structure rotates.

Interpretation:
- The system currently finds **regime-local edges** more easily than **regime-robust edges**.

---

### 2. Session asymmetry is too large

Observed pattern from strategy explanations:
- Many promising M15 strategies are strong in **London**.
- Several leak PnL in **New York**.
- Asia performance is mixed and often lower conviction.

Why this matters:
- A strategy can look acceptable in aggregate while actually being carried by one session and damaged by another.
- If the live system trades all sessions too freely, the weak sessions can erase the strong-session edge.

Interpretation:
- The system likely has **session-specific edge**, but the current controls do not exploit that hard enough.

---

### 3. Live regime selection is still coarser than research context

Observed pattern:
- `research/regime.py` supports richer regime structure.
- `execution/signals.py` still consumes a simpler legacy regime label path for live filtering.
- `high_vol` / `low_vol` handling remains relatively blunt in live selection.

Why this matters:
- Research context is richer than live decision context.
- Good regime information is being compressed too early.

Interpretation:
- The system is leaving useful context on the table during live filtering.

---

### 4. Backtest realism is acceptable for screening, but still not strong enough for high-confidence production claims

Observed pattern:
- The backtest engine is still fundamentally bar-based.
- Entry/exit assumptions remain simplified.
- A large share of exits comes from `exit_rule`, not clean TP hits.
- Many strategy explanations show `avg_holding_bars = 0.0`, which weakens interpretability and confidence.

Why this matters:
- M15 tolerates simplification better than M5/M1, but realism still matters.
- Thin edges can disappear live if cost/friction assumptions are not strict enough.

Interpretation:
- The current backtester is good enough for discovery, but not yet strict enough to confidently separate mediocre from production-grade M15 strategies.

---

### 5. Strategy family diversity is still too narrow

Observed pattern:
- Core generation is now intentionally biased toward simpler MA/RSI/ATR structures.
- This is cleaner than heavy indicator soup, but also means many strategies are still close cousins of each other.

Why this matters:
- A larger pool does not automatically mean a wider hypothesis space.
- Evolution can become parameter-tuning over similar ideas rather than discovery of genuinely different playbooks.

Interpretation:
- The system currently has more **parameter variation** than **playbook diversity**.

---

### 6. Acceptance pressure is still too permissive for thin-edge strategies

Observed pattern:
- Many strategies in the pool still cluster around modest profit factor / moderate instability.
- Some accepted exploratory strategies are useful for learning, but others may simply add noise.

Why this matters:
- Thin-edge strategies can consume execution bandwidth, risk budget, and operator attention.
- They also pollute the evolutionary pool and make the system feel “busy” instead of selective.

Interpretation:
- Pool governance still needs to become more brutal, especially for M15 production focus.

---

### 7. Exit behavior is not yet expressive enough

Observed pattern:
- In many strategies, `exit_rule_ratio` dominates and `tp_hit_ratio` is small.
- This suggests many strategies are effectively exiting because the state changed, not because the move completed cleanly.

Why this matters:
- Exit logic becomes more sensitive to small timing drift.
- Live-vs-backtest mismatch risk increases.
- It becomes harder to classify whether the strategy is truly trend-following, mean-reverting, or just condition-chasing.

Interpretation:
- Exit design is a meaningful source of fragility and should be treated as a first-class research target.

---

## Priority Roadmap

## Phase A – Tighten M15 selection quality (highest priority)

### Goal
Reduce fragile strategies in the pool and make the live set more selective.

### Actions

1. **Raise acceptance pressure for M15-focused promotion**
   - Keep `exploratory` for learning, but make `active` significantly harder to reach.
   - Tighten standards around:
     - walk-forward quality,
     - session leakage,
     - regime concentration,
     - drawdown asymmetry,
     - expectancy after costs.

2. **Add explicit penalties for regime imbalance**
   - Penalize strategies that are heavily dependent on a single regime while materially negative elsewhere.
   - Example:
     - a strategy that is strong only in `trending_down` but sharply negative in `high_vol` should be capped at `exploratory` unless filters isolate its trade context.

3. **Add explicit penalties for session leakage**
   - Penalize strategies with one strong session and one deeply negative session.
   - Make this part of evaluation, not just interpretation.

### Deliverable
- Fewer but stronger `active` strategies.
- Cleaner distinction between:
  - `active` = robust enough for normal risk,
  - `exploratory` = interesting but conditional,
  - `candidate/disabled` = not ready.

---

## Phase B – Make live trading more session-aware

### Goal
Stop allowing weak sessions to dilute strong-session edge.

### Actions

1. **Promote session-aware gating into live selection**
   - Use `strategy_explain.session_pnl` more directly.
   - Let strategies trade only in sessions where they have demonstrated acceptable edge.

2. **Add session eligibility metadata to strategy governance**
   - Example fields:
     - `preferred_sessions`
     - `blocked_sessions`
     - `session_confidence`

3. **Prefer London-first discipline for XAUUSDm M15**
   - Since multiple pool examples show stronger London performance, treat London as the primary high-confidence session until evidence says otherwise.

### Deliverable
- Session-aware live execution.
- Lower session-based PnL leakage.
- Clearer relationship between research findings and live deployment windows.

---

## Phase C – Upgrade regime-aware live filtering from “good enough” to “sharp”

### Goal
Bring live decision quality closer to the richness of the research layer.

### Actions

1. **Use more of the structured regime output in live selection**
   - Move beyond the legacy `regime` label when practical.
   - Incorporate:
     - `regime_class`,
     - `regime_type`,
     - `regime_confidence`,
     - volatility context.

2. **Separate high-vol handling from generic ranging fallback**
   - Avoid flattening `high_vol` too aggressively into simple fallback logic.
   - Treat volatile trend and volatile non-trend contexts differently.

3. **Apply confidence-aware throttling**
   - If regime confidence is weak, either:
     - reduce execution aggressiveness,
     - or require stronger strategy edge to trade.

### Deliverable
- A live layer that uses regime context more precisely.
- Lower mismatch between research richness and execution logic.

---

## Phase D – Improve backtest realism for M15 validation

### Goal
Make M15 research more trustworthy without over-engineering toward sub-minute simulation.

### Actions

1. **Audit cost model inputs used in practice**
   - Verify actual spread, slippage, and commission assumptions match the broker/live environment closely enough.
   - Prefer slightly pessimistic assumptions over optimistic ones.

2. **Improve interpretability of holding-period behavior**
   - Fix or validate why `avg_holding_bars` is frequently `0.0`.
   - Ensure trade duration and bar-hold metrics are accurately reported.

3. **Strengthen exit-path realism checks**
   - Review stop/TP/exit-rule priority behavior for edge cases.
   - Add sanity checks for strategies whose profit comes almost entirely from exit-rule behavior.

4. **Add stricter “after-cost survivability” review**
   - Strategy should remain clearly acceptable after realistic friction.
   - Marginal PF strategies should be deprioritized or discarded.

### Deliverable
- Better separation between discoverable ideas and deployable ideas.
- Higher confidence that M15 backtest winners can survive live friction.

---

## Phase E – Expand playbook diversity without adding indicator soup

### Goal
Increase hypothesis diversity while preserving interpretability.

### Actions

1. **Add more distinct M15 playbook families**
   - Examples:
     - trend continuation after pullback,
     - session breakout continuation,
     - volatility compression → expansion,
     - controlled mean reversion with hard session restrictions.

2. **Avoid reintroducing heavy indicator mixes by default**
   - Keep the “simple but expressive” philosophy.
   - Diversity should come from market logic, not indicator count inflation.

3. **Tag playbooks more explicitly**
   - Example fields:
     - `playbook_type`
     - `primary_market_condition`
     - `intended_session`

### Deliverable
- Broader search space.
- Less false diversity from near-duplicate strategies.

---

## Phase F – Improve exit design and exit diagnostics

### Goal
Reduce fragility caused by overly generic exit-rule behavior.

### Actions

1. **Classify exit styles explicitly**
   - Distinguish:
     - target-driven exits,
     - state-change exits,
     - protective exits,
     - time-based exits.

2. **Penalize over-fragile exit signatures**
   - If a strategy relies almost entirely on condition flip exits without robust post-cost performance, score it down.

3. **Experiment with a small number of clearer exit archetypes**
   - Example:
     - ATR target + trend invalidation,
     - session-end exit,
     - time-stop after N bars.

### Deliverable
- Strategies that are easier to reason about and less sensitive to small timing noise.

---

## Recommended Execution Order

If improvements must be done in 80/20 order, do them in this sequence:

1. **Phase A – Tighten M15 selection quality**
2. **Phase B – Session-aware live filtering**
3. **Phase C – Sharpen regime-aware live filtering**
4. **Phase D – Improve backtest realism / reporting**
5. **Phase E – Expand playbook diversity**
6. **Phase F – Improve exit design**

Reason:
- Better filtering and governance will likely create more impact, faster, than adding more strategy templates immediately.
- The system first needs to become more selective before it becomes more expansive.

---

## Suggested Documentation Cleanup

Based on the current docs set, this roadmap suggests the following documentation adjustments:

### Add
- This file as the dedicated M15-focused roadmap.

### Update
- `03-DEVELOPMENT_PLAN.md`
  - Keep it as the broad multi-phase historical roadmap.
  - Add a note pointing to this file as the current **M15 production hardening roadmap**.

- `04-IMPROVEMENT_OPPORTUNITIES.md`
  - Keep it as a parking lot for future ideas.
  - Remove ambiguity by pointing M15-specific near-term work to this file instead of mixing it into generic wishlists.

- `01-OVERVIEW.md`
  - Tighten the “scope” language so it reflects the actual codebase more honestly (currently the repo is MT5-centric and currently M15/XAU-oriented, not yet a broad Binance/Bybit/Exness production stack).

- `02-ARCHITECTURE.md`
  - Tighten the architecture description so it reflects the current implementation rather than a generic conceptual trading platform.

### De-emphasize / keep as historical scratch
- `scratch/dev_notes/*`
  - Keep for implementation history and fine-grained notes.
  - Do not treat them as the canonical current roadmap for M15 hardening.

---

## Success Criteria

This roadmap is succeeding when:

- The active M15 pool becomes smaller but stronger.
- London/NY session leakage is materially reduced.
- Fewer strategies are accepted on thin edge.
- Live strategy selection uses regime/session context more precisely.
- Backtest winners survive more reliably in live conditions.
- The system becomes more boring in a good way: fewer noisy trades, clearer reasons, better selectivity.

---

## Changelog (Docs)

- 2026-03-26: Added a dedicated M15 improvement roadmap focused on regime robustness, session filtering, stricter selection pressure, backtest realism, playbook diversity, and exit design.