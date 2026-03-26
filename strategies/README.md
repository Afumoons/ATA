# strategies/ – Definitions, Generation, Pool & Live-Aware Degradation

## Purpose

This module defines **how strategies are represented**, how new ones are
generated/evolved, and how the global strategy pool is stored and maintained.

It provides:

- A serializable `StrategyDefinition` config object (no executable code).
- Tools to generate and mutate strategies (MA/RSI-focused with legacy
  Ichimoku/Fibonacci support).
- A `StrategyPool` abstraction to track scores, statuses, stats, and (via
  other modules) live performance.

## Key Files

- `base.py`
  - Defines `StrategyDefinition` dataclass:
    - `name`, `symbol`, `timeframe`.
    - `long_entry_rule` / `short_entry_rule` – string expressions evaluated over
      feature rows (via backtest engine).
    - `exit_rule` – string expression controlling exits (used in backtests).
    - `stop_loss_pips`, `take_profit_pips` – SL/TP distances.
    - Optional `sl_atr_mult`, `tp_atr_mult` – ATR-based SL/TP multipliers used
      by the backtest engine when present (with ATR column in features).
    - `params` – free-form dict used by generator/evolution.
  - Methods:
    - `to_dict()` / `from_dict()` – JSON-serializable representation.

- `generator.py`
  - Focused on **initial strategy creation**.
  - Uses a mix of rule templates:
    - MA-based trend continuation using `ma_short` vs `ma_long`.
    - Range/mean-reversion patterns using RSI with low `trend_strength`.
    - Legacy Ichimoku/Fibonacci continuation patterns (still available but
      down-weighted for most markets).
    - `LONG_ENTRY_TEMPLATES`, `SHORT_ENTRY_TEMPLATES`, `EXIT_TEMPLATES`.
  - `random_strategy(symbol, timeframe)`:
    - For core 15m markets (`XAUUSDm`, `BTCUSDm`), biases strongly toward
      simpler MA/RSI-based templates and away from heavy Ichimoku/Fibonacci
      patterns to favor more interpretable strategies.
    - Samples template parameters (`trend_min`, `rsi_exit`, `trend_exit`).
    - Builds rule strings by formatting templates with these params.
    - Picks SL/TP from a discrete set of pip values for all markets.
    - For core 15m markets, additionally samples conservative ATR-based
      SL/TP multiples (`sl_atr_mult`, `tp_atr_mult`) used by the backtest
      engine while keeping pip-based distances available for live sizing.
    - Attaches lightweight metadata into `StrategyDefinition.params` so later
      phases can reason about each strategy family without re-parsing rule
      strings, including:
      - `long_family` / `short_family` (e.g. `ma_trend`, `rsi_range`, `ichifib`).
      - `regime_type_long` / `regime_type_short` and an aggregate
        `regime_type` (e.g. `trend`, `range`, `mixed`).
      - `preferred_symbols` / `preferred_timeframes` indicating which
        symbol/timeframe the strategy was generated for.
    - Produces a `StrategyDefinition` with a name like
      `"core15_{symbol}_{timeframe}_{rand_id}"` for core 15m markets or
      `"ichifib_{symbol}_{timeframe}_{rand_id}"` for others.
  - `save_strategy(strategy)` / `load_strategy(path)` – read/write strategy
    JSON files under `strategies/generated/`.
  - `generate_batch(...)` / `generate_and_save_batch(...)` – helpers to create
    many strategies at once.

- `evolution.py`
  - Implements a simple evolutionary algorithm over existing strategies.
  - `EvolutionConfig`:
    - `population_size`, `elite_frac`, `mutation_rate`, `crossover_rate`.
  - Mutation helpers:
    - `_mutate_params(params)` – nudge numeric fields within safe bounds
      (e.g. `rsi_low`, `rsi_high`, `trend_min`, `vol_max`, `rsi_exit`, `trend_exit`).
    - `_mutate_strategy(strat)` – create a new `StrategyDefinition` by
      combining mutated params with a fresh template from `random_strategy`.
  - Crossover:
    - `_crossover(a, b)` – mix parameter dictionaries from two parents, then
      instantiate a new child strategy via `random_strategy`.
  - `evolve_population(symbol, timeframe, scored_strategies, cfg=DEFAULT_EVOL_CONFIG)`:
    - If no scored strategies are available, generates a fresh population of
      random strategies.
    - Otherwise:
      - Sorts by score and extracts elites.
      - Builds a new population from a mix of:
        - elites (copied),
        - mutated elites,
        - crossovers between elites,
        - fresh randoms.
  - `save_population(strategies)` / `load_population()` – I/O helpers for the
    generated population under `strategies/generated/`.

- `pool.py`
  - Defines the persistent **strategy pool** abstraction.
  - `StrategyRecord` dataclass:
    - `name`, `symbol`, `timeframe`.
    - `status` – `"candidate"`, `"active"`, `"exploratory"`, `"disabled"`, `"retired"`.
    - `score` – numeric score (e.g. from evaluation metrics).
    - `stats` – evaluation stats dict (including `strategy_explain`), not just
      flat floats.
      This now includes explicit routing metadata under
      `stats["strategy_explain"]["meta"]`, such as:
      - `best_regime` / `worst_regime`
      - `best_session` / `worst_session`
      - `allowed_regimes` / `blocked_regimes`
      - `allowed_sessions` / `blocked_sessions`
      - `routing_confidence`
  - `StrategyPool` dataclass:
    - `strategies: Dict[str, StrategyRecord]` – keyed by strategy name.
    - `to_dict()` / `from_dict()` – JSON serialization helpers with defensive
      handling of corrupt/mismatched records (bad entries are skipped with a
      warning instead of crashing the whole pool load).
    - `upsert_strategy(strategy, stats, score, status="candidate")` – insert or
      update a strategy in the pool.
    - `set_status(name, status)` – manually change status.
    - `top_strategies(status_filter="candidate", limit=10)` – convenience
      method to fetch the highest scoring strategies.
    - `prune(max_inactive=_MAX_INACTIVE_STRATEGIES)` – removes the lowest-scoring
      **inactive** strategies (candidate/disabled/retired) beyond a size cap,
      while never pruning `active` / `exploratory` entries. This prevents
      `pool_state.json` from growing without bound.
  - File layout:
    - `pool_state.json` stores the serialized pool, managed via:
      - `load_pool()` – load or create an empty pool.
      - `save_pool(pool)` – persist pool to disk.

## Directories

- `strategies/generated/`
  - JSON files, one per generated strategy, named `{strategy_name}.json`.
  - Used by:
    - Research/evolution (`evolve_population`, `load_population`).
    - Live execution (`execution.signals.execute_signals_for_symbol`) to
      reconstruct `StrategyDefinition` for `active` and `exploratory` strategies.

- `strategies/pool_state.json`
  - Serialized `StrategyPool`.
  - Updated by `scheduler.job_research_strategies()` on each research cycle.
  - After each cycle, additional **live performance-based degradation rules**
    are applied using aggregated stats from
    `execution/strategy_live_stats.json`, demoting clearly underperforming
    `active` strategies back to `candidate`.
  - Periodically pruned (via `StrategyPool.prune`) to keep the number of
    inactive strategies bounded.

## How It’s Used

- `scheduler/job_research_strategies()`:
  - Loads `StrategyPool` via `load_pool()`.
  - Selects best parent strategies for a symbol/timeframe using **hybrid**
    scores (base score + small memory-based bonus from `ResearchMemory`).
  - Uses `evolve_population(...)` to generate new candidate strategies.
  - Backtests and evaluates each candidate.
  - Calls `pool.upsert_strategy(...)` with status determined by promotion logic
    (active/candidate/exploratory/disabled).
  - Stores evaluation results in vector memory.
  - Finally, applies a conservative **live degradation pass** that:
    - reads `execution/strategy_live_stats.json`,
    - for each `active` strategy with enough live trades and good backtests,
      demotes it to `candidate` if live returns are significantly negative or
      far below backtest expectations.
    - sends a WhatsApp alert via `send_strategy_degradation_alert(...)` when a
      strategy is degraded.
  - Calls `pool.prune(...)` to remove excess inactive strategies and then
    `save_pool(pool)` at the end of the job.

- `execution/signals.execute_signals_for_symbol(...)`:
  - Reads `StrategyPool` via `load_pool()`.
  - Filters for `status in {"active", "exploratory"}` for the given symbol/timeframe.
  - Computes a regime-specific edge per strategy from
    `strategy_explain.regime_pnl[regime_label].return_pct` and
    prefers strategies with better historical performance in the **current regime**.
  - Optionally caps the number of strategies considered per run (e.g. top 5 active,
    top 3 exploratory) to keep live behaviour focused.
  - Loads each selected `StrategyDefinition` from `strategies/generated/`.
  - Evaluates entry rules on the latest feature row and routes allowed signals to
    `engine.execute_trade(...)`, using **normal risk** for `active` strategies and a
    **reduced risk tier** for `exploratory` strategies.

## Gotchas / Notes

- `strategies/generated/` is intended for **generated artifacts**, not
  hand-crafted configs; it is ignored in Git to avoid noise and bloat.
- If a strategy in the pool cannot be loaded from disk (e.g. missing JSON
  file), it is skipped and an exception is logged.
- Strategy names are used as IDs and must be unique; collisions will overwrite
  previous records in the pool.
- Live degradation rules are intentionally conservative and one-sided: they
  only downgrade strategies that are clearly failing; they do not auto-upgrade
  based on live performance alone.
- `StrategyPool.from_dict(...)` is defensive: a single corrupt record in
  `pool_state.json` no longer crashes the whole scheduler; the bad record is
  skipped with a warning.

## Changelog (Docs)

- 2026-03-21: Documented ATR-based SL/TP support, defensive pool loading,
  pool pruning, and the live degradation + WhatsApp alert integration.
