# Phase 4 – Memory-Guided Governance

**Goal:**

Use ResearchMemory (vector store) and live stats to:

1. Filter out strategy candidates that resemble historically bad
   patterns before spending compute on backtests.
2. Bias evolution and selection toward historically robust strategies.
3. Combine backtest and live performance into hybrid scores for
   promotion/demotion.
4. (Optional) Build regime-specific "playbooks" and a memory-backed
   circuit breaker.

This file provides high-level guidance for Phase 4. It is **advanced**
and should only be attempted after Phases 1–3 are implemented, tested,
and running stably.

Root path for this project:

```text
C:\Users\afusi\.openclaw\workspace\autonomous_trading_ai
```

---

## 4.1 Candidate Filtering via ResearchMemory (4.1)

**Idea:** Reduce wasted backtest compute by avoiding strategy candidates
that are similar to historically poor performers.

### High-level plan

1. Extend `vector_memory/ResearchMemory` (or add a helper) to support
   queries that:
   - filter by `symbol`, `timeframe`, and optionally regime/session
     metadata,
   - return top-k similar strategies with their key stats.

2. In `scheduler/job_research_strategies`, add a pre-backtest check for
   each new candidate strategy:
   - Build a text representation of the strategy (e.g. name, rules
     summary, key params) or reuse stored statistics when available.
   - Query ResearchMemory for similar entries.
   - Analyze the neighbors' stats:
     - count how many have `sharpe_ratio < 0` or
       `profit_factor < 1.0`,
     - inspect regime-specific returns if available.

3. If the candidate is too similar to a cluster of clearly bad
   strategies:
   - either skip `run_backtest` for this candidate, or
   - assign a strong penalty to its eventual score.

### Notes

- This step should be conservative: it is better to backtest a few
  redundant strategies than to accidentally block a genuinely new edge.
- Implement this as a small, well-isolated function so it can be tuned
  or disabled easily.

---

## 4.2 Memory-Guided Elite Selection (4.2)

**Idea:** When selecting parents for evolution, prefer strategies whose
"neighborhood" in memory also looks good.

### High-level plan

1. For each candidate parent (StrategyRecord) in the pool:
   - Compute a **memory consistency bonus** using ResearchMemory:
     - query nearest neighbors,
     - compute an aggregate score (e.g. average Sharpe/PF of neighbors),
     - normalize into a small bonus value.

2. Modify parent selection in `job_research_strategies`:
   - current logic sorts by `rec.score` (backtest-based).
   - new logic sorts by `rec.score + memory_bonus`.

3. Keep the memory bonus small (e.g. a fraction of a score unit) so it
   nudges selection without dominating the base evaluation.

### Notes

- The exact formula for `memory_bonus` can be iterated over time.
- All decisions should still be explainable from logged stats and
  ResearchMemory contents.

---

## 4.3 Hybrid Live + Backtest Scoring (4.3)

**Idea:** Use both historical backtests and live performance to
prioritize strategies.

### High-level plan

1. For each strategy in the pool:
   - From backtest stats: `return_pct`, `sharpe_ratio`,
     `max_drawdown_pct`, `profit_factor`, regime behavior.
   - From live stats (via `execution/strategy_live_stats.json`):
     - `total_pnl`, `num_trades`, `recent_pnls`,
     - compute live_return_pct (relative to initial_equity).

2. Normalize these into two scores:
   - `bt_score_norm` – based on existing evaluation score, scaled to
     [0, 1].
   - `live_score_norm` – based on live_return_pct, volatility, and
     stability of recent_pnls.

3. Combine into a hybrid score:

   ```text
   hybrid_score = w_bt * bt_score_norm + w_live * live_score_norm
   ```

   where `w_bt` > `w_live` initially (e.g. 0.7 vs 0.3).

4. Use `hybrid_score` for:
   - ranking strategies in the pool,
   - choosing parents for evolution,
   - informing promotion/demotion decisions beyond the existing
     degradation rules.

### Notes

- Start with a conservative weight on live performance and increase it
  only after enough live trades accumulate.
- Ensure strategies with very little live data are not over-penalized.

---

## 4.4 Regime-Specific Memory & Playbooks (4.4)

**Idea:** Build a library of regime-specific "playbooks" that describe
what works well in certain conditions.

### High-level plan

1. When storing strategy results in ResearchMemory, include metadata
   from `strategy_explain`, such as:
   - `best_regime`, `worst_regime`,
   - dominant sessions (asia/london/new_york),
   - volatility buckets.

2. Implement helper functions like
   `query_top_playbooks(regime_label, session, vol_bucket)` that:
   - query ResearchMemory with filters on these metadata fields,
   - return a small set of top historical strategies and their
     characteristics.

3. Use this information to:
   - refine live regime-aware selection (Phase 2) by referencing
     historically best playbooks for the current regime/context.
   - provide human-readable summaries (e.g.
     "XAU M15 trend-follow scalper, best in London session high vol,
     avoids high-impact news").

### Notes

- This sub-phase mostly improves research and interpretability; it
  should not increase live risk.

---

## 4.5 Memory-Backed Circuit Breaker (Optional, 4.5)

**Idea:** Add a meta risk layer that reacts to historically dangerous
patterns by temporarily reducing risk or disabling certain strategies.

### High-level plan

1. Analyze ResearchMemory and live logs for patterns where:
   - a given combination of `regime_class`, `news_impact_level`, and
     symbol/timeframe leads to repeated large drawdowns.

2. Implement a small circuit-breaker module (or extend
   `execution/live_monitor`) that:
   - monitors current context (regime, news impact, etc.),
   - checks against known dangerous patterns from memory,
   - if a match is found:
     - temporarily reduces `risk_per_trade` caps, and/or
     - disables specific strategies known to perform poorly in this
       pattern.

3. All actions should be logged clearly so humans can audit the
   circuit-breaker decisions.

### Notes

- This is **optional** and should be treated very conservatively.
- It should never increase risk; it only reduces or disables it under
  certain contexts.

---

## Safety & Implementation Notes

- Phase 4 is intentionally broad and should be implemented in **small,
  testable steps**.
- For each sub-phase (4.1–4.5):
  - isolate changes to a few functions/files,
  - add logging to observe effects,
  - run tests and inspect logs before committing.
- If any part of Phase 4 introduces instability or unexpected behavior,
  it is acceptable to disable or roll back that sub-phase while keeping
  the rest of the system intact.

Phase 4 is optional. The system should already be functional and
reasonably robust after Phases 1–3; Phase 4 is about making it smarter
and more self-aware over time, not about raising risk.