# Manual Trade Ticket Specification

_Last updated: 2026-04-30_

## Purpose
Define the bounded first release of the operator-side manual trade ticket before UI/API/live-submit implementation proceeds.

## Product Scope for First Release
The first release is an operator-only ticket inside the UI that:
- calculates lot sizing from explicit risk input
- supports Buy/Sell market orders and Buy Limit/Sell Limit pending orders
- supports stop loss and take profit input by pips or absolute price
- previews the final payload before submit
- marks every submitted order as an explicit manual-user trade
- keeps manual trades segregated from autonomous strategy attribution, governance, and research/live statistics

Out of scope for first release:
- stop/stop-limit pending orders
- trailing stop, partial close, scale-in/out, or bracket editing after submit
- autonomous strategy reuse, strategy attribution, or hybrid auto-manual execution
- bulk multi-order basket submit
- write-capable operator controls outside this manual ticket flow

## Dedicated Identity and Segregation Contract
Manual ticket orders must carry explicit non-strategy identity:
- `order_origin = manual_user`
- `execution_origin = operator_ui`
- `is_manual = true`
- `exclude_from_strategy_eval = true`
- MT5 comment tag includes `clio-manual-user`

Rules:
- never attribute a manual ticket to any autonomous strategy name
- never let manual tickets enter promotion/demotion, live decay, drift scoring, specialist evaluation, or research acceptance metrics
- manual trades may appear in execution/audit views, but only with explicit manual labeling or dedicated manual buckets

## Supported Order Types
First release supports:
- Market: Buy, Sell
- Pending / limit: Buy Limit, Sell Limit

First release excludes:
- Buy Stop, Sell Stop
- stop-limit variants

## Supported Risk Input Modes
- Risk in money: operator enters account-currency loss budget directly
- Risk in % equity: operator enters percent of current account equity, backend resolves amount from latest account snapshot

## Supported SL/TP Input Modes
Stop loss:
- by pips
- by absolute asset price

Take profit:
- by pips
- by absolute asset price

Conversion rules:
- pips are converted using normalized symbol metadata and symbol digits/point rules
- preview and submit payloads must always resolve to explicit final prices

## Symbol-Class Validation Rules
Validation should use normalized symbol metadata and symbol-class heuristics.

### Forex
- allow pip-based entry/SL/TP workflow
- respect broker digits, point size, tick size, lot step, and min/max lot
- reject zero/negative stop distance
- warn when stop distance is extremely tight relative to tick size or typical spread

### Metals
- support price-based and pip-like distance input using symbol point/tick metadata rather than hard-coded forex assumptions
- validate lot sizing with contract size and tick value from broker metadata
- warn when operator input rounds to invalid price increments or lot steps

### Crypto
- treat tick size and contract/tick value as broker-defined, not forex-like defaults
- allow larger absolute price ranges without overflow/format assumptions
- warn when risk sizing produces below-min-lot exposure or exceeds max lot

### Cross-class invariants
For all supported classes:
- symbol metadata must exist or calculator stays disabled
- entry, SL, and TP must land on valid tick increments after normalization
- lot size must be rounded to valid lot step before preview
- rounded lot size must still respect min lot and max lot
- SL must be on the loss side of entry, TP on the profit side, based on Buy vs Sell
- pending limit price must be on the valid side of current market price

## Execution Safety Rules
- live submit is blocked unless preview was generated from the same normalized payload
- operator must pass an explicit confirmation gate before live submit
- backend must reject payloads with missing symbol metadata, stale account equity, invalid price geometry, or impossible lot sizing
- submit path must be idempotency-aware to reduce duplicate-click risk
- audit trail must record preview intent and final broker response
- manual submit code path must stay separate from autonomous strategy order creation
- any fallback/default strategy field must remain empty or manual-only, never mapped to an autonomous strategy

## Suggested Payload Shape Direction
Preview/submit flows should converge on a normalized payload containing:
- symbol
- side
- order_type
- entry_mode
- entry_price if pending
- risk_mode
- risk_value
- stop_loss_mode
- stop_loss_input
- take_profit_mode
- take_profit_input
- derived lot_size
- derived normalized entry/sl/tp prices
- manual identity fields listed above

T1 metadata audit reference: `docs/manual-trade-ticket-symbol-metadata-audit.md`

## Release Sequence
1. T0 specification and boundaries
2. T1 symbol metadata audit and sizing engine
3. T3 backend risk calculator API
4. T2 UI calculator form
5. T4 manual identity/segregation completion
6. T5 preview and confirmation
7. T6 live submit
8. T7 monitoring visibility
9. T8 hardening/polish
