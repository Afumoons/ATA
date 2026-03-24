# Phase 4 – Next Steps (Reminder)

Context (recorded by Clio Nova):
- Phase 4.1 (memory-guided candidate filtering via ResearchMemory) is already implemented in `scheduler/main.py`.
- The system now skips backtests for strategies whose nearest neighbors in ResearchMemory (same symbol/timeframe) are overwhelmingly bad (Sharpe < 0, PF < 1.0, or return_pct << -5%).

When we want to continue Phase 4 later, the next planned sub-phases are:

## 4.2 – Memory-Guided Elite Selection

- Add a small "memory consistency" bonus when selecting parent strategies in `job_research_strategies`:
  - For each parent candidate (StrategyRecord), query ResearchMemory for neighbors and compute an average quality metric (e.g. average Sharpe/PF of neighbors).
  - Combine pool score + memory bonus to rank parents for `evolve_population`.
- Keep the memory bonus small so it nudges selection without overriding backtest evaluation.

## 4.3 – Hybrid Live + Backtest Scoring

- Combine backtest stats and live stats (from `execution/strategy_live_stats.json`) into a hybrid score, e.g.:

  ```text
  hybrid_score = w_bt * normalized_bt_score + w_live * normalized_live_score
  ```

- Use `hybrid_score` to:
  - rank strategies in the pool,
  - select parents for evolution,
  - inform promotion/demotion decisions alongside the existing degradation rules.

## 4.4 – Regime-Specific Playbooks (Optional)

- Store richer metadata from `strategy_explain` (best/worst regimes, dominant sessions, volatility buckets) in ResearchMemory.
- Add helpers to query "top playbooks" for a given regime + context (e.g. trending_up + London + high_vol).
- Integrate these playbooks into live regime-aware selection as an additional layer (beyond Phase 2's simple regime filter).

## 4.5 – Memory-Backed Circuit Breaker (Optional, High Caution)

- Analyze ResearchMemory + live logs for patterns where certain contexts (regime_class + news_impact_level + symbol/timeframe) repeatedly cause large drawdowns.
- Implement a conservative circuit-breaker in `execution/live_monitor` (or a new module) that:
  - temporarily reduces risk caps or disables specific strategies when those dangerous contexts reappear.
- All decisions must be logged clearly for human audit.

---

How to resume later:
- When Afu says e.g. "lanjut 4.2" or "lanjut Phase 4 berikutnya", use this file and `dev_notes/phase4_memory_guided_governance.md` as the concrete roadmap.
- Always implement one sub-phase at a time, with tests and logs between steps.
