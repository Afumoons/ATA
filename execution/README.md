# execution/ – Live Trade Execution, Daily State & Live Monitoring

## Purpose

This module is the live side of the system.

It is responsible for:

- converting eligible strategy signals into real MT5 orders
- enforcing live routing and risk gates before orders are sent
- tracking daily account state and drawdown
- wiring closed MT5 deals back into account and strategy state
- maintaining open-trade and per-strategy live snapshots

Recent Track B / Track C work plus the latest post-audit hardening significantly
strengthen this module by making it more explicitly **routing-aware**,
**stateful**, **observable**, more robust in closed-deal attribution, and more
proactive about strategy-level decay.

## Key Responsibilities

### 1) Order execution

- validate proposed trades against account-level risk rules
- size and submit MT5 orders
- log executed trades

### 2) Live signal gating

- apply daily limits
- enforce one-open-position-per-strategy slot rules
- apply session and regime routing gates
- apply volatility mismatch and confidence gates
- block negative-edge exploratory fallback from forcing clearly bad candidates through
- rank strategies by edge
- run separate exposure tiers for `active` vs `exploratory`

### 3) State tracking

- maintain daily PnL and trade counts
- maintain equity history and peak equity
- process closed MT5 deals exactly once
- aggregate live PnL by strategy
- snapshot open trades and ticket-to-strategy mappings

## Key Files

### `engine.py`

Thin wrapper around MT5 order placement.

Responsibilities:

- compute volume from risk inputs and SL distance
- call `risk.manager.validate_trade(...)`
- place the order through MT5 when allowed
- log successful executions to `trades.log`
- tag trades with strategy-identifying comments for later monitoring

### `signals.py`

This is the core **live routing layer**.

It bridges saved research outputs into real-time execution.

Important behavior includes:

- reading the latest feature row and routing context
- using `can_open_new_trade(...)` to enforce daily limits
- using `strategy_has_open_position(...)` to prevent accidental re-entry/pyramiding
- selecting `active` and `exploratory` strategies for the current symbol/timeframe
- applying session hard gates from `strategy_explain.meta`
- applying regime allow/block policies from `strategy_explain.meta`
- expanding coarse regimes into candidate labels using structured regime context
- applying volatility mismatch guards
- using `regime_confidence` to reject weak-confidence contexts
- loading live routing switches/thresholds from `autonomous_trading_ai.config.routing_config`
- ranking strategies by regime-specific edge
- executing with normal risk for `active` and reduced risk for `exploratory`
- returning structured outcome info so the scheduler can log why trades were or were not taken

This file is where pass 3’s specialist-routing behavior becomes operational.

### `live_state_utils.py`

Maintains day-level risk/account state.

Main roles:

- read/write `live_state.json`
- track:
  - `daily_pnl`
  - `daily_return_pct`
  - `trades_today`
  - `locked_for_day`
- update state when new closed PnL arrives
- enforce daily trade-count and drawdown limits
- check whether a strategy already has an open live slot

### `live_monitor.py`

Monitors the actual account and synchronizes MT5 reality back into the system.

Responsibilities:

- update `equity_history.json`
- maintain `peak_equity`
- query MT5 closed deals
- register newly closed trade PnL into daily state
- update per-strategy live PnL stats
- use broader attribution fallbacks (`order`, `position_id`, deal ticket)
- write unmatched closed-deal audit rows when attribution fails
- enforce the portfolio circuit breaker by disabling live-tier strategies
  (`active` and `exploratory`) when drawdown breaches the configured threshold

### `live_observer.py`

Observation/snapshot utilities for the live account.

This file supports lightweight views such as open-trade snapshots so the system
and human operator can inspect current exposure without reconstructing it from
raw MT5 calls each time.

### `strategy_live_stats.py`

Maintains aggregated per-strategy live performance.

Typical fields include:

- total PnL
- number of trades
- average PnL
- last update time
- recent rolling window of trade outcomes

These stats are used downstream by the scheduler’s degradation logic.

Manual trades are now represented explicitly as `manual_*` buckets inside
`strategy_live_stats.json` rather than being silently dropped or mistaken for
engine strategies. The current convention is:

- `manual_test_xau` for explicit manual test executions that were opened with that name
- `manual_unmatched_<SYMBOL>` for closed MT5 deals that could not be matched back to the
  engine ticket map (for example Afu's manual trades in `unmatched_closed_deals.json`)

These manual buckets are bookkeeping-only. Engine governance / live decay /
strategy-quality logic must ignore them so they do not contaminate automated
strategy health decisions.

### `live_decay.py`

Provides a lightweight proactive decay-assessment layer on top of realized live
strategy stats.

Current role:

- read rolling recent outcomes from `strategy_live_stats.json`
- identify weak live behavior before account-level damage accumulates
- emit warning/degrade-style outcomes for scheduler/or operator use
- stay intentionally conservative (soft governance first, not blind hard disable)

## State Files

Pass 3 makes the execution state surface more explicit.

### `execution/trades.log`

Append-only log of executed live orders.

### `execution/live_state.json`

Daily account-state snapshot, including:

- date
- starting/current equity
- daily PnL
- daily return %
- number of closed trades today
- day lock status

### `execution/equity_history.json`

Time-series equity history plus peak-equity tracking.

Used for portfolio drawdown monitoring and circuit-breaker enforcement.

### `execution/closed_trades_state.json`

Internal bookkeeping for closed-deal processing.

Used to prevent double-counting the same MT5 deal.

### `execution/strategy_live_stats.json`

Aggregated live performance by strategy.

Used by degradation logic and operator inspection.

### `execution/open_trades.json`

Snapshot of current open trades for quick inspection and tooling.

### `execution/ticket_strategy_map.json`

Maps MT5 trade identifiers back to strategy identity when needed for later
attribution and monitoring flows.

### `execution/unmatched_closed_deals.json`

Audit artifact for closed MT5 deals that could not be mapped back to a strategy.
Useful for diagnosing broker-id lineage mismatches.

Each unmatched row may also include a `manual_bucket` field showing the
explicit bucket name used in `strategy_live_stats.json` (for example
`manual_unmatched_XAUUSDC`).

### `execution/pool_audit_trail.json`

Audit artifact for pool/circuit-breaker actions such as pruning, dedup
replacement, and bulk disable events.

## Pass 3 Live Routing Model

The live execution path now behaves more like a specialist dispatcher than a
simple “top-score strategy executor.”

It can combine:

- current session context
- current regime context
- volatility regime
- regime confidence
- strategy allow/block metadata
- backtest-derived regime edge
- tiered exposure sizing

So a strategy may be skipped even if it has a high total score, because:

- it is blocked for the current session
- it is blocked for the current regime
- the volatility state is a poor fit
- confidence is too low
- it already has an open live slot
- daily limits are hit
- no current entry trigger exists
- exploratory fallback would otherwise have forced through a still-negative edge candidate

That is intentional. Pass 3 favors **controlled specialist deployment** over
looser general execution.

## Routing Config Reference

All pass-3 routing switches live in `autonomous_trading_ai.config.RoutingConfig`.
These settings control how strict the live router is after a strategy already
made it into the pool.

### Quick mental model

- **best session** = the single session where the strategy looked strongest
- **allowed sessions** = sessions the strategy is permitted to trade in
- **blocked sessions** = sessions the strategy should avoid
- **allowed regimes** = market regimes the strategy is permitted to trade in
- **blocked regimes** = market regimes the strategy should avoid

Think of them as different layers, not duplicates.

### Session config: what is the difference?

#### `require_best_session_for_entry`

This is the **strictest** session rule.

If `True`:
- the strategy can only trade in its one recorded `best_session`
- example: if best session is `london`, it will be blocked in `asia` and `new_york`

If `False`:
- the strategy may still trade outside its single best session
- but it can still be restricted by `allowed_sessions` or `blocked_sessions`

Practical meaning:
- use `True` when you want highly specialist deployment
- use `False` when you want to relax the system and allow “good enough outside best session” behavior

#### `enforce_allowed_sessions`

This checks the strategy's explicit session allowlist.

If `True`:
- and the strategy has `allowed_sessions=[...]`
- the current session must be in that list

If `False`:
- ignore the strategy's allowlist completely

Example:
- `allowed_sessions=["london", "new_york"]`
- current session = `asia`
- if `enforce_allowed_sessions=True` → blocked
- if `enforce_allowed_sessions=False` → this allowlist does not block the trade

Practical meaning:
- this is a **whitelist-style** filter
- useful when research found the strategy should only operate in some sessions

#### `enforce_blocked_sessions`

This checks the strategy's explicit session blocklist.

If `True`:
- and the strategy has `blocked_sessions=[...]`
- the current session must not be in that list

If `False`:
- ignore the strategy's session blocklist completely

Example:
- `blocked_sessions=["asia"]`
- current session = `asia`
- if `enforce_blocked_sessions=True` → blocked
- if `enforce_blocked_sessions=False` → this blocklist does not block the trade

Practical meaning:
- this is a **blacklist-style** filter
- useful when a strategy is broadly okay, except for a few bad sessions

### Best-session vs allowed-session vs blocked-session

These three settings are related, but not the same:

- `require_best_session_for_entry=True`
  - only one session is acceptable: the single best one
- `enforce_allowed_sessions=True`
  - several sessions may be acceptable if they are in the allowlist
- `enforce_blocked_sessions=True`
  - several sessions may be acceptable except the explicitly blocked ones

Compact examples:

- Best session = `london`
- Allowed sessions = `[london, new_york]`
- Blocked sessions = `[asia]`

If current session is:
- `london`
  - best-session gate: pass
  - allowed-session gate: pass
  - blocked-session gate: pass
- `new_york`
  - best-session gate: fail
  - allowed-session gate: pass
  - blocked-session gate: pass
- `asia`
  - best-session gate: fail
  - allowed-session gate: fail
  - blocked-session gate: fail

So:
- **best session** is the narrowest rule
- **allowed sessions** is a positive allowlist
- **blocked sessions** is a negative denylist

### Regime config

#### `enforce_allowed_regimes`

If `True`:
- and the strategy defines `allowed_regimes=[...]`
- at least one of the current candidate regimes must be in that list

If `False`:
- ignore the regime allowlist

Practical meaning:
- keeps a strategy inside the market conditions it was designed for

#### `enforce_blocked_regimes`

If `True`:
- and the strategy defines `blocked_regimes=[...]`
- any overlap with the current candidate regimes will block the strategy

If `False`:
- ignore the regime blocklist

Practical meaning:
- prevents known-bad deployment contexts

### Confidence config

#### `min_regime_confidence_active`

Minimum required regime-confidence score for `active` routing.

- higher = stricter, fewer trades, more confidence required
- lower = looser, more trades allowed under uncertain classification

Recommended interpretation:
- keep this relatively strict because `active` is the main risk tier

#### `min_regime_confidence_exploratory`

Minimum required regime-confidence score for `exploratory` routing.

- higher = exploratory behaves more conservatively
- lower = more exploratory participation in uncertain conditions

Recommended interpretation:
- usually lower than `active`, because exploratory is intentionally looser and smaller sized

### Volatility config

#### `enforce_volatility_mismatch_gate`

If `True`:
- block strategies whose metadata says they are a poor fit for the current volatility state

If `False`:
- skip the volatility mismatch protection

Practical meaning:
- protects against using calm-market specialists in event-driven/high-vol conditions and similar mismatches

### Edge threshold config

#### `active_regime_edge_threshold`

Minimum regime-specific edge required for `active` strategies after they already pass earlier gates.

- higher = stricter quality bar, fewer active strategies survive
- lower = more active strategies survive

#### `exploratory_regime_edge_threshold`

Minimum regime-specific edge required for `exploratory` strategies.

- higher = exploratory becomes more selective
- lower = exploratory admits weaker candidates

#### `keep_best_exploratory_on_empty_edge_filter`

If `True`:
- when all exploratory candidates fail the edge threshold, keep the single best one anyway

If `False`:
- exploratory stays empty if nothing beats the threshold

Practical meaning:
- `True` preserves controlled experimentation
- `False` makes exploratory behave more like a strict reject-only tier

### Operator guidance

If you want the system to stay very strict:
- keep `require_best_session_for_entry=True`
- keep all allow/block enforcement enabled
- keep confidence thresholds relatively high
- keep volatility mismatch gate enabled

If you want to relax the system slightly without removing all discipline:
- first consider setting `require_best_session_for_entry=False`
- keep allow/block enforcement on
- only lower confidence/edge thresholds gradually

If you want to experiment more aggressively:
- relax best-session enforcement first
- then evaluate whether allow/block lists are too restrictive
- avoid disabling too many gates at once, or you lose the meaning of specialist routing

## How It’s Used

### `scheduler.job_execute_signals()`

- loads features and strategy pool
- checks macro-news lockout
- computes live risk tier
- calls `signals.execute_signals_for_symbol(...)`

### `scheduler.job_live_monitor()`

- calls `live_monitor.update_live_stats()`
- updates equity history, daily state, live strategy stats, and circuit-breaker state
- may also refresh open-trade snapshots depending on observer wiring

### `risk/manager.py`

- validates proposed trades before MT5 submission

## Gotchas / Notes

- This module operates on **real account state**; debugging scripts can cause
  real actions if they invoke execution code.
- Daily state is account-level, not strategy-level.
- Per-strategy live stats are intentionally lighter than a full strategy-level
  equity curve model.
- MT5 deal-history availability matters; truncated broker/terminal history can
  affect reconstruction.
- The circuit breaker currently acts by disabling `active` strategies in the
  pool; that is a deliberate safety mechanism, not just a log event.

## Changelog (Docs)

- 2026-04-04: Updated for negative-edge exploratory fallback guard and proactive live decay detection v1.
- 2026-04-03: Updated for Track B attribution/audit improvements and Track C execution-facing exit/governance context.

- 2026-03-21: Documented daily guardrails, news lockout, circuit breaker,
  and active/exploratory risk tiers.
- 2026-03-27: Updated for pass 3 with explicit routing behavior, expanded live
  state artifacts (`open_trades.json`, `ticket_strategy_map.json`, observer
  flows), and stronger emphasis on the specialist-dispatch model.
