# Manual Trade Ticket Symbol Metadata Audit

_Last updated: 2026-04-30_

## Why this exists
T1 needs a single normalized symbol-spec shape before the manual risk calculator, preview API, and submit flow can share the same broker geometry.

## Existing metadata sources already present in repo

### 1. Canonical symbol mapping in `config.py`
Current foundation already exists for:
- canonical research symbol normalization via `canonical_symbol(...)`
- execution symbol variants via `execution_variants_for(...)`

This is the correct entry point for manual ticket symbol resolution because the UI should speak canonical symbols while the backend can still execute the broker-visible variant.

### 2. Broker symbol discovery in MT5-facing modules
Existing MT5 discovery already appears in:
- `data/collector_mt5.py::_resolve_mt5_symbol(...)`
- `execution/engine.py::_resolve_execution_symbol(...)`

Both modules already rely on `mt5.symbol_info(...)` and `symbol_select(...)` to find the execution-ready broker symbol.

### 3. Broker lot constraints already partially consumed in execution
`execution/engine.py::_clamp_volume(...)` already reads:
- `volume_min`
- `volume_max`
- `volume_step`

This confirms the broker already exposes the lot-boundary fields the manual ticket needs.

### 4. Hard-coded pip fallbacks still exist today
Current execution/signal code still contains fallback heuristics in:
- `execution/engine.py::_pip_value_for_symbol(...)`
- `execution/signals.py::_pip_params(...)`

These are acceptable as legacy autonomous-execution fallbacks, but they are not sufficient as the primary data source for manual ticket sizing because the manual ticket must be broker-geometry driven and audit-friendly.

## Normalized symbol spec payload
The manual trade ticket should standardize on this payload shape:

```json
{
  "symbol": "XAUUSDm",
  "symbol_canonical": "XAUUSDm",
  "execution_symbol": "XAUUSDm",
  "instrument_class": "metals",
  "digits": 2,
  "point_size": 0.01,
  "tick_size": 0.01,
  "tick_value": 1.0,
  "contract_size": 100.0,
  "min_lot": 0.01,
  "lot_step": 0.01,
  "max_lot": 100.0,
  "source": "mt5.symbol_info"
}
```

## MT5 field mapping
The normalized payload maps cleanly from MT5 symbol info:

- `symbol` -> request/UI symbol
- `symbol_canonical` -> `canonical_symbol(symbol)`
- `execution_symbol` -> resolved broker-visible variant
- `digits` -> `info.digits`
- `point_size` -> `info.point`
- `tick_size` -> `info.trade_tick_size`
- `tick_value` -> `info.trade_tick_value`
- `contract_size` -> `info.trade_contract_size`
- `min_lot` -> `info.volume_min`
- `lot_step` -> `info.volume_step`
- `max_lot` -> `info.volume_max`

## Implementation note added in code
`execution/symbol_metadata.py` now provides:
- `classify_instrument(...)`
- `normalize_symbol_spec(...)`
- `fetch_symbol_spec(...)`
- dataclasses for the normalized spec and warnings snapshot

This gives T1 and T3 a reusable source of truth without changing live autonomous order behavior yet.

## Gaps that remain after this slice
Not done in this slice:
- risk sizing math engine
- `POST /api/execution/risk-calc`
- UI form
- live manual submit path
- preview confirmation hashing/idempotency

## Recommendation for the next slice
Build the reusable sizing engine on top of `execution/symbol_metadata.py`, and make it reject silent hard-coded pip assumptions whenever normalized broker metadata is missing or non-positive.
