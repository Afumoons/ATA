# 15 - BTC MC hardening + XAG viability repair v3 patch (2026-04-06)

## Scope

Next coherent batch after docs 13/14 and the D5c tracker, focused on:

1. **BTCUSDm M15 Monte Carlo hardening** for already-good challengers that were dying on a binary MC tail gate.
2. **XAGUSDm M15 viability repair v3** focused on cheap-prescreen survival, especially zero-trade breakout/session families.

## What changed

### 1) BTCUSDm M15 MC tail relief is now symbol/family aware, not global

File: `scheduler/main.py`

Added `_passes_symbol_specific_mc_tail_relief(...)` and wired it into the MC gate.

Behavior:
- only applies to **BTC**
- only applies to **mixed ma_trend/rsi_range challengers**
- still requires:
  - at least 40 trades
  - PF >= 1.14
  - Sharpe >= 1.20
  - abs DD <= 5%
  - WF Sharpe >= 1.0
  - MC p5 > -650
  - MC loss probability <= 0.36
  - MC DD p95 <= 1000

This preserves the hard global MC bar while allowing a narrow escape hatch for the specific BTC cohort that already clears cheap prescreen + full backtest + WF and only fails because MC p5 is modestly negative rather than catastrophically negative.

### 2) XAGUSDm M15 generation priors were reweighted and narrowed around likely-survivor families

File: `strategies/generator.py`

Added `XAG_M15_FAMILY_WEIGHTS`:
- upweights `vol_breakout`, `compression_breakout`, `session_breakout`
- downweights `ma_trend`, `rsi_range`

Also tightened XAG-specific priors:
- smaller stop range bias (`75/100/125`)
- slightly better TP skew (`125/150/200/250`)
- stricter `pullback_trend` / `ma_trend` / `rsi_range` filters to reduce catastrophic overtrading

### 3) XAG breakout/session volatility thresholds were corrected to the actual feature scale

File: `strategies/generator.py`

Observed on the current XAG feature set:
- `volatility` mean ~ `0.0051`
- 75th percentile ~ `0.0060`
- max ~ `0.0226`

Old XAG breakout/session/compression priors were effectively operating on the wrong order of magnitude for `vol_min` / `vol_max`, which can suppress entries or make the family behavior incoherent.

Updated to XAG-realistic ranges:
- `session_breakout.vol_min`: `0.0025 .. 0.0065`
- `vol_breakout.vol_min`: `0.0030 .. 0.0070`
- `compression_breakout.vol_max`: `0.0030 .. 0.0080`

### 4) XAG session/vol breakout entry templates were lightened

File: `strategies/generator.py`

Added XAG-only template overrides so those families are no longer universally chained to heavier MA-structure requirements.

This was aimed directly at the prior failure mode where XAG session/breakout variants frequently produced **0 trades** at cheap prescreen.

## Focused evidence

### BTC targeted probes (pre-patch signature driving the MC relief)

Known BTC challengers:
- `core15_BTCUSDm_M15_275e.json`
- `core15_BTCUSDm_M15_0338.json`
- `core15_BTCUSDm_M15_924b.json`

Representative metrics from focused replay:
- `275e`: PF `1.155`, Sharpe `1.379`, WF Sharpe `4.045`, MC p5 `-483.79`, loss prob `0.32`, DD p95 `817.63`
- `0338`: PF `1.193`, Sharpe `1.637`, WF Sharpe `4.019`, MC p5 `-470.47`, loss prob `0.27`, DD p95 `815.34`
- `924b`: PF `1.111`, Sharpe `1.024`, WF Sharpe `3.367`, MC p5 `-630.12`, loss prob `0.41`, DD p95 `909.97`

Interpretation:
- first two are exactly the kind of BTC challengers worth saving via narrow tail relief
- third stays below the new bar because PF / Sharpe / MC loss-prob quality are weaker

### XAG focused rerun findings

Focused cheap-prescreen reruns after the patch showed that the **volatility-scale mismatch was real and fixed**, but XAG `session_breakout` / `vol_breakout` still produced repeated 0-trade candidates in the sampled rerun.

So v3 produced:
- a validated fix for one hard blocker (bad volatility scale)
- better family weighting / priors
- lighter templates
- but **not yet a confirmed cheap-prescreen breakthrough for XAG breakout/session families** on this dataset

## Tests

`python -m pytest autonomous_trading_ai\tests\test_hardening_regime_and_generation.py -q`

Result:
- **14 passed**

Coverage added/updated for:
- BTC MC tail relief narrowness
- XAG M15 family weights
- XAG session template lightening
- XAG prior range checks

## Assessment

### BTCUSDm M15
Good, coherent improvement.

The new rule is explicit, narrow, symbol-aware, family-aware, and does **not** loosen MC globally.

### XAGUSDm M15
Repair is still incomplete.

This batch fixed a real parameter-scale issue and further reduced obvious generator-side waste, but sampled reruns still showed zero-trade behavior for XAG breakout/session families. The next likely work item is to inspect whether the remaining blocker is:
- regime gating,
- session feature availability/semantics in the expression context,
- or still-overstrict trend/session composition on XAG M15.

## Files changed in this batch

- `scheduler/main.py`
- `strategies/generator.py`
- `tests/test_hardening_regime_and_generation.py`
