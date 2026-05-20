# scheduler/ – Orchestration, Background Jobs & System Loop

## Purpose

This module is the **orchestrator** for `autonomous_trading_ai`.

It wires together:

- market and news data refresh
- feature / regime generation
- strategy research and evaluation
- live signal execution
- live monitoring and safety actions
- outbound news / degradation alerts
- optional Telegram mentor-signal listener autostart

If the rest of the project is a collection of subsystems, `scheduler/` is what
turns them into a continuously running machine.

## Key File

### `main.py`

Contains:

- the managed symbol/timeframe configuration
- all recurring job definitions
- scheduler startup and shutdown logic
- the command-line runtime entrypoint

## Core Jobs

### `job_update_data()`

Refreshes raw OHLC, feature sets, and regime outputs.

Typical flow per symbol:

1. fetch OHLC from MT5
2. save raw parquet
3. compute features
4. add regime fields
5. save final feature parquet

### `job_research_strategies()`

Runs the research/evolution loop.

Typical flow:

1. load features
2. load strategy pool
3. query research memory for neighbor guidance
4. rank/select parents with family-aware stratification
5. evolve/generate candidate strategies
6. reject structural duplicates and semantic near-duplicates before heavier checks
7. cheap-prescreen candidates before heavier checks
8. backtest and evaluate each candidate
9. apply memory-guided dead-zone penalties, novelty metadata, and stricter exit-fragility checks
10. run robustness checks
11. assign pool status
12. persist results into pool + vector memory
13. run live-degradation pass on current active strategies
14. save/prune pool

Recent adjacent hardening around this job family also added:

- runtime protection against forcing exploratory candidates through fallback when best regime edge is still negative
- concentration-aware selection at the execution-stage pool-building layer

This job is especially important because it persists routing-related metadata
from `strategy_explain.meta`, not just raw performance stats, and now also
includes stricter research gating, novelty metrics, and motif metadata.

### `job_execute_signals()`

Runs the live execution loop.

Typical flow:

1. load current pool
2. compute effective live risk cap
3. load latest features for each symbol
4. skip execution if `in_news_lockout` is active
5. build a diversified execution-stage candidate pool so runtime selection is less clustered by family/regime/motif
6. hand off to `execution.signals.execute_signals_for_symbol(...)`
7. log detailed trade / skip / reject reasons

This is where the scheduler activates pass 3’s specialist-routing behavior.

### `job_live_monitor()`

Synchronizes live account reality back into system state.

Typical responsibilities:

- append equity history
- update peak equity
- process newly closed MT5 deals
- refresh daily state
- refresh per-strategy live stats
- run proactive live decay assessment from recent realized strategy outcomes
- enforce portfolio-level circuit-breaker actions
- support open-trade observation flows

### `job_update_news()`

Refreshes the local macro-news store.

Typical responsibilities:

- call `data.news_collector.update_news_events()`
- update `data/raw/news_events.parquet`
- optionally summarize upcoming high-impact events
- feed alerting flows

### `job_news_alert()`

Checks for imminent macro events and sends notifications through the notifier
path using cooldown logic.

## Pass 3 Role

Pass 3 makes the scheduler more than a timer. It is now the **policy executor**
that coordinates:

- structured regime-aware research
- specialist-aware live routing
- degradation feedback from live performance
- news-aware execution suppression
- stateful safety actions

A lot of the project’s practical behavior is now determined not just by module
capabilities, but by **how this scheduler sequences them**.

## Lifecycle

### `start_scheduler()`

Typical startup behavior:

- optionally respect `scheduler_config.enable_scheduler`
- initialize MT5 once
- create the APScheduler instance
- register recurring jobs
- start the background scheduler
- autostart the Telegram signal listener in a daemon thread when `TELEGRAM_API_ID` and `TELEGRAM_API_HASH` are available from environment/`.env`

### `shutdown_scheduler(sched)`

Typical shutdown behavior:

- stop APScheduler cleanly
- close MT5 connection via `shutdown_mt5()`

### CLI entrypoint

Run:

```powershell
cd C:\laragon\www
python -m autonomous_trading_ai.scheduler.main
```

This starts the loop and keeps it alive until interrupted. If Telegram credentials exist in `C:\laragon\www\autonomous_trading_ai\.env`, the `japsku` signal listener also starts automatically in shadow mode unless disabled.

## Configuration Notes

The scheduler owns practical runtime choices such as:

- managed symbols
- managed timeframe
- job frequencies
- effective live risk cap passed into execution

These are typically defined in `main.py` plus shared config from `config.py`.

Telegram signal listener env knobs live in `.env` / process environment:

```text
TELEGRAM_API_ID=...
TELEGRAM_API_HASH=...
TELEGRAM_SIGNAL_SESSION=ata_telegram_signals
ATA_TELEGRAM_SIGNAL_AUTOSTART=true
ATA_TELEGRAM_SIGNAL_CHANNEL=japsku
ATA_TELEGRAM_SIGNAL_MODE=auto_live
ATA_TELEGRAM_SIGNAL_HISTORY=0
# Demo auto-live currently uses both mode=auto_live and:
ATA_TELEGRAM_SIGNAL_LIVE=true
```

Set `ATA_TELEGRAM_SIGNAL_AUTOSTART=false` to run scheduler without the Telegram listener.

## How It Connects the Project

The scheduler is the place where these modules actually meet:

- `data/`
- `research/`
- `strategies/`
- `backtests/`
- `execution/`
- `risk/`
- `vector_memory/`
- `notifications/`

If you want to understand “what the system actually does over time,” this is
usually the first file to inspect.

## Gotchas / Notes

- Job timing is typically UTC; keep timezone assumptions consistent.
- Research jobs are heavier than execution/data refresh jobs and usually run
  less often.
- Missing features or temporary data issues should degrade gracefully per symbol.
- Alert and news failures should not stop the core trading loop.
- Because pass 3 introduces more nuanced live gating, good logging from this
  module matters more than before for debugging why a trade did or didn’t happen.

## Changelog (Docs)

- 2026-04-08: Updated for structural/semantic dedup, family-stratified parent selection, novelty metadata, and motif-aware runtime diversification.
- 2026-04-04: Updated for execution-stage concentration control and proactive live decay assessment.
- 2026-04-03: Updated for Track A / C research-gating behavior (cheap prescreen, dead-zone penalties, and stricter exit-fragility checks).

- 2026-03-21: Documented job structure, news jobs, lockout flow, and live
  degradation integration.
- 2026-03-27: Updated for pass 3 to emphasize scheduler sequencing,
  specialist-routing orchestration, and policy/state coordination.

- 2026-05-20: Documented Telegram signal listener autostart from `scheduler.main`, `.env` knobs, and live-mode guard flags.
- 2026-05-20: Updated env example for demo auto-live arming.
