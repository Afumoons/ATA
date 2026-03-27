# autonomous_trading_ai – System Overview

`autonomous_trading_ai` is a modular autonomous trading research and execution
system built around:

- **MT5 market data and order execution**
- **feature engineering + structured regime detection**
- **strategy generation, evaluation, and pool management**
- **risk-aware live routing with daily guardrails and a portfolio circuit breaker**
- **vector-backed research memory**
- **optional macro-news awareness and WhatsApp alerts**

This README is the **top-level map** for the project after **pass 3**. Each
major submodule also has its own `README.md` with implementation-level detail.

## Current Architecture

The project is organized into a few core loops:

1. **Collect market + macro data**
   - `data/collector_mt5.py` fetches OHLCV from MetaTrader 5.
   - `data/news_collector.py` fetches and normalizes macro calendar events from
     Forex Factory.

2. **Build research-grade features and regimes**
   - `research/features.py` computes RSI, ATR, volatility, moving averages,
     Ichimoku/cloud context, Fibonacci zones, and optional news-aware fields.
   - `research/regime.py` adds both:
     - a legacy `regime` label for compatibility, and
     - structured regime metadata such as `regime_class`, `regime_type`,
       `regime_confidence`, and `vol_regime`.

3. **Generate, evolve, and manage strategy inventory**
   - `strategies/generator.py` creates new strategy definitions.
   - `strategies/evolution.py` mutates/crosses higher-scoring strategies.
   - `strategies/pool.py` persists the long-lived strategy pool and status model.

4. **Backtest and evaluate candidates**
   - `backtests/engine.py` simulates bar-by-bar trading.
   - `backtests/explain.py` builds structured `strategy_explain` outputs.
   - `backtests/evaluation.py`, `walkforward.py`, and `monte_carlo.py`
     score and stress-test candidates.

5. **Route live signals through risk controls**
   - `execution/signals.py` turns features + pool state into live decisions.
   - `execution/engine.py` sends validated orders to MT5.
   - `execution/live_state_utils.py`, `live_monitor.py`, `live_observer.py`,
     and `strategy_live_stats.py` maintain state, live PnL, open-trade views,
     and drawdown protection.

6. **Orchestrate the whole system**
   - `scheduler/main.py` runs recurring jobs for data refresh, research,
     execution, monitoring, and news alerts.

7. **Persist research memory and notifications**
   - `vector_memory/research_memory.py` stores and queries strategy research in Chroma.
   - `notifications/whatsapp_notifier.py` sends best-effort alerts via webhook.
   - `webhook_server.py` provides a small FastAPI receiver for outbound alerts.

## Pass 3 Highlights

Pass 3 brings the system into a more explicit **research-to-live specialization**
model.

### 1) Structured regime-aware routing

The system now relies on richer regime context rather than only a single coarse
label. The feature pipeline carries:

- `regime`
- `regime_class`
- `regime_type`
- `regime_confidence`
- `vol_regime`
- optional news-derived lockout/context flags

This allows live execution to reason about specialist strategies more cleanly,
including session and volatility mismatches.

### 2) Explicit strategy routing metadata

Backtests now feed `strategy_explain.meta`, which can persist guidance such as:

- `allowed_regimes` / `blocked_regimes`
- `allowed_sessions` / `blocked_sessions`
- `best_regime` / `worst_regime`
- `best_session` / `worst_session`
- `routing_confidence`

That metadata is stored in pool records and reused by live execution instead of
being re-inferred ad hoc.

### 3) Stronger live gating

The live execution path now combines:

- daily trade-count / daily drawdown limits
- one-open-position-per-strategy slot enforcement
- session hard gates
- regime allow/block policy gates
- volatility mismatch filtering
- confidence-aware gating
- edge-based ranking for `active` and `exploratory` tiers

### 4) Live monitoring maturity

The execution layer now has a clearer separation between:

- executed trades (`trades.log`)
- daily account state (`live_state.json`)
- equity and drawdown history (`equity_history.json`)
- closed deal processing (`closed_trades_state.json`)
- per-strategy live stats (`strategy_live_stats.json`)
- open-trade snapshots (`open_trades.json`)
- ticket-to-strategy mapping (`ticket_strategy_map.json`)

### 5) Better doc coverage for operations

The module READMEs now document not just the main research loop, but also the
live-state artifacts, helper scripts, alert paths, and the current limitations
of the system.

## End-to-End Flow

### A. Data + feature preparation

1. `collector_mt5.py` fetches OHLCV bars from MT5.
2. `news_collector.py` refreshes macro events into `data/raw/news_events.parquet`.
3. `features.py` computes indicators and optional news-aware fields.
4. `regime.py` adds legacy and structured regime labels.
5. Outputs are stored in:
   - `data/raw/`
   - `data/features/`

### B. Research cycle

1. The scheduler loads current features for each managed symbol/timeframe.
2. It loads the `StrategyPool` from `strategies/pool_state.json`.
3. Existing strategies are ranked using base evaluation stats plus small
   memory-based bonuses/penalties from `ResearchMemory`.
4. New candidates are generated/evolved.
5. Each candidate is:
   - backtested,
   - explained,
   - scored,
   - checked with walk-forward and Monte Carlo,
   - assigned a pool status (`active`, `exploratory`, `candidate`, `disabled`, `retired`).
6. The result is stored both in the strategy pool and in Chroma-backed research memory.

### C. Live execution cycle

1. Latest features are loaded.
2. If the latest row indicates `in_news_lockout=True`, execution is skipped for
   that symbol.
3. `execution/signals.py` filters strategies through session/regime/confidence
   gates and ranks them by regime-specific edge.
4. Eligible signals are sent to `execution/engine.py`.
5. `risk/manager.py` validates each trade before order submission.
6. Successful trades are logged and tracked for later monitoring.

### D. Live monitoring cycle

1. `live_monitor.py` polls account equity and closed MT5 deals.
2. Daily PnL/trade counts are pushed into `live_state.json`.
3. Strategy-specific live PnL is aggregated in `strategy_live_stats.json`.
4. Open positions are snapshotted into `open_trades.json`.
5. If portfolio drawdown breaches the configured threshold, the circuit breaker
   disables all `active` strategies.

### E. Alerting / webhook path

- News alerts and degradation alerts can be sent through
  `notifications/whatsapp_notifier.py`.
- `webhook_server.py` exposes `POST /hooks/whatsapp_outbound` for local or
  gateway integration.
- This alert path is still **best-effort / experimental** and should not be
  treated as critical trading infrastructure.

## Module Map

- `data/README.md` – MT5 OHLC ingestion and Forex Factory news ingestion.
- `research/README.md` – features, news-aware context, structured regimes.
- `strategies/README.md` – strategy definitions, generation, pool, manifests,
  and live-aware degradation.
- `backtests/README.md` – bar simulation, explainability, scoring, robustness.
- `risk/README.md` – account-level risk checks and config relationships.
- `execution/README.md` – live execution, routing, state files, monitoring.
- `scheduler/README.md` – recurring jobs and orchestration logic.
- `vector_memory/README.md` – Chroma-backed research memory.
- `notifications/README.md` – outbound WhatsApp/webhook alert path.
- `scripts/README.md` – operational/debug/helper scripts.

## Important Project Files

At the top level:

- `config.py`
  - Shared runtime config for risk, data, and scheduler behavior.
- `logging_utils.py`
  - Logging bootstrap/helpers used across modules.
- `webhook_server.py`
  - FastAPI webhook receiver for outbound message handoff.
- `.env`
  - Environment-based local configuration.

Operational folders you will likely touch:

- `docs/`
- `agent_instructions/`
- `user_instructions/`
- `tests/`
- `logs/`
- `tmp/`

## Runtime Notes

Typical runtime flow:

1. Start MT5 and ensure the target symbols are available.
2. Ensure the Python environment for `autonomous_trading_ai` is active.
3. Ensure Chroma storage is available at the configured path.
4. Optionally run one-shot preparation / inspection scripts from `scripts/`.
5. Start the scheduler:

```powershell
python -m autonomous_trading_ai.scheduler.main
```

## Current Limitations

- The system is still heavily oriented around **single-symbol / per-symbol**
  research loops rather than full portfolio optimization.
- Macro news handling is pragmatic and useful, but still relatively lightweight.
- The alerting/webhook path is not yet hard-guaranteed delivery infrastructure.
- Research memory improves selection guidance, but should be treated as a soft
  heuristic layer, not a source of truth.
- Backtests remain bar-based abstractions and do not model every broker/runtime
  edge case.

## Changelog (Docs)

- 2026-03-21: Documented news ingestion, news-aware regimes/lockout,
  WhatsApp alerts, strategy degradation, and the then-current architecture.
- 2026-03-27: Updated top-level documentation for **pass 3** with structured
  routing, explicit strategy metadata, stronger live gating, expanded execution
  state artifacts, and refreshed module map.
