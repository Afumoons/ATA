# strategies/ – Definitions, Generation, Pool & Routing Metadata

## Purpose

This module defines how strategies are represented, created, evolved, stored,
and governed over time.

It provides:

- a serializable strategy definition format
- random generation and evolutionary mutation/crossover
- persistent pool storage and status management
- metadata surfaces that connect research outputs to live-routing behavior

Pass 3 makes this module more important because the strategy pool is no longer
just a ranked list. It is now a **specialist inventory with explicit routing
hints and live-governance state**.

## Key Files

### `base.py`

Defines `StrategyDefinition`.

Core fields include:

- `name`
- `symbol`
- `timeframe`
- `long_entry_rule`
- `short_entry_rule`
- `exit_rule`
- `stop_loss_pips`
- `take_profit_pips`
- optional `sl_atr_mult`
- optional `tp_atr_mult`
- free-form `params`

This dataclass is intentionally declarative. It stores strategy logic as data,
not executable strategy classes.

### `generator.py`

Creates fresh strategy definitions.

Current strategy-generation bias includes:

- MA-based trend rules
- RSI/range-style rules
- legacy Ichimoku/Fibonacci-based templates
- explicit XAU specialist families such as impulse/pullback and session continuation

For core 15m markets, generation is biased toward simpler, more interpretable
families with more explicit family/playbook metadata.

The generator also stores lightweight family metadata in `params`, such as:

- long/short family type
- regime bias
- preferred symbol/timeframe
- exit archetype (`state_change`, `time_stop`, `session_guard`)
- whether the strategy has a time stop or session exit guard

That makes later analysis easier without re-parsing rule strings.

### `evolution.py`

Handles evolutionary search.

Important capabilities:

- elite retention
- parameter mutation
- crossover between parents
- fallback fresh-random generation

Used by the scheduler’s research loop to build new candidate populations from
higher-quality pool members.

### `pool.py`

Stores and manages the persistent `StrategyPool`.

Important structures:

- `StrategyRecord`
- `StrategyPool`

Each record includes:

- identity (`name`, `symbol`, `timeframe`)
- `status`
- numeric `score`
- `stats`

The `stats` blob now matters a lot because it can include the full
`strategy_explain`, including pass 3 routing metadata.

Important capabilities include:

- `upsert_strategy(...)`
- `set_status(...)`
- `top_strategies(...)`
- `prune(...)`
- `load_pool()` / `save_pool()`

### `live_manifest.py`

Provides a live-facing manifest / compact view of strategy inventory for
execution or operator-facing inspection.

This helps bridge the rich stored pool data into a more operational surface for
live workflows.

## Strategy Status Model

The pool can track statuses such as:

- `active`
- `exploratory`
- `candidate`
- `disabled`
- `retired`

A rough interpretation:

- `active` → trusted enough for normal live exposure
- `exploratory` → allowed for limited live discovery with reduced risk
- `candidate` → promising but not yet approved for live use
- `disabled` → currently disallowed
- `retired` → historical / no longer in active rotation

## Pass 3 Role

Pass 3 turns the strategy module into a **routing-governance layer**.

A strategy record can now carry explicit specialist metadata through
`stats["strategy_explain"]["meta"]`, such as:

- `allowed_regimes`
- `blocked_regimes`
- `allowed_sessions`
- `blocked_sessions`
- `best_regime`
- `worst_regime`
- `best_session`
- `worst_session`
- `routing_confidence`

That means the pool is not just answering:

- “which strategies scored highly?”

It is also helping answer:

- “which strategies are allowed here?”
- “which strategies are specialists vs poor fits?”
- “which strategies should receive reduced exposure?”

## Live Feedback Loop

The strategy layer is also affected by live performance.

After research updates, the scheduler can run a conservative degradation pass
using `execution/strategy_live_stats.json`.

This can demote underperforming `active` strategies back to `candidate` when:

- enough live evidence exists
- live returns are clearly poor
- recent trade behavior is meaningfully weak

That makes the pool a **living governance artifact**, not a static research dump.

## Storage Layout

### `strategies/generated/`

Generated JSON strategy definitions.

Used to reconstruct `StrategyDefinition` objects during research and live
execution.

### `strategies/pool_state.json`

Persistent serialized strategy pool.

This is the main long-lived inventory of strategy state.

### `strategies/pool_state.backup-*.json`

Backup snapshots of the pool state.

Useful during manual maintenance or recovery.

## How It’s Used

### In research

`scheduler.job_research_strategies()`:

- loads the pool
- selects parents
- evolves/generates candidates
- backtests and evaluates them
- stores score, stats, and status
- writes new research memory entries
- applies live degradation pass
- prunes excess inactive entries
- saves the final pool

### In live execution

`execution.signals.execute_signals_for_symbol(...)`:

- loads strategies from the pool
- filters to `active` / `exploratory`
- reads routing metadata and edge behavior
- loads definition JSONs from `generated/`
- evaluates entries on the latest feature row

## Gotchas / Notes

- Strategy names are IDs; collisions overwrite existing records.
- Missing generated JSON files will cause a pool record to be skipped by live execution.
- Generated artifacts should stay machine-friendly and reproducible.
- Pool loading is intentionally defensive so one corrupt record does not kill the
  whole system.
- Live degradation is intentionally one-sided and conservative; it removes trust
  more readily than it grants it.

## Changelog (Docs)

- 2026-04-03: Updated for Track A / C generator changes, explicit XAU playbooks, and exit-archetype metadata.

- 2026-03-21: Documented ATR-based SL/TP support, defensive pool loading,
  pruning, and live degradation integration.
- 2026-03-27: Updated for pass 3 with explicit routing-metadata framing,
  `live_manifest.py`, specialist inventory language, and stronger explanation of
  the strategy pool as a governance surface.