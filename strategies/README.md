# strategies/ – Definitions, Generation & Pool

## Purpose

This module defines **how strategies are represented**, how new ones are
generated/evolved, and how the global strategy pool is stored.

It provides:

- A serializable `StrategyDefinition` config object (no executable code).
- Tools to generate and mutate strategies (Ichimoku + Fibonacci-biased).
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
    - `params` – free-form dict used by generator/evolution.
  - Methods:
    - `to_dict()` / `from_dict()` – JSON-serializable representation.

- `generator.py`
  - Focused on **initial strategy creation**.
  - Uses Ichimoku/Fibonacci-flavored rule templates:
    - `LONG_ENTRY_TEMPLATES`, `SHORT_ENTRY_TEMPLATES`, `EXIT_TEMPLATES`.
  - `random_strategy(symbol, timeframe)`:
    - Samples template parameters (`trend_min`, `rsi_exit`, `trend_exit`).
    - Builds rule strings by formatting templates with these params.
    - Picks SL/TP from a discrete set of pip values.
    - Produces a `StrategyDefinition` with a name like
      `"ichifib_{symbol}_{timeframe}_{rand_id}"`.
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
    - `status` – `"candidate"`, `"active"`, `"disabled"`, `"retired"`.
    - `score` – numeric score (e.g. from evaluation metrics).
    - `stats` – evaluation stats dict (including `strategy_explain`).
  - `StrategyPool` dataclass:
    - `strategies: Dict[str, StrategyRecord]` – keyed by strategy name.
    - `to_dict()` / `from_dict()` – JSON serialization helpers.
    - `upsert_strategy(strategy, stats, score, status="candidate")` – insert or
      update a strategy in the pool.
    - `set_status(name, status)` – manually change status.
    - `top_strategies(status_filter="candidate", limit=10)` – convenience
      method to fetch the highest scoring strategies.
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
      reconstruct `StrategyDefinition` for `active` strategies.

- `strategies/pool_state.json`
  - Serialized `StrategyPool`.
  - Updated by `scheduler.job_research_strategies()` on each research cycle.
  - After each cycle, additional **live performance-based degradation rules**
    are applied using aggregated stats from
    `execution/strategy_live_stats.json`, demoting clearly underperforming
    `active` strategies back to `candidate`.

## How It’s Used

- `scheduler/job_research_strategies()`:
  - Loads `StrategyPool` via `load_pool()`.
  - Selects best parent strategies for a symbol/timeframe using their scores.
  - Uses `evolve_population(...)` to generate new candidate strategies.
  - Backtests and evaluates each candidate.
  - Calls `pool.upsert_strategy(...)` with status determined by promotion logic
    (active/candidate/disabled).
  - Stores evaluation results in vector memory.
  - Finally, applies a conservative **live degradation pass** that:
    - reads `execution/strategy_live_stats.json`,
    - for each `active` strategy with enough live trades and good backtests,
      demotes it to `candidate` if live returns are significantly negative or
      far below backtest expectations.
  - Calls `save_pool(pool)` at the end of the job.

- `execution/signals.execute_signals_for_symbol(...)`:
  - Reads `StrategyPool` via `load_pool()`.
  - Filters for `status == "active"` for the given symbol/timeframe.
  - Loads each active `StrategyDefinition` from `strategies/generated/`.
  - Evaluates entry rules on the latest feature row and routes allowed signals
    to `engine.execute_trade(...)`.

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
