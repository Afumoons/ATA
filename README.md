# autonomous_trading_ai – System Overview

This package is a **full-stack autonomous trading agent** built around:

- MetaTrader 5 for execution and data.
- A research loop that evolves strategies over time.
- Risk-aware live execution with daily guardrails and a circuit breaker.
- Vector-backed research memory for analysis.
- Optional **news-aware behaviour and WhatsApp alerts** via an OpenClaw
  webhook.

This README gives the high-level map. Each submodule has its own
`README.md` with more detail.

## High-Level Pipeline

1. **Data Ingestion & News (`data/`)**
   - `collector_mt5.py` connects to MT5 and fetches OHLCV for configured
     symbols/timeframes.
   - Raw bars are saved under `data/raw/{symbol}_{timeframe}_ohlc.parquet` with
     **UTC-aware** timestamps.
   - `news_collector.py` fetches macro news events from Forex Factory, filters
     for gold-relevant events, and stores them in
     `data/raw/news_events.parquet` for use by the research and
     notifications modules.

2. **Feature, News Context & Regime Research (`research/`)**
   - `features.py` turns raw OHLC into feature-rich datasets:
     RSI, ATR, volatility, ATR-normalised trend strength, Ichimoku,
     Fibonacci zones, and **macro news features** (impact level, time to
     nearest event, news windows, and lockout flags).
   - `regime.py` classifies bars into market regimes (trend/range/vol spike,
     event-driven, etc.) using an ATR-normalised `trend_strength` scale and
     volatility quantiles. It also labels *event-driven* regimes around
     high-impact news.
   - A legacy `regime` label is maintained for backwards compatibility.
   - Feature files live under
     `data/features/{symbol}_{timeframe}_features.parquet`.

3. **Strategy Generation & Pool (`strategies/`)**
   - `base.py` defines the `StrategyDefinition` config (rules + SL/TP + params,
     including optional ATR-based SL/TP multipliers).
   - `generator.py` creates MA/RSI/Ichimoku/Fibonacci-biased strategies as JSON
     files in `strategies/generated/`, with metadata describing each strategy
     family and intended regime.
   - `evolution.py` evolves strategies over time using an elite + mutation +
     crossover scheme, optionally guided by **research memory**: parent scores
     get small bonuses/penalties based on how similar strategies have behaved
     historically on the same symbol/timeframe.
   - `pool.py` maintains the persistent `StrategyPool` in
     `strategies/pool_state.json`, tracking stats, scores, and statuses
     (`active` / `exploratory` / `candidate` / `disabled` / `retired`). It is
     updated both by research cycles and by live-performance-based degradation
     rules, and prunes old inactive strategies to avoid unbounded growth.

4. **Backtesting, Evaluation & Explainability (`backtests/`)**
   - `engine.py` runs bar-by-bar backtests, applying risk-based sizing and
     trading costs, producing `BacktestResult` objects. The default mode is now
     **single-open-position per strategy** (`max_positions_per_strategy=1`),
     with an explicit override available for legacy multi-position studies.
   - `explain.py` builds `strategy_explain` structures describing behaviour by
     regime, session, risk characteristics, stability, and news context.
   - `evaluation.py` turns stats + explain into a numeric score and
     acceptance decision, including bonus/penalty components based on
     regime/session/news behaviour.
   - `walkforward.py` and `monte_carlo.py` provide robustness checks
     (out-of-sample and PnL stress tests).

5. **Risk Management (`risk/`)**
   - `manager.py` enforces account-level rules before any trade is sent:
     - max risk % per trade,
     - max concurrent open positions,
     - max portfolio drawdown vs `equity_peak`.
   - Daily loss / trade caps are handled separately in
     `execution/live_state_utils.py` and enforced via
     `execution/signals.execute_signals_for_symbol(...)` using `risk_config`.
   - Risk thresholds live in `config.py` and are shared across backtests and
     live execution.

6. **Live Execution, Daily State & Circuit Breaker (`execution/`)**
   - `engine.py` is the MT5 execution layer; it sizes trades, calls the
     risk manager, and logs to `execution/trades.log`.
   - `signals.py` turns the latest features + active/exploratory strategies into
     live signals and calls `engine.execute_trade(...)` (subject to daily
     limits, regime filters, and the live **1-strategy-1-open-position** gate).
     It:
     - enforces daily loss / trade-count caps via
       `live_state_utils.can_open_new_trade(...)`,
     - uses regime-specific edge (from `strategy_explain.regime_pnl`) to
       filter strategies per current regime,
     - uses **two risk tiers** (normal risk for `active`, reduced risk for
       `exploratory`).
   - `live_state_utils.py` maintains per-day metrics in `execution/live_state.json`:
     `daily_pnl`, `daily_return_pct`, `trades_today`, and a daily lockout flag.
   - `live_monitor.py` tracks equity history in `execution/equity_history.json`,
     computes drawdown, wires **real closed MT5 deals** into `DailyState` via
     `closed_trades_state.json`, updates per-strategy live stats, and enforces
     a portfolio-level **circuit breaker** using
     `risk_config.max_portfolio_drawdown_pct` (disabling all `active`
     strategies when the drawdown limit is breached).
   - `strategy_live_stats.py` maintains aggregated **per-strategy live PnL**
     (including a rolling window of recent PnLs) in
     `execution/strategy_live_stats.json`, which is used for **strategy
     degradation detection**.

7. **Scheduler / Orchestration (`scheduler/`)**
   - `main.py` uses APScheduler to orchestrate the whole loop:
     - `job_update_data` (every 5 min): fetch OHLC → compute features + regimes → save.
     - `job_research_strategies` (every 30 min): evolve strategies, backtest,
       evaluate, run robustness checks, and update both `StrategyPool` and
       **research memory**:
       - Parents are scored using a hybrid of backtest score + a small
         memory-based bonus/penalty derived from similar past strategies in
         `ResearchMemory` for the same symbol/timeframe.
       - New candidates can be skipped early if memory shows that their
         pattern family has historically performed poorly.
       - After each cycle, conservative **live-performance-based degradation
         rules** demote clearly underperforming `active` strategies back to
         `candidate` based on their aggregated live returns and a rolling
         window of recent trades. Degradation events trigger WhatsApp alerts.
     - `job_execute_signals` (every 5 min): load features + active/exploratory
       strategies, apply **news lockout** (`in_news_lockout`) to avoid trading
       during high-impact events, generate regime-aware signals, and execute
       them subject to risk + daily limits.
     - `job_live_monitor` (every 5 min): update equity history and daily state,
       wire closed deals, enforce the portfolio-level circuit breaker, and keep
       per-strategy live stats up-to-date for the degradation rules.
     - `job_update_news` (daily 06:00 UTC): refresh the Forex Factory calendar
       and summarise upcoming high-impact, gold-relevant events.
     - `job_news_alert` (every 5 min): send near-term WhatsApp alerts for
       imminent high-impact events, with per-event cooldown.
   - `start_scheduler()` / `shutdown_scheduler()` manage MT5 and job lifecycle.

8. **Research Memory (`vector_memory/`)**
   - `research_memory.py` wraps a Chroma `PersistentClient`.
   - `ResearchMemory.store_strategy_result(...)` stores evaluation outputs as
     text + metadata for later semantic search, including the research
     `position_mode` so legacy multi-position results can be separated from the
     newer single-position mode.
   - `ResearchMemory.query_similar(...)` and
     `query_similar_strategies(...)` power the parent bonus and candidate
     veto logic in the research job, with new runs preferring
     `single_position` neighbors when both modes exist.

9. **Notifications & Webhook (`notifications/` & `webhook_server.py`)**
   - `notifications/whatsapp_notifier.py` builds WhatsApp messages (news
     alerts, circuit breaker alerts, strategy degradation alerts) and sends
     them to an OpenClaw-managed webhook.
   - `webhook_server.py` is a small FastAPI app exposing
     `POST /hooks/whatsapp_outbound` with a `?token=` guard. It currently logs
     messages to stdout and is intended to be wired into the OpenClaw gateway.
   - This path is **experimental** and should be treated as best-effort
     alerts; core trading does not depend on it.

10. **Configuration (`config.py`)**
    - `RiskConfig` – defines risk thresholds (per-trade, portfolio DD, daily limits).
    - `DataConfig` – default MT5 timeframe and history length.
    - `SchedulerConfig` – enables/disables the APScheduler loop.

## Runtime Flow (Typical)

1. Start MT5 and ensure the desired symbols (e.g. `XAUUSDm`) are visible.
2. Start Chroma (Docker or direct) pointing at the workspace `chroma_data/`.
3. (Optional) Start the FastAPI webhook server (`webhook_server.py`) and point
   `OPENCLAW_WHATSAPP_WEBHOOK` at it.
4. Activate the `autonomous_trading_ai` virtualenv.
5. (Optional) Run a one-shot research cycle:
   - `job_update_data()` then `job_research_strategies()`.
6. Start the scheduler:
   - `python -m autonomous_trading_ai.scheduler.main`.

From there, the system loops indefinitely:

- keeping data/features/regimes fresh,
- evolving and re-evaluating the strategy pool,
- executing signals from `active`/`exploratory` strategies with risk/daily guards,
- monitoring equity/drawdown and applying a circuit breaker when needed,
- logging research outcomes to Chroma and using them to guide future searches,
- continuously **pruning underperforming strategies** based on live results,
- and (optionally) sending news / degradation alerts via WhatsApp.

## Where to Look for Details

- `data/README.md` – MT5 data ingestion and Forex Factory news.
- `research/README.md` – features, news context & regimes.
- `strategies/README.md` – strategy config, generation, pool & live degradation.
- `backtests/README.md` – simulation, evaluation, explainability.
- `risk/README.md` – risk manager, daily guardrails & circuit breaker config.
- `execution/README.md` – live execution, news lockout & daily state.
- `scheduler/README.md` – orchestrator, job schedule, news/alert flows.
- `vector_memory/README.md` – Chroma-backed research memory.
- `notifications/README.md` – WhatsApp/alert plumbing.

For operational runbooks (how to start everything from scratch), see:

- `user_instructions/START_AUTONOMOUS_TRADING.md`
- `agent_instructions/SETUP_AUTONOMOUS_TRADING_ENVIRONMENT.md`

## Changelog (Docs)

- 2026-03-21: Updated for news ingestion (`data/news_collector.py`),
  news-aware regimes and lockout, WhatsApp alerts via `notifications/`, live
  strategy degradation, circuit breaker integration, and the current
  single-symbol default (`XAUUSDm`).
