# DEVELOPMENT_PLAN.md – autonomous_trading_ai

## Vision

Build an autonomous trading system that:

- Produces **real, live trades** under controlled risk.
- Learns and adapts to **market regimes** over time.
- Maintains **high standards** for production strategies while allowing
  **small-risk exploration** to discover new edges.
- Is **well-documented**, testable, and versioned via git.

This plan is the high-level roadmap. Detailed per-file instructions for
individual phases live under `dev_notes/`.

For the **current near-term production hardening focus on `XAUUSDm M15`**, see:
- `06-M15_IMPROVEMENT_ROADMAP.md`

Treat this file as the broad historical / structural roadmap, and the M15 file
as the current execution-priority roadmap.

---

## Principles

1. **Safety-first for production**
   - Keep strict thresholds for `active` strategies.
   - Do not silently relax risk constraints or thresholds just to "force" trades.

2. **Exploration under small risk**
   - Introduce an `exploratory` strategy tier with significantly lower
     per-trade risk, so the system can gather live data without exposing
     the account to large drawdowns.

3. **Regime-aware behavior**
   - Use `regime` information and `strategy_explain.regime_pnl` to select
     strategies that have edge in the **current** market regime.

4. **Iterative development**
   - Implement improvements in **phases**.
   - After each phase:
     - Run basic tests.
     - Update documentation.
     - Commit changes to git with clear messages.

5. **Transparent automation**
   - Background agents / cron jobs must follow this plan and the
     per-file instructions in `dev_notes/`.
   - All significant changes should be reflected in docs + git history.

---

## Phases Overview

### Phase 0 – Baseline & Snapshot

**Goal:** Capture current state of the codebase and strategy pool.

Tasks:
- Record git status / recent commits into `notes/dev_log.md`.
- Snapshot `strategies/pool_state.json` into `notes/pool_snapshot.md`:
  - total strategies
  - count per status (candidate/active/disabled/...)  

> This phase is informational only; it does not change behavior.

---

### Phase 1 – Exploratory Strategy Tier + Risk Tiers

**Goal:** Ensure there is always a tier of strategies that can trade live
with **small risk**, without lowering standards for `active`.

Key changes:

- Extend `StrategyRecord.status` to support a new status: `"exploratory"`.
- In `job_research_strategies`:
  - Keep existing strict criteria for `active` strategies.
  - For strategies that are `accepted` but not strong enough for `active`:
    - Promote to `exploratory` if they:
      - Have sufficient backtest trade count (e.g. `num_trades >= 20`), and
      - Show positive performance in trending regimes.
    - Otherwise keep them as `candidate`.
- In `execute_signals_for_symbol`:
  - Distinguish between `active` and `exploratory` records.
  - Use **two risk tiers**:
    - `active` → normal risk (`risk_perc` as currently computed).
    - `exploratory` → reduced risk (e.g. 4x smaller, capped at a low
      percentage like 0.1% per trade).

Result:
- The system can begin placing small, controlled exploratory trades even
  when no strategy qualifies as fully `active`.

Detailed file-level steps: see
`dev_notes/phase1_exploratory_status_and_risk_tiers.md`.

---

### Phase 2 – Regime-Aware Live Strategy Selection

**Goal:** Make live execution adaptive to the **current market regime**.

Key changes:

- In `execute_signals_for_symbol`:
  - Read the latest `regime` label from the latest feature row.
  - Define a helper to read regime-specific performance from
    `strategy_explain.regime_pnl` and compute an "edge" value per
    strategy for a given regime.
  - Filter and rank `active` and `exploratory` strategies by their edge
    in the current regime.
  - Optionally limit how many strategies are allowed to fire signals per
    symbol/timeframe in a given run (e.g. top 5 `active`, top 3
    `exploratory`).

Result:
- In trending regimes, the system prefers trend-following strategies
  with good historical performance in those regimes.
- In ranging regimes, it prefers range / mean-reversion strategies.

Detailed file-level steps: see
`dev_notes/phase2_regime_aware_live_selection.md`.

---

### Phase 3 – Generator Improvements (More Practical Strategies)

**Goal:** Increase the proportion of generated strategies that are:

- sufficiently active (`num_trades` not too low), and
- structurally reasonable (not overly niche or fragile).

Key changes (high level):

- Extend `LONG_ENTRY_TEMPLATES` / `SHORT_ENTRY_TEMPLATES` with additional
  patterns:
  - simple trend-follow using MA + trend strength,
  - simple range/mean-reversion using RSI + low trend strength.
- Optionally introduce ATR-based SL/TP multiples via new parameters
  (`sl_atr_mult`, `tp_atr_mult`) and integrate them into backtesting.
- Future work: leverage ResearchMemory to soft-filter new strategies that
  closely resemble historically poor performers.

Detailed file-level plan: to be defined in
`dev_notes/phase3_generator_improvements.md`.

---

### Phase 4 – Memory-Guided Governance (Optional / Advanced)

**Goal:** Use vector-backed ResearchMemory and live stats to:

- Reduce compute spent on clearly bad pattern families.
- Bias evolution and selection toward historically promising areas.
- Make promotion/demotion decisions that combine backtest and live
  performance.

Phase 4 is split into several sub-phases:

#### 4.1 Candidate Filtering via ResearchMemory

- Before backtesting a new strategy candidate, query ResearchMemory for
  similar strategies (filtered by symbol/timeframe and relevant
  metadata).
- If most similar strategies show consistently poor performance
  (e.g. Sharpe < 0, PF < 1.0, or very bad in specific regimes), either:
  - skip backtesting this candidate entirely, or
  - apply a strong penalty to its final score so it is unlikely to be
    promoted.

#### 4.2 Memory-Guided Elite Selection

- When selecting parent strategies for evolution, augment the existing
  score with a "memory consistency" bonus:
  - Strategies whose nearest neighbors in ResearchMemory also perform
    well across multiple windows receive a higher effective score.
- Use this hybrid score (pool score + memory bonus) to choose elites for
  `evolve_population`.

#### 4.3 Hybrid Live + Backtest Scoring

- Combine backtest stats and live stats (from
  `execution/strategy_live_stats.json`) into a hybrid score:

  ```text
  hybrid_score = w_bt * normalized_bt_score + w_live * normalized_live_score
  ```

- Use the hybrid score for:
  - ranking strategies in the pool,
  - choosing parents for evolution,
  - informing promotion/demotion decisions.

#### 4.4 Regime-Specific Memory & Playbooks

- Store and query ResearchMemory with richer metadata from
  `strategy_explain`:
  - best/worst regimes,
  - dominant sessions,
  - volatility buckets.
- Provide helpers to query "playbooks" with edge in specific regimes and
  contexts (e.g. trending_up + London + high_vol).
- Use these playbooks to refine regime-aware selection in live
  execution, beyond the basic Phase 2 logic.

#### 4.5 Memory-Backed Circuit Breaker (Optional)

- Add a meta risk layer that:
  - observes repeated crash patterns (e.g. strategies with certain
    characteristics consistently underperform around high-impact news),
  - temporarily reduces risk or disables affected strategies when
    similar conditions reappear.

This phase requires careful design and iteration and should be tackled
after Phase 1–3 are stable. It is **optional** and should respect the
same safety constraints: no increase in risk percentages, and no
weakening of existing risk controls.

---

### Phase 5 – Testing & Sanity Checks

Baseline tests after each major phase:

- Syntax / import checks:
  - `python -m compileall autonomous_trading_ai` **or**
  - `python -c "import autonomous_trading_ai"`.
- If test suite exists (e.g. pytest):
  - run `pytest` in the repo.
- Functional dry runs (in a safe/test environment when possible):
  - `job_update_data()` once.
  - `job_research_strategies()` once.
  - `job_execute_signals()` once.

Check results:

- `strategies/pool_state.json` shows reasonable counts for
  `active` / `exploratory` / `candidate` / `disabled`.
- Logs from `job_execute_signals` show either:
  - valid signal execution attempts, or
  - clear, expected reasons for skipping (no features, daily limits,
    etc.), but not systematic failure.

---

### Phase 6 – Documentation Updates

After behavior changes, update:

- `strategies/README.md`:
  - explain new `exploratory` status and its role.
- `execution/README.md`:
  - describe risk tiers for `active` vs `exploratory`.
- `scheduler/README.md`:
  - describe how research and live execution now incorporate
    exploratory status and regime-aware selection.
- Any user/agent instruction files related to running the system:
  - reflect the new lifecycle and monitoring expectations.

Detailed doc steps: to be captured per phase under `dev_notes/`.

---

### Phase 7 – Git Workflow & Logging

For each phase or coherent batch of changes:

1. Ensure working tree is clean, or changes are clearly scoped.
2. Run basic tests (Phase 5).
3. Commit using conventional-ish messages, e.g.:
   - `feat: add exploratory strategy tier and risk levels`
   - `feat: make live execution regime-aware`
   - `feat: extend strategy generator templates`
   - `docs: update strategy lifecycle documentation`
4. Update `notes/dev_log.md` with:
   - date/time,
   - short summary of changes,
   - tests run and their outcome.

Optional:

- Maintain `notes/changelog.md` for higher-level milestones (e.g. when
  shipping a new version to a live account).

---

## How Background Agents Should Use This Plan

- Use this file as the **high-level roadmap**.
- Before making changes, consult the relevant `dev_notes/phaseX_*.md`
  file for concrete, per-file instructions.
- Respect the phase ordering: focus on Phase 1–2 first to get live
  exploratory trading and regime-aware behavior, then proceed to Phase 3+
  when stable.
- Never bypass tests and documentation steps; they are integral to the
  development loop, not optional extras.
