# Track D2a — Zero-trade family diagnosis

Date: 2026-04-05
Owner: Clio Nova

## Scope

This note diagnoses the families that repeatedly fail with `0 trades` in the new Track D family-stage summaries.

Primary artifact inputs:
- `tmp/research_family_stage_summaries/XAUUSDm_M15.json`
- `tmp/research_family_stage_summaries/XAGUSDm_M15.json`

Generator/code inputs:
- `strategies/generator.py`

Representative validation:
- sampled generated strategies from `strategies/generated/`
- spot backtests replayed on saved feature sets for representative examples

---

## Executive finding

The zero-trade problem is real and structurally consistent.

It is **not** mainly a cheap-prescreen threshold artifact.
It starts earlier: many breakout/continuation families are generated with **entry conditions so restrictive that the backtest never opens a position at all**.

Across both XAU and XAG, the recurring pattern is:

1. session gating narrows the valid bars too hard
2. volatility gating narrows them again
3. directional confirmation narrows them again
4. RSI / fib / MA alignment adds another layer
5. result: the conjunction often never becomes true on the saved M15 feature history

So D2 is fundamentally a **generator-prior problem**, not a later promotion/governance problem.

---

## What the stage artifacts say

### XAUUSDm M15
Families repeatedly showing pure zero-trade cheap-prescreen failures:
- `vol_breakout`
- `compression_breakout`
- `session_breakout`
- `xau_impulse_pullback`
- `xau_session_continuation`

Examples from the family-stage artifact:
- `vol_breakout_XAUUSDc_M15_c57c: tr=0 pf=0.00 sh=0.00 dd=0.0`
- `session_breakout_XAUUSDc_M15_fbd6: tr=0 pf=0.00 sh=0.00 dd=0.0`
- `xau_impulse_pullback_XAUUSDc_M15_e624: tr=0 pf=0.00 sh=0.00 dd=0.0`
- `xau_session_continuation_XAUUSDc_M15_596f: tr=0 pf=0.00 sh=0.00 dd=0.0`

### XAGUSDm M15
Same pattern appears even earlier and more broadly:
- `vol_breakout`
- `compression_breakout`
- `session_breakout`
- `xau_impulse_pullback`
- `xau_session_continuation`

Examples from the family-stage artifact:
- `vol_breakout_XAGUSDc_M15_09c8: tr=0 pf=0.00 sh=0.00 dd=0.0`
- `compression_breakout_XAGUSDc_M15_e9be: tr=0 pf=0.00 sh=0.00 dd=0.0`
- `session_breakout_XAGUSDc_M15_d21d: tr=0 pf=0.00 sh=0.00 dd=0.0`
- `xau_impulse_pullback_XAGUSDc_M15_5dc7: tr=0 pf=0.00 sh=0.00 dd=0.0`
- `xau_session_continuation_XAGUSDc_M15_9aff: tr=0 pf=0.00 sh=0.00 dd=0.0`

---

## Generator sample review

## 1. `vol_breakout`

Representative samples:
- XAU: `volatility > 1.0 and close > ma_short and ma_short > ma_long and trend_strength > 0.32`
- XAG: `volatility > 1.504 and trend_strength > 0.37 and close > ma_short and rsi > 55`

Observed issue:
- `vol_min` is frequently high (`~1.0` to `1.5+`)
- `trend_min` is also often high (`~0.27` to `0.41`)
- additional MA or RSI confirmation stacks on top

Diagnosis:
- this is demanding simultaneous high volatility, strong trend, and already-confirmed direction
- on M15 this often means the template only fires during rare impulse bars
- once spread/session/execution assumptions are applied, many samples never trigger at all

## 2. `compression_breakout`

Representative samples:
- XAU: `volatility < 0.279 and ma_short > ma_long and trend_strength > 0.09 and rsi > 50`
- XAG: `volatility < 0.101 and ma_short > ma_long and trend_strength > 0.2 and rsi > 50`

Observed issue:
- the family requires low-volatility compression
- but also requires directional trend confirmation at the same time
- in XAG especially, `vol_max` can become extremely low (`0.10` range)

Diagnosis:
- the template is trying to trade a breakout while still demanding the market remain inside a strict low-volatility state
- that creates a contradiction: the setup often asks for pre-breakout compression and post-breakout directional confirmation on the same bar
- the result is a large number of `0 trade` strategies rather than just low-frequency strategies

## 3. `session_breakout`

Representative samples:
- XAU: `session_new_york == 1 and volatility > 1.258 and ma_short > ma_long and rsi > 55 and trend_strength > 0.12`
- XAG: `session_london == 1 and volatility > 1.447 and close > ma_short and trend_strength > 0.41`

Observed issue:
- session gating is hard binary
- then `vol_min` is high
- then trend confirmation is required
- often RSI or MA alignment is required too

Diagnosis:
- this family narrows candidate bars twice before even reaching direction filters:
  - first by session
  - then by volatility
- after that it still asks for a mature trend state
- that produces a very sparse trigger surface, especially for XAG where the volatility/trend thresholds are often more aggressive than the underlying feature distribution seems to support

## 4. `xau_impulse_pullback`

Representative samples:
- XAU: `session_london == 1 and close > ma_short and ma_short > ma_long and trend_strength > 0.45 and volatility > 0.926 and rsi > 52 and rsi < 68`
- XAG: `session_london == 1 and close > ma_short and ma_short > ma_long and trend_strength > 0.13 and volatility > 1.101 and rsi > 52 and rsi < 68`
- alternate branch uses `fib_zone_382 == 1` / `fib_zone_618 == 1`

Observed issue:
- session restriction + volatility gate + trend gate + MA alignment + RSI window is already tight
- the fib version introduces a discrete feature flag that may occur rarely in combination with the other conditions
- the family is XAU-themed but is also being generated for XAG in the current system

Diagnosis:
- this family is over-specified for a first-pass generator prior
- it behaves more like a niche hand-crafted specialist than a broad search family
- routing the same templates into XAG likely worsens the mismatch

## 5. `xau_session_continuation`

Representative samples:
- XAU: `session_new_york == 1 and ma_short > ma_long and close > ma_short and trend_strength > 0.4 and rsi > 55 and volatility > 0.645`
- XAG: `session_new_york == 1 and ma_short > ma_long and close > ma_short and trend_strength > 0.22 and rsi > 55 and volatility > 1.059`

Observed issue:
- continuation logic requires the move to already be underway
- session filter is mandatory
- volatility gate is mandatory
- trend filter is mandatory
- often RSI confirmation is mandatory too

Diagnosis:
- the family is effectively demanding an already-established session trend continuation bar with extra momentum proof
- that is too selective for broad research generation, especially with current random parameter ranges

---

## Spot backtest confirmation

Representative replay checks on saved features confirmed the artifact diagnosis:

### XAUUSDm examples
- `core15_XAUUSDm_M15_0009` (`vol_breakout`) -> `0 trades`
- `core15_XAUUSDm_M15_0145` (`session_breakout`) -> `0 trades`
- `core15_XAUUSDm_M15_0207` (`pullback_trend` sample with high threshold) -> `0 trades`

### XAGUSDc examples
- `vol_breakout_XAGUSDc_M15_0079` -> `0 trades`
- `compression_breakout_XAGUSDc_M15_0013` -> `0 trades`
- `session_breakout_XAGUSDc_M15_03a3` -> `0 trades`
- `pullback_trend_XAGUSDc_M15_0099` -> `0 trades`

This matters because it confirms the failure is not merely a logging artifact. The generated rule sets themselves often do not fire on the stored feature histories.

---

## Top recurring causes of zero-trade

### Cause 1 — stacked conjunction overload
Too many mandatory clauses are combined on one entry rule:
- session
- volatility
- trend strength
- MA structure
- RSI bounds
- sometimes fib zone flags

### Cause 2 — volatility thresholds too ambitious for M15
Breakout families often draw `vol_min` values that appear too high for frequent triggering.
Compression families often draw `vol_max` values so low that they become almost unreachable.

### Cause 3 — trend thresholds too high once combined with session/vol filters
A threshold that might be acceptable alone becomes too strict when paired with already-narrow session and volatility conditions.

### Cause 4 — XAU-specialist templates are leaking into XAG generation
`xau_impulse_pullback` and `xau_session_continuation` are clearly tuned around XAU-style session behavior but still show up in XAG generation.
That likely deepens the zero-trade problem for silver.

### Cause 5 — families are trying to describe rare ideal bars instead of viable recurring setups
The generator is often sampling “perfect” breakout/continuation bars instead of “tradable enough” setups.
That makes research diversity look good on disk while practical trigger frequency collapses.

---

## Proposed first generator constraints for the next patch batch

These are diagnosis-stage recommendations only. They are not yet implemented in this note.

### `vol_breakout`
- lower `vol_min` range materially
- lower `trend_min` ceiling
- avoid combining `rsi > 55` / `rsi < 45` with the highest volatility thresholds
- prefer one directional confirmer, not three

### `compression_breakout`
- raise `vol_max` floor so compression is reachable
- avoid requiring strong directional confirmation on the same bar as compression
- consider converting one branch into a two-step breakout proxy rather than pure same-bar compression+trend conjunction

### `session_breakout`
- soften `vol_min` and `trend_min` together for session-gated families
- avoid hard RSI requirements on both sides when session gating is already present
- prefer London/New York bias without always requiring a mature trend state

### `xau_impulse_pullback`
- narrow this family to XAU first instead of sharing it unchanged with XAG
- reduce simultaneous use of session + volatility + MA alignment + RSI window + fib requirement
- keep one “specialist” branch, but add one simpler branch that can actually fire

### `xau_session_continuation`
- lower the upper bound of `trend_min`
- use either RSI confirmation or strong MA/close alignment, not both by default
- keep the family session-aware, but do not require a fully mature continuation bar every time

---

## D2a conclusion

The Track D zero-trade diagnosis is now strong enough to support a conservative repair patch.

Most important conclusion:

> the breakout / continuation families are not mainly failing because the cheap prescreen is too strict
> they are failing because the generator currently samples too many near-impossible entry conjunctions

That means the next patch should focus on **family-specific entry simplification and tighter parameter priors**, not on loosening all downstream gates globally.
