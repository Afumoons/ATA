# autonomous_trading_ai – Architecture

This document describes the implemented high-level architecture of the current
system.

## Framing

The current codebase is best understood as:

- an **MT5-centric research + live execution stack**
- with a **specialist strategy inventory**
- governed by a **routing layer**
- orchestrated by a recurring scheduler loop

It is not a generic abstract exchange framework. Use the real modules and files
as the source of truth.

## High-Level Flow

```text
[MT5 OHLC + Forex Factory News]
              ↓
        [data/ collection]
              ↓
 [research/ features + structured regimes]
              ↓
[strategies/ generation + pool governance]
              ↓
 [backtests/ evaluation + explainability]
              ↓
[vector_memory/ research memory guidance]
              ↓
[scheduler/ orchestration]
       ↙                    ↘
[execution/ live routing]   [notifications/ alerts]
       ↓
 [MT5 order execution + monitoring]
```

## Main Runtime Components

### 1. Data layer – `data/`

Responsibilities:

- connect to MT5
- fetch OHLCV bars
- persist raw parquet data
- fetch and normalize Forex Factory macro events

Important files:

- `data/collector_mt5.py`
- `data/news_collector.py`

Important outputs:

- `data/raw/{symbol}_{timeframe}_ohlc.parquet`
- `data/raw/news_events.parquet`

### 2. Feature + regime layer – `research/`

Responsibilities:

- compute indicators and derived features
- join macro-news context
- classify market regimes
- preserve both legacy and structured regime fields

Important files:

- `research/features.py`
- `research/regime.py`

Important outputs:

- `data/features/{symbol}_{timeframe}_features.parquet`
- fields such as:
  - `regime`
  - `regime_class`
  - `regime_type`
  - `regime_confidence`
  - `vol_regime`
  - `in_news_lockout`

### 3. Strategy inventory layer – `strategies/`

Responsibilities:

- define strategy specs as data
- generate and evolve candidate strategies
- persist pool records and statuses
- carry routing metadata forward from research

Important files:

- `strategies/base.py`
- `strategies/generator.py`
- `strategies/evolution.py`
- `strategies/pool.py`
- `strategies/live_manifest.py`

Important persistent artifacts:

- `strategies/generated/*.json`
- `strategies/pool_state.json`

### 4. Research evaluation layer – `backtests/`

Responsibilities:

- simulate historical strategy behavior
- compute score and threshold decisions
- build `strategy_explain`
- run walk-forward and Monte Carlo checks

Important files:

- `backtests/engine.py`
- `backtests/evaluation.py`
- `backtests/explain.py`
- `backtests/walkforward.py`
- `backtests/monte_carlo.py`

Important architectural role:

This layer produces the metadata later reused by live routing, especially via:

- `strategy_explain.regime_pnl`
- `strategy_explain.session_pnl`
- `strategy_explain.meta`

### 5. Research memory layer – `vector_memory/`

Responsibilities:

- store evaluation summaries in Chroma
- query similar prior strategies
- provide soft guidance for parent selection and candidate filtering

Important file:

- `vector_memory/research_memory.py`

Important property:

This is **advisory**, not a hard execution dependency.

### 6. Orchestration layer – `scheduler/`

Responsibilities:

- run recurring jobs
- keep the whole system synchronized
- invoke research, execution, monitoring, and alerts

Important file:

- `scheduler/main.py`

Typical jobs:

- `job_update_data`
- `job_research_strategies`
- `job_execute_signals`
- `job_live_monitor`
- `job_update_news`
- `job_news_alert`

### 7. Live execution layer – `execution/`

Responsibilities:

- enforce live eligibility and routing logic
- validate trades through account-level risk checks
- place orders into MT5
- maintain daily state and live-performance state
- observe equity and open/closed trades

Important files:

- `execution/signals.py`
- `execution/engine.py`
- `execution/live_state_utils.py`
- `execution/live_monitor.py`
- `execution/live_observer.py`
- `execution/strategy_live_stats.py`

Important state artifacts:

- `execution/trades.log`
- `execution/live_state.json`
- `execution/equity_history.json`
- `execution/closed_trades_state.json`
- `execution/strategy_live_stats.json`
- `execution/open_trades.json`
- `execution/ticket_strategy_map.json`

### 8. Hard risk layer – `risk/`

Responsibilities:

- per-trade risk cap
- max open positions
- max portfolio drawdown check vs peak equity

Important file:

- `risk/manager.py`

Important note:

This is separate from session/regime routing and separate from daily guardrails.

### 9. Notifications / alert layer – `notifications/` + `webhook_server.py`

Responsibilities:

- build outbound alerts
- POST them to a configured webhook target
- support operator awareness for important events

Important files:

- `notifications/whatsapp_notifier.py`
- `webhook_server.py`

Important note:

This path is currently **best-effort / experimental** and not critical for the
trading loop.

## Pass 3 Architecture Shift

Pass 3 mainly changes how research and live layers connect.

### Before

The system leaned more toward:

- score-driven selection
- coarse regime usage
- lighter specialist governance

### Now

The system leans more toward:

- explicit specialist metadata
- structured regime-aware routing
- session hard gates
- confidence-aware eligibility
- volatility mismatch handling
- clear no-trade outcomes when no specialist is credible

## Live Decision Pipeline

A practical pass 3 live flow now looks like:

```text
[Latest feature row]
      ↓
[Daily/news/open-slot guards]
      ↓
[Session eligibility gate]
      ↓
[Regime allow/block gate]
      ↓
[Volatility mismatch gate]
      ↓
[Confidence gate]
      ↓
[Rank eligible specialists by edge]
      ↓
[Apply active/exploratory risk tier]
      ↓
[Risk manager validation]
      ↓
[MT5 order execution]
```

Key principle:

- **eligibility first, ranking second**

## Design Constraints

The architecture intentionally accepts these limitations:

- per-symbol research is stronger than portfolio-level intelligence
- backtests are still bar-based abstractions
- research memory is heuristic guidance, not authority
- alert delivery is not guaranteed infrastructure
- operator visibility exists, but not yet as a polished dashboard product

## Practical Mental Model

If you need one sentence to remember the architecture:

> `autonomous_trading_ai` is a scheduler-driven MT5 research/execution system that discovers specialist strategies, stores them in a governed pool, and deploys them conservatively through a structured live-routing layer.

## Changelog (Docs)

- 2026-03-27: Rewrote the architecture doc to match the implemented pass 3 module graph, state artifacts, and specialist-routing execution model.