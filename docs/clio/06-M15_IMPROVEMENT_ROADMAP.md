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

The intended design is also **not** to find one universal strategy that works everywhere.

The correct design target is:

> Build a portfolio of **specialist strategies** that are strong in specific regimes / sessions, then use a disciplined **routing layer** to activate only the right specialists in the right context.

In practice, many strategies already appear strongest only under a subset of conditions (specific regimes, sessions, or volatility states). That is **acceptable and expected**.

The real problem is that the current pipeline still does not route and gate those specialists sharply enough, and it still lets too many fragile or thin-edge strategies survive into the pool.

---

## Biggest M15 Bottlenecks

### 1. Regime specialist routing is still too weak

Observed pattern:
- Many strategies are strongest in `trending_down`.
- Several degrade badly in `high_vol` and some `ranging` conditions.
- Some strategies are clearly regime specialists, but the system does not yet fully treat them as such.

Why this matters:
- Specialist behavior is expected.
- The failure mode is not that a strategy is regime-specific; the failure mode is letting a regime-specific strategy trade outside its edge zone.
- Live performance degrades when routing is too permissive or too coarse.

Interpretation:
- The system is already discovering **regime-local specialists**, but the orchestration layer is not yet strong enough to deploy them with enough precision.

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
- Same-bar ambiguity is now instrumented, which improves visibility, but that instrumentation is diagnostic only and not yet a fill-model upgrade.

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

### 6. Acceptance pressure is still too permissive for weak specialists and noisy candidates

Observed pattern:
- Many strategies in the pool still cluster around modest profit factor / moderate instability.
- Some accepted exploratory strategies are useful for learning, but others may simply add noise.
- Not every specialist is a good specialist; some are just overfit or too fragile.

Why this matters:
- Weak specialists still consume execution bandwidth, risk budget, and operator attention.
- They also pollute the evolutionary pool and make routing less trustworthy.

Interpretation:
- Pool governance still needs to become more selective, not to force universal robustness, but to ensure each surviving specialist has a credible and well-bounded role.
- Recent post-audit hardening already helped here through negative-edge fallback blocking, light concentration control, and proactive live decay detection.

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

## Phase A – Build a stronger specialist routing layer (highest priority)

### Goal
Treat regime/session specialization as a first-class design feature, then route strategies more precisely.

### Actions

1. **Make specialist intent explicit in governance**
   - Treat “best in one regime, weak elsewhere” as acceptable **if** the strategy has a clear bounded role.
   - Stop implicitly rewarding only broad-average behavior.

2. **Add explicit specialist metadata**
   - Promote fields such as:
     - `best_regime`
     - `worst_regime`
     - `best_session`
     - `worst_session`
     - volatility preference
     - routing confidence

3. **Strengthen “do not trade” behavior**
   - If there is no clear specialist with edge in the current context, the system should stay flat.
   - Weak or ambiguous routing should default to inaction, not forced participation.

### Deliverable
- The system becomes a **specialist portfolio + routing engine**, not an accidental search for universal strategies.
- Specialist strategies are easier to interpret, categorize, and deploy safely.

---

## Phase B – Make live trading session-aware

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

3. **Route specialists only to their intended edge zone**
   - A `trending_down` specialist should not be treated as generally eligible.
   - A range specialist should not be trusted automatically during high-vol trend expansion.

4. **Apply confidence-aware throttling**
   - If regime confidence is weak, either:
     - reduce execution aggressiveness,
     - or require stronger strategy edge to trade.

### Deliverable
- A live layer that uses regime context more precisely.
- Lower mismatch between research richness and execution logic.
- Better deployment of specialist strategies.

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

1. **Phase A – Build a stronger specialist routing layer**
2. **Phase B – Session-aware live filtering**
3. **Phase C – Sharpen regime-aware live filtering**
4. **Phase D – Improve backtest realism / reporting**
5. **Phase E – Expand playbook diversity**
6. **Phase F – Improve exit design**

Reason:
- The highest leverage now is not searching for universal robustness.
- The highest leverage is correctly **routing specialist strategies** to the contexts where they actually have edge.
- Better routing and gating should come before expanding playbook count.

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

## Related technical follow-up

For the detailed routing-layer audit and implementation checklist, see:
- `07-ROUTING_LAYER_AUDIT_AND_TASKLIST.md`

Implemented so far:
- **A1 v1** - explicit routing metadata derived into `strategy_explain.meta`
- **A2 v1** - session hard gate in live routing using `allowed_sessions` / `blocked_sessions`
- **A3 v1** - structured regime routing and confidence-aware gating in live execution
- **A4 v1** - unified scheduler orchestration for `active` + `exploratory`
- **A5 v1** - explicit no-eligible-specialist vs no-entry reporting
- **A6 v1** - specialist-aware promotion logic
- **A7 v1** - specialist-aware execution quality-gate review
- **Post-audit follow-through** - negative-edge fallback guard, same-bar ambiguity instrumentation, proactive live decay detection v1, and concentration control at manifest/runtime layers

---

## Changelog (Docs)

- 2026-04-04: Cleaned roadmap status text, fixed corrupted bullets, and added post-audit hardening work now already completed.
- 2026-03-26: Added a dedicated M15 improvement roadmap focused on regime robustness, session filtering, stricter selection pressure, backtest realism, playbook diversity, and exit design.
- 2026-03-26: Reframed the roadmap around specialist strategies + routing-layer discipline.
- 2026-03-26: Updated roadmap status after A1/A2 implementation progress and linked the routing-layer audit/tasklist.
- 2026-03-27: Updated roadmap status after A3–A7 v1 implementation progress.
- 2026-03-27: Validated saved feature pipeline fields (`regime`, `regime_class`, `regime_type`, `regime_confidence`, `vol_regime`) and tightened A3 routing to use structured candidate labels plus explicit volatility mismatch handling.
- 2026-03-27: Implemented stricter M15 research pressure for Phase D/E follow-through: pessimistic backtest defaults in scheduler research, Monte Carlo survivability gating, stronger specialist/session governance thresholds, and broader deterministic playbook-family diversity in strategy generation/evolution.

