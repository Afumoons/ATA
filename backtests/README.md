# backtests/ – Simulation, Evaluation & Explainability

## Purpose

This module handles the **offline research side** of the trading system:

- simulate strategy behavior bar-by-bar
- compute summary performance statistics
- build structured explanations of where a strategy works or fails
- run robustness checks before a strategy is trusted more broadly

In pass 3, this module matters even more because its outputs now feed the
system’s **specialist routing model**, not just a single numeric score.

## What This Module Produces

The key outputs from the backtesting layer are:

- `BacktestResult`
- performance `stats`
- `strategy_explain`
- evaluation `score`
- acceptance decision (`accepted`)
- optional walk-forward aggregates
- optional Monte Carlo stress-test aggregates

These outputs are then consumed by:

- `scheduler/main.py`
- `strategies/pool.py`
- `vector_memory/research_memory.py`
- `execution/signals.py` indirectly via `strategy_explain.meta`

## Key Files

### `engine.py`

Core bar-by-bar simulator.

Important pieces:

- `Trade` dataclass
  - single closed-trade record with times, prices, side, size, SL/TP, PnL,
    and optional regime tagging
- `BacktestResult` dataclass
  - strategy metadata
  - list of trades
  - equity curve
  - summary stats dict
- `_eval_rule(row, rule)`
  - evaluates rule strings against a feature row using a restricted namespace
- `run_backtest(df, strategy, ...)`
  - executes the simulation over historical bars
  - applies position sizing from risk-per-trade and SL distance
  - supports fixed-pip SL/TP and ATR-based SL/TP
  - applies costs from `costs.py`
  - tags trades with regimes when available
  - computes stats and attaches `strategy_explain`
- `_compute_basic_stats(...)`
  - computes core metrics such as return, Sharpe, DD, PF, win rate, trade count
  - now also emits same-bar ambiguity diagnostics when a candle touches both SL and TP while the fill model remains pessimistic SL-first
- `save_backtest_result(result)`
  - writes JSON exports under `backtests/results/`

### `costs.py`

Trading-cost helpers used by the backtest engine.

This file keeps cost modeling separate from simulation logic so spreads,
slippage, and commissions can be applied consistently.

### `evaluation.py`

Turns performance outputs into a score and pass/fail decision.

Important pieces:

- `EvaluationConfig`
  - thresholds for minimum trades, Sharpe, drawdown, PF
  - weights for the scoring model
- `compute_score(stats, cfg)`
  - combines Sharpe, PF, and DD penalty into a base score
  - then adjusts it using `strategy_explain`
- `passes_thresholds(stats, cfg)`
  - enforces minimum requirements
- `evaluate_strategy(stats, cfg)`
  - produces the final score + `accepted` decision

In pass 3, scoring is not just about “good total return.” It also rewards or
penalizes **behavior quality** in ways that matter for specialist live routing.

### `explain.py`

Builds the structured `strategy_explain` object.

This is one of the most important pass 3 pieces.

`strategy_explain` can include:

- `regime_pnl`
- `session_pnl`
- `risk_behavior`
- `stability`
- `news_behavior`
- `meta`

The `meta` section is especially important because it can contain:

- `best_regime` / `worst_regime`
- `best_session` / `worst_session`
- `allowed_regimes` / `blocked_regimes`
- `allowed_sessions` / `blocked_sessions`
- `routing_confidence`
- descriptive tags like trend-follower vs range trader

Those fields persist into pool stats and are later reused by the live-routing
layer.

### `walkforward.py`

Out-of-sample validation helpers.

Used to split time-series data into rolling train/test windows and estimate how
stable a fixed strategy spec remains when evaluated on unseen sections.

Outputs typically include:

- per-window results
- aggregate Sharpe
- aggregate max drawdown
- number of windows

### `monte_carlo.py`

PnL stress-testing helpers.

Used to stress trade-sequence fragility with either:

- full trade-order shuffling, or
- block-bootstrap resampling that preserves short local streak structure

Optional slippage-like noise can also be applied.

Outputs typically include:

- mean / p5 / p95 final PnL
- mean / p5 / p95 max drawdown
- loss probability
- CVaR-style tail loss metric (`mc_cvar_p5`)
- drawdown threshold breach probabilities

## Core Pass 3 Role

Pass 3 makes backtests more than a promotion filter. They now provide the raw
material for **specialist governance**:

- which regimes a strategy should be allowed in
- which sessions it should avoid
- whether it behaves poorly near macro events
- whether it is too unstable to route live capital confidently

In other words:

- `evaluation.py` decides if a strategy is good enough
- `explain.py` helps decide **where and when** it should be used

## Directory Layout

- `backtests/results/`
  - exported JSON results for offline inspection and AI-assisted review

## How It’s Used

### In research

`scheduler.job_research_strategies()` typically:

1. loads features
2. runs `run_backtest(...)`
3. evaluates stats with `evaluate_strategy(...)`
4. optionally runs walk-forward and Monte Carlo
   - current research flow now prefers block-bootstrap MC for larger trade sets,
     because sequence clustering matters for bounded specialists too
5. stores stats + explain into the strategy pool and research memory

### In live routing

The live layer does not call this module directly during each execution pass,
but it consumes the artifacts produced here through saved pool records.

That means the quality of:

- `regime_pnl`
- `session_pnl`
- `news_behavior`
- `meta.allowed_*`
- `meta.blocked_*`
- `meta.routing_confidence`

has direct downstream impact on execution behavior.

## Gotchas / Notes

- `_eval_rule` uses restricted `eval`; rule strings are system-generated, not
  intended for arbitrary user-supplied expressions.
- Backtests are bar-based abstractions and cannot fully model live broker
  microstructure.
- Walk-forward validation currently checks robustness of a fixed strategy spec;
  it does not do full per-window re-optimization.
- Same-bar ambiguity instrumentation is currently diagnostic only; it improves
  auditability but does not yet change fill policy.
- Monte Carlo is now stronger than pure shuffle because it can use block-bootstrap
  resampling plus richer governance metrics.
- Even so, it still does not fully model regime-aware scenario stress or all
  real execution clustering effects.
- For pass 3, a strategy with decent global PnL can still be a poor live
  candidate if its routing or stability profile is weak.

## Changelog (Docs)

- 2026-04-04: Updated for Monte Carlo v1 upgrade (block bootstrap, richer tail metrics, and governance-oriented outputs).
- 2026-04-04: Updated for same-bar ambiguity diagnostics in backtest stats.
- 2026-03-21: Documented bar simulation, evaluation, explainability, and
  robustness tooling.
- 2026-03-27: Updated for pass 3 emphasis on `strategy_explain.meta`,
  specialist routing support, and the module’s role in live governance.