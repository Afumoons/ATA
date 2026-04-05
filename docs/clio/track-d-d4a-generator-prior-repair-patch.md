# Track D4a — First generator-prior repair patch

Date: 2026-04-05
Owner: Clio Nova
Status: implemented, conservative first batch

## Scope

This patch is the first generator-only repair batch after the D2a/D3a diagnosis.
It does not loosen downstream acceptance gates.
It changes generator priors so fewer obviously broken families are produced in the first place.

Target clusters:
- zero-trade families:
  - `vol_breakout`
  - `compression_breakout`
  - `session_breakout`
  - `xau_impulse_pullback`
  - `xau_session_continuation`
- catastrophic-loss families:
  - `ma_trend`
  - `rsi_range`
  - `pullback_trend`

## What changed

### 1) Simplified zero-trade family entries

Implemented in `strategies/generator.py`:

- `vol_breakout`
  - removed the mandatory RSI confirmer from the loosest branch
  - kept directional structure but reduced conjunction overload
- `compression_breakout`
  - removed same-branch RSI dependency
  - added a simpler reachable branch based on compression + MA/close structure
- `session_breakout`
  - kept session gating but removed the extra RSI requirement from the New York branch
  - preserved directional structure while reducing stacked confirmations
- `xau_impulse_pullback`
  - simplified the main branch by removing the RSI window from the session+trend+volatility branch
  - kept one fib specialist branch for narrower XAU-style structure
- `xau_session_continuation`
  - removed the London/NY mutual exclusion requirement from the London branch
  - removed the mandatory RSI confirmer from the New York branch

### 2) Tightened catastrophic-loss family priors

Implemented in `strategies/generator.py`:

- `ma_trend`
  - raised the broad family `trend_min` floor
  - narrowed XAU M15 `trend_min` lower bound upward as well
  - added family-specific trend exits instead of fully generic exit pairing
- `rsi_range`
  - narrowed `trend_min` to a tighter range-safe band
  - tightened `trend_exit` and `rsi_exit` ranges
  - moved to fade-specific exit pools instead of the generic family-wide exit lottery
- `pullback_trend`
  - raised `trend_min` floor
  - tightened `trend_exit` and `rsi_exit` ranges
  - moved to pullback-specific invalidation/time-decay exits

### 3) Tightened breakout-family parameter ranges

Implemented in `strategies/generator.py`:

- lowered `vol_min` / `trend_min` ranges for `vol_breakout` and `session_breakout`
- raised `vol_max` floor and reduced `trend_min` range for `compression_breakout`
- narrowed XAU M15 breakout/session ranges further to stay conservative but reachable

### 4) Added family-safe exit pairing

The main D3a fix in this batch is stopping the worst family/exit mismatch patterns.

New exit pools:
- `TREND_EXIT_TEMPLATES`
- `FADE_EXIT_TEMPLATES`
- `PULLBACK_EXIT_TEMPLATES`
- `BREAKOUT_EXIT_TEMPLATES`

Applied by family instead of letting these families draw from the same generic exit pool.

### 5) Blocked XAU-specialist leakage into non-XAU generation

Added `_normalize_family_for_market()` and applied it in generation/rebuild paths.

Current conservative behavior:
- `xau_impulse_pullback` requested on non-XAU symbols remaps to `pullback_trend`
- `xau_session_continuation` requested on non-XAU symbols remaps to `session_breakout`

This is a first containment step, not the final XAU/XAG separation design.

## Why this is conservative

This patch intentionally does **not**:
- reopen acceptance gates
- add new complex families
- change backtest engine behavior
- claim D5 symbol separation is done

It only reduces obvious generator-side failure patterns already identified in D2a/D3a.

## Validation

Focused tests:
- `python -m pytest tests/test_hardening_regime_and_generation.py -q`
- Result: `7 passed`

Added targeted test coverage for:
- non-XAU remapping of XAU specialist families
- family-specific exit-pool separation by archetype

## Known next step

D4a is only the first repair patch.
The next required step is a research rerun using the family-stage summaries to compare before/after counts, especially:
- zero-trade counts for breakout/session/XAU specialist families
- destructive survival/failure mix for `ma_trend`, `rsi_range`, `pullback_trend`
- whether XAG still dies disproportionately early even after the XAU leakage guard
