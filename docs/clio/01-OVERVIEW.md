# autonomous_trading_ai – Overview

## Purpose

`autonomous_trading_ai` is an MT5-centric autonomous trading research and
execution system designed for **supervised semi-autonomous operation**.

Its current strengths are:

- automated market-data refresh
- feature engineering and regime detection
- strategy generation/evolution
- backtesting and robustness checks
- persistent strategy-pool governance
- live execution with hard risk controls
- live monitoring, degradation, circuit-breaker behavior, and proactive live decay detection

The current codebase is best understood as a **specialist strategy portfolio +
routing engine**, not a generic all-broker trading framework.

## Current Scope

Implemented scope today is centered on:

- **MetaTrader 5** for data and execution
- strongest practical alignment with **`XAUUSDm` on `M15`**
- support for additional symbols/timeframes where configured
- structured regime-aware live routing
- Chroma-backed research memory
- optional best-effort webhook/WhatsApp alerts

The current system is **not** best described as:

- a universal multi-broker engine
- a mature multi-asset portfolio optimizer
- a fully hands-off black-box trading bot

## Core Design Philosophy

### 1) Specialist strategies, not one universal strategy

The system is designed to find and operate **bounded specialists**:

- trend specialists
- range / mean-reversion specialists
- session-biased specialists
- volatility-sensitive specialists

A strategy is allowed to be narrow if it has a credible role and the routing
layer knows when to use it.

### 2) Eligibility before ranking

The live system should first ask:

- is this strategy allowed in the current session?
- is it allowed in the current regime?
- is volatility a fit?
- is routing confidence high enough?

Only then should it rank eligible strategies by edge.

### 3) Research and live are connected, but not identical

Research finds and explains candidate behaviors.
Live execution reuses that information conservatively.

Backtests help answer:

- does this strategy have evidence?
- where is it strongest or weakest?

Live routing then asks:

- should it trade **right now**?

## Key Concepts

- **StrategyDefinition** – declarative rule-based strategy spec
- **StrategyPool** – long-lived inventory of strategy records and statuses
- **Specialist routing** – live policy layer that determines strategy eligibility
- **`strategy_explain`** – structured explanation of backtest behavior
- **`strategy_explain.meta`** – routing-oriented summary such as allowed/blocked regimes/sessions
- **Exploratory tier** – lower-risk live tier used for controlled evidence gathering
- **ResearchMemory** – Chroma-backed memory of prior evaluated strategies
- **Daily guardrails** – daily DD / trade-count limits
- **Circuit breaker** – portfolio-level protection based on drawdown from peak equity

## Current Operating Modes

### 1. Backtest / research

- historical features
- candidate generation/evolution
- scoring, explainability, walk-forward, Monte Carlo
- no live order placement

### 2. Live semi-autonomous operation

- scheduler refreshes data/features
- live router selects eligible strategies
- MT5 orders are placed if all gates pass
- state, equity, and live PnL are continuously monitored

### 3. Operator-assisted inspection

- scripts provide quick debugging, status summaries, and maintenance tooling
- docs/runbooks support manual restart, inspection, and troubleshooting

## Safety Philosophy

The system should prefer:

- **no trade** over weak trade
- bounded exploratory risk over blind experimentation
- explicit logging over hidden behavior
- conservative degradation over overconfident promotion

Failure should lean safe:

- missing data → skip
- bad routing context → skip
- daily lock active → skip
- portfolio DD breach → disable active strategies

## OpenClaw / Clio Role

Clio is best used here as:

- an operator/developer assistant
- a documentation maintainer
- a research summarizer
- a workflow orchestrator

Clio can inspect:

- pool state
- runbooks
- logs
- research exports
- memory summaries

but should not be treated as a replacement for the hard-coded risk and
execution safety layers.

## Current Status Snapshot

A more honest shorthand for the project today:

- **Research loop:** materially hardened by Track A
- **Live routing:** materially improved and now paired with stronger attribution/audit behavior from Track B plus post-audit concentration control
- **Risk controls:** real and meaningful, with upstream selection sanity improved by negative-edge fallback protection and decay-aware governance
- **Operator visibility:** improved, including unmatched-deal and pool-audit artifacts
- **Alerting:** useful but best-effort
- **Portfolio intelligence:** still limited
- **Backtest realism:** adequate for screening, not perfect
- **Exit quality:** improved by Track C, though native partial-TP support is still absent

## Changelog (Docs)

- 2026-04-04: Updated overview snapshot for post-audit hardening work (fallback guard, concentration control, live decay detection).
- 2026-04-03: Refreshed the overview status snapshot after Track A / B / C implementation.

- 2026-03-27: Rewrote the overview to reflect the real MT5-centric pass 3 system, specialist-routing design, and current safety boundaries.