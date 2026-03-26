# autonomous_trading_ai – Architecture

This document describes how the system is structured at a high level. It should be kept in sync with the actual code as the project evolves.

Important framing:
- The current implementation is **not** a generic multi-broker execution platform.
- The current codebase is best understood as an **MT5-centric research + live execution stack**, with the strongest present operating alignment around **`XAUUSDm M15`**.
- When this doc uses conceptual terms, prefer interpreting them through the actual implemented modules (`data`, `research`, `strategies`, `backtests`, `execution`, `scheduler`, `risk`) rather than as future-platform promises.

## 1. High‑Level Diagram (Conceptual)

A typical end‑to‑end flow looks like this:

```text
[Data Source(s)] -> [Data Layer] -> [Signal Engine] -> [Trade Planner]
                                          |                 |
                                          v                 v
                                     [Risk Checker] ----> [Execution Adapter]
                                          |
                                          v
                                      [Journal]
```

And for OpenClaw integration:

```text
[autonomous_trading_ai] <-> [Project Files / Logs]
                               ^
                               |
                        [Clio + Subagents]
                               |
                               v
                       [Alerts / Dashboards]
```

## 2. Main Components

> NOTE: Update names/paths to match the actual code structure (modules, packages, folders).

### 2.1 Data Layer

Responsibilities:
- Fetch historical and/or live market data (candles, order book, funding, etc.).
- Normalize data into a format the signal engine expects.
- Provide caching where needed to avoid hammering APIs.

Possible locations:
- `src/data/` or equivalent.

### 2.2 Signal Engine

Responsibilities:
- Consume normalized market data.
- Compute indicators and patterns.
- Emit **signals** like:
  - `LONG_SETUP`, `SHORT_SETUP`, `EXIT_SIGNAL`, etc.

Notes:
- Should be deterministic given the same data.
- Should be testable in isolation (unit tests on indicator logic).
- Current trading mode is **1 strategy → 1 open position**. Backtests and live
  execution should not pyramid the same strategy while its prior position is
  still open, unless a legacy/migration path explicitly opts back into
  multi-position behaviour.

### 2.3 Trade Planner

Responsibilities:
- Turn a signal into a **trade plan**:
  - symbol, side, entry, SL, TP, size, leverage, time‑in‑force.
- Use account/equity info and risk parameters to size positions.

Interface (conceptual):

```ts
TradePlan = {
  id: string,
  timestamp: string,
  symbol: string,
  side: "long" | "short",
  leverage: number,
  size_quote: number,
  entry: number,
  stop_loss?: number,
  take_profit?: number,
  meta?: Record<string, any>
}
```

### 2.4 Risk Checker (Core for OpenClaw Sandbox)

Responsibilities:
- Decide whether a `TradePlan` is **allowed** or **blocked** before execution.
- Encapsulate rules such as:
  - max % equity per trade,
  - max number of concurrent positions per symbol,
  - **max one open position per strategy slot** (`strategy + symbol + timeframe`) in the current live mode,
  - max leverage per market,
  - session time rules (avoid certain hours),
  - volatility filters, etc.

Integration pattern with OpenClaw (file‑based example):

1. Engine writes a JSON file like:
   - `runtime/risk_requests/<id>.json` containing the `TradePlan` + context.
2. An OpenClaw sandbox subagent:
   - reads the request file,
   - evaluates rules,
   - writes `runtime/risk_results/<id>.json` with a structure like:

```jsonc
{
  "id": "same-as-request",
  "decision": "allow",     // or "block"
  "reasons": [
    "risk_per_trade_ok",
    "within_leverage_limit"
  ],
  "adjustments": {
    // optional: the risk engine can shrink size, force tighter SL, etc.
  }
}
```

3. Engine waits for the result and either:
   - proceeds to execution, or
   - skips the trade and logs the block.

### 2.5 Execution Adapter(s)

Responsibilities:
- Translate `TradePlan` into real API calls for specific exchanges:
  - Binance, Bybit, Exness, etc.
- Handle authentication, rate limits, and error handling.

Design notes:
- Keep adapters thin and declarative; they should not contain strategy logic.
- Prefer a clean interface like:

```ts
executeTrade(plan: TradePlan, options?: ExecuteOptions): Promise<ExecutionResult>
```

### 2.6 Journal & Logging

Responsibilities:
- Persist all important events:
  - signals,
  - trade plans,
  - risk decisions,
  - executed orders,
  - PnL and metrics.

Implementation ideas:
- Append‑only JSONL files in `logs/` or `runtime/logs/`.
- Human‑readable summaries in Markdown for daily/weekly review.

## 3. Config & Parameters

> Keep this section in sync with actual config files (YAML/JSON/env).

Key configuration areas:
- Exchange credentials (kept **out of git**, loaded via env/secret store).
- Risk parameters:
  - max_risk_pct_per_trade,
  - max_daily_loss,
  - per‑symbol leverage caps.
- Strategy toggles:
  - enable/disable specific signals or markets.

File layout suggestion:

```text
config/
  env.example            # placeholder env vars
  risk.default.json      # default risk limits
  strategy.default.json  # default strategy toggles
```

## 4. OpenClaw Integration Points

Current/planned integration points:

1. **Risk Checker Subagent**
   - Sandbox subagent consumes `runtime/risk_requests/*.json`.
   - Produces `runtime/risk_results/*.json`.

2. **Journaling & Analytics**
   - Clio can read logs and produce:
     - daily summaries,
     - edge analysis,
     - anomaly detection (e.g., unusual loss streaks).

3. **Alerting (via WhatsApp webhook skill)**
   - A separate process/agent can watch:
     - `logs/` for error events,
     - `risk_results/` for blocked trades,
     - PnL metrics.
   - When certain thresholds are hit, send concise alerts.

## 5. Runtime Topologies

A few ways this system can be deployed:

1. **Local Dev & Backtest**
   - Run engine + data locally.
   - No OpenClaw involvement required.

2. **Local Live + OpenClaw Sandbox**
   - Engine runs on the same machine as OpenClaw.
   - File‑based risk requests/results exchanged via the workspace.
   - Subagents in sandbox handle risk logic and summaries.

3. **Hybrid (Server Engine, Local Gateway)**
   - In future, engine can run on a server/VPS,
   - OpenClaw gateway on your laptop/desktop,
   - Connected via shared storage or API bridge.

## 6. Future Extensions

- Multi‑strategy orchestration (portfolio of strategies running in parallel).
- Strategy‑specific risk modules (e.g., mean‑reversion vs breakout).
- Web dashboard for monitoring (positions, PnL, health).
- Richer integration with Clio for semi‑automated parameter tuning.

---

> Keep this file short, accurate, and updated. When you change how components talk to each other, update this doc so both you and Clio always have the same mental model.
