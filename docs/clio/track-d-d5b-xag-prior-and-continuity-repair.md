# Track D5b — XAG-specific prior and continuity repair

Date: 2026-04-05
Owner: Clio Nova
Status: implemented, conservative XAG-only repair batch

## Scope

This batch targets the next repair wave requested after the post-D4a audit:
- improve `XAGUSDm` cheap-prescreen viability
- improve downstream continuity for viable XAG challengers
- avoid collateral changes to `XAUUSDm` and `BTCUSDm`

This is a **market-specific generator repair**, not a broad acceptance loosening pass.

## Inputs / rationale

Source-of-truth drivers:
- `docs/clio/11-FAMILY-QUALITY-REPAIR-INSTRUCTIONS-AND-TASKLIST.md`
- `docs/clio/12-POST-D4A-RERUN-AUDIT.md`

Observed post-D4a XAG failure patterns:
- many XAG breakout/session/compression families still died with `0 trades` at cheap prescreen
- some XAG trend/range families traded, but failed destructively before downstream continuity mattered
- rebuilt non-XAU strategies could preserve stale `xau_*` family metadata after normalization, which undermined family-level observability and family-safe repair logic

## What changed

### 1) Fixed rebuilt non-XAU family normalization persistence

Implemented in `strategies/generator.py` inside `rebuild_strategy_from_params()`:
- after choosing the normalized family for the target symbol, the rebuilt params now explicitly overwrite:
  - `family`
  - `playbook_type`
  - `primary_market_condition`

Why this matters:
- previously, a non-XAU rebuild could normalize internally but still keep stale `xau_*` family fields from incoming params after merge
- that could pollute Track D family counts and keep XAG/BTC rebuilds tied to the wrong family identity

### 2) Added XAG M15 market-specific family priors

Implemented in `strategies/generator.py` under the new `symbol == "XAGUSDm" and timeframe == "M15"` branch.

Conservative XAG-specific changes:
- set `microstructure_profile = xag_m15`
- widened XAG stop/target defaults modestly to avoid ultra-tight churn:
  - `stop_loss_pips`: `75/100/125/150`
  - `take_profit_pips`: `100/125/150/200`
- softened cheap-prescreen-dead families:
  - `compression_breakout`
    - higher reachable `vol_max`
    - lower `trend_min`
    - slightly longer time-stop window
  - `vol_breakout`
    - lower `vol_min`
    - lower `trend_min`
  - `session_breakout`
    - lower `vol_min`
    - lower `trend_min`
- tightened destructive XAG families without touching XAU/BTC priors:
  - `pullback_trend`
    - narrower, lower `trend_exit`
    - moderate `trend_min`
  - `ma_trend`
    - higher `trend_min` floor than generic XAG-adjacent generation
    - slightly tighter trend exits
  - `rsi_range`
    - tighter range-safe `trend_min`
    - narrower `trend_exit`
    - tighter `rsi_exit`
    - more reachable but still bounded `vol_max`

## Intended effect

This batch is trying to reduce two specific XAG failure modes simultaneously:

1. **dead-on-arrival cheap-prescreen failures**
   - by making breakout/session/compression templates more reachable on XAG M15

2. **downstream continuity collapse for the few XAG strategies that do trigger**
   - by stopping obviously misclassified rebuilt families and tightening destructive trend/range priors only for XAG

## Why this is conservative

This batch intentionally does not:
- loosen global cheap-prescreen thresholds
- reopen research gates globally
- alter XAU priors
- alter BTC priors
- claim full XAG coherence is solved without a new rerun

It only tightens or softens the XAG generator surface where the post-D4a audit showed clear symbol-specific mismatch.

## Validation

Focused test coverage added for:
- non-XAU rebuild normalization persistence
- XAG-specific `session_breakout` parameter ranges
- XAG-specific `compression_breakout` parameter ranges

Representative validation command:
- `python -m pytest autonomous_trading_ai/tests/test_hardening_regime_and_generation.py -q`

## Required next check

A fresh research rerun is still required to confirm whether this XAG-only repair batch actually improves:
- cheap-prescreen pass counts
- family-stage continuity past cheap prescreen
- absence of stale `xau_*` family leakage in new XAG/BTC artifacts
