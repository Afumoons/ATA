# autonomous_trading_ai – Overview

## 1. Purpose

`autonomous_trading_ai` is an opinionated trading engine designed to run semi‑autonomously under Afu's supervision.

High‑level goals:
- Automate repetitive trading workflows (signal evaluation, order sizing, risk checks, logging).
- Keep a **clear separation** between decision logic (strategy) and execution (brokers/exchanges).
- Make it easy to **test, simulate, and audit** decisions after the fact.

Non‑goals (for now):
- Being a generic "for everyone" framework.
- Blind, fully autonomous trading without risk guardrails.

## 2. Scope

Current intended scope:
- Markets: crypto + FX (primarily via Binance/Bybit/Exness APIs).
- Styles: scalp + intraday, with aggressive risk profile but explicit caps.
- Instruments: spot + perp futures.

Out of scope (current design):
- Options/derivatives beyond perps.
- Long‑horizon portfolio optimization.

> NOTE: Update this section as markets/instruments actually supported by the code evolve.

## 3. Core Concepts

- **Signal** – A structured description of why a trade is considered (indicator state, pattern, context).
- **Trade plan** – A proposed order: symbol, side, size, entry, SL/TP, leverage, time‑in‑force, etc.
- **Risk rule** – A constraint that can block or shrink a trade (max % equity per trade, max leverage, session time rules, etc.).
- **Execution** – The concrete interaction with an exchange/broker API.
- **Journal entry** – A log record that ties together signal → decision → execution → outcome.

## 4. Operating Modes

Planned/typical modes:

1. **Backtest / Simulation**
   - Inputs: historical data.
   - Output: trade logs + performance metrics.
   - No real API calls.

2. **Paper / Shadow Trading**
   - Runs in (near) real‑time.
   - Generates trade plans and decisions, but does not hit live order APIs.

3. **Live Assisted**
   - Engine proposes trades and passes through a **risk checker** (e.g., via OpenClaw sandbox subagent).
   - Final execution can still require explicit human approval.

4. **Live Semi‑Autonomous** (future)
   - Engine + risk checker operate continuously.
   - Human supervision via alerts, dashboards, and configurable kill‑switches.

## 5. Safety & Risk Philosophy

- Default stance: **aggressive but bounded** risk.
- Every trade should be explainable in terms of:
  - What signal triggered it.
  - Which risk rules were checked and passed.
  - How size and leverage were calculated.
- The engine should fail **safe** (stop trading or reduce size) on:
  - Data quality issues (missing candles, bad prices).
  - Connectivity issues to exchanges.
  - Inconsistent account state (margin, positions).

## 6. Integration with OpenClaw

`autonomous_trading_ai` is designed to integrate with an OpenClaw‑based assistant (Clio Nova):

- Clio can read and write project files (plans, logs, configs) to:
  - Propose strategy changes.
  - Summarize performance.
  - Generate or review risk rules.
- Sandbox subagents can:
  - Perform **risk & sanity checks** on trade plans before execution.
  - Produce human‑readable explanations.
- Messaging plugins (WhatsApp, etc.) can be wired (via webhook skills) to send alerts on:
  - Strategy errors.
  - Risk rule violations.
  - Large PnL swings.

## 7. Status

Early stage / evolving.

Use this section to keep a short, honest snapshot:

- [ ] Backtest path stable
- [ ] Paper trading stable
- [ ] Live trading connected (which exchanges?)
- [ ] Risk checker integrated with OpenClaw
- [ ] Alerting wired (WhatsApp / others)

Update checkboxes as features become real.
