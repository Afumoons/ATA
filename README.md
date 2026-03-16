# autonomous_trading_ai – System Overview

This package is a **full-stack autonomous trading agent** built around:

- MetaTrader 5 for execution and data.
- A research loop that evolves strategies over time.
- Risk-aware live execution.
- Vector-backed research memory for analysis.

This README gives the high-level map. Each submodule has its own
`README.md` with more detail.

## High-Level Pipeline

1. **Data Ingestion (`data/`)**
   - `collector_mt5.py` connects to MT5 and fetches OHLCV for configured
     symbols/timeframes.
   - Raw bars are saved under `data/raw/{symbol}_{timeframe}_ohlc.parquet`.

2. **Feature & Regime Research (`research/`)**
   - `features.py` turns raw OHLC into feature-rich datasets:
     RSI, ATR, volatility, trend strength, Ichimoku, Fibonacci zones,
     optional macro news context.
   - `regime.py` classifies bars into market regimes (trend/range/vol spike,
     etc.), and adds a legacy `regime` label used in backtests.
   - Feature files live under `data/features/{symbol}_{timeframe}_features.parquet`.

3. **Strategy Generation & Pool (`strategies/`)**
   - `base.py` defines the `StrategyDefinition` config (rules + SL/TP + params).
   - `generator.py` creates Ichimoku/Fibonacci-biased strategies as JSON files
     in `strategies/generated/`.
   - `evolution.py` evolves strategies over time using an elite + mutation +
     crossover scheme.
   - `pool.py` maintains the persistent `StrategyPool` in `strategies/pool_state.json`,
     tracking stats, scores, and statuses (`active` / `candidate` / `disabled`).

4. **Backtesting, Evaluation & Explainability (`backtests/`)**
   - `engine.py` runs bar-by-bar backtests, applying risk-based sizing and
     trading costs, producing `BacktestResult` objects.
   - `explain.py` builds `strategy_explain` structures describing behavior by
     regime, session, risk characteristics, stability, and news context.
   - `evaluation.py` turns stats + explain into a numeric score and
     acceptance decision.
   - `walkforward.py` and `monte_carlo.py` provide robustness checks
     (out-of-sample and PnL stress tests).

5. **Risk Management (`risk/`)**
   - `manager.py` enforces account-level rules before any trade is sent:
     - max risk % per trade,
     - max concurrent open positions,
     - max portfolio drawdown vs `equity_peak`.
   - Daily loss / trade caps are handled separately in
     `execution/live_state_utils.py`.

6. **Live Execution & Daily State (`execution/`)**
   - `engine.py` is the MT5 execution layer; it sizes trades, calls the
     risk manager, and logs to `execution/trades.log`.
   - `signals.py` turns the latest features + active strategies into live
     signals and calls `engine.execute_trade(...)` (subject to daily limits).
   - `live_state_utils.py` maintains per-day metrics in `execution/live_state.json`:
     `daily_pnl`, `daily_return_pct`, `trades_today`, and a daily lockout flag.
   - `live_monitor.py` tracks equity history in `execution/equity_history.json`,
     computes drawdown, optionally disables strategies, and wires **real closed
     MT5 deals** into `DailyState` via `closed_trades_state.json`.
   - `strategy_live_stats.py` maintains aggregated **per-strategy live PnL**
     (including a rolling window of recent PnLs) in
     `execution/strategy_live_stats.json`, which is used for **strategy
     degradation detection**.

7. **Scheduler / Orchestration (`scheduler/`)**
   - `main.py` uses APScheduler to orchestrate the whole loop:
     - `job_update_data` (every 5 min): fetch OHLC → compute features + regime → save.
     - `job_research_strategies` (every 30 min): evolve strategies, backtest,
       evaluate, run robustness checks, update `StrategyPool`, and write to
       `ResearchMemory`. After each cycle, it also applies conservative
       **live-performance-based degradation rules** that demote clearly
       underperforming `active` strategies back to `candidate` based on their
       recent live returns.
     - `job_execute_signals` (every 5 min): load features + active strategies,
       generate/execute signals, enforced by risk + daily limits.
     - `job_live_monitor` (every 5 min): update equity history and daily state,
       enforce portfolio-level safety.
   - `start_scheduler()` / `shutdown_scheduler()` manage MT5 and job lifecycle.

8. **Research Memory (`vector_memory/`)**
   - `research_memory.py` wraps a Chroma `PersistentClient`.
   - `ResearchMemory.store_strategy_result(...)` stores evaluation outputs as
     text + metadata for later semantic search.
   - `ResearchMemory.query_similar(...)` can be used by scripts/agents to find
     strategies with similar stats/behavior.

9. **Configuration (`config.py`)**
   - `RiskConfig` – defines risk thresholds (per-trade, portfolio DD, daily limits).
   - `DataConfig` – default MT5 timeframe and history length.
   - `SchedulerConfig` – enables/disables the APScheduler loop.

## Runtime Flow (Typical)

1. Start MT5 and ensure the desired symbols (e.g. `XAUUSDm`) are visible.
2. Start Chroma (Docker or direct) pointing at the workspace `chroma_data/`.
3. Activate the `autonomous_trading_ai` virtualenv.
4. (Optional) Run a one-shot research cycle:
   - `job_update_data()` then `job_research_strategies()`.
5. Start the scheduler:
   - `python -m autonomous_trading_ai.scheduler.main`.

From there, the system loops indefinitely:

- keeping data/features/regimes fresh,
- evolving and re-evaluating the strategy pool,
- executing signals from `active` strategies with risk/daily guards,
- monitoring equity/drawdown,
- logging research outcomes to Chroma,
- and continuously **pruning underperforming strategies** based on live results.

## Where to Look for Details

- `data/README.md` – MT5 data ingestion.
- `research/README.md` – features & regimes.
- `strategies/README.md` – strategy config, generation & pool.
- `backtests/README.md` – simulation, evaluation, explainability.
- `risk/README.md` – risk manager & config.
- `execution/README.md` – live execution & daily state.
- `scheduler/README.md` – orchestrator & job schedule.
- `vector_memory/README.md` – Chroma-backed research memory.

For operational runbooks (how to start everything from scratch), see:

- `user_instructions/START_AUTONOMOUS_TRADING.md`
- `agent_instruction/SETUP_AUTONOMOUS_TRADING_ENVIRONMENT.md`
