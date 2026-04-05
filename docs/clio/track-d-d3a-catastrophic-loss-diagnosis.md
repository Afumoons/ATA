# Track D3a — Catastrophic-loss family diagnosis

Date: 2026-04-05
Owner: Clio Nova

## Scope

This note diagnoses families that do trade, but frequently do so in structurally broken ways.

Primary focus families:
- `ma_trend`
- `rsi_range`
- `pullback_trend`

Inputs used:
- `tmp/research_family_stage_summaries/XAUUSDm_M15.json`
- `tmp/research_family_stage_summaries/XAGUSDm_M15.json`
- sampled generated strategies from `strategies/generated/`
- spot backtest replay on saved feature sets

---

## Executive finding

The catastrophic-loss problem is distinct from the zero-trade problem.

These families are **not too strict**.
They are usually too permissive, badly balanced, or exit-broken.

The recurring failure signatures are:
- trend families entering too often on weak directional evidence
- range families fading without enough protection against persistent trend regimes
- exit templates that are sometimes badly aligned with the trade archetype, causing late exits, wrong-sided exits, or weak loss containment
- reward/risk mixes that are not sufficiently selective to compensate for noisy entry logic

So D3 is fundamentally a **sanity-priors and exit-coherence problem**.

---

## What the stage artifacts say

The family-stage summaries already separate these families from the pure `0 trade` group.

### XAUUSDm M15 artifact examples
- `ma_trend`: cheap-prescreen samples with huge trade counts but weak quality
  - `core15_XAUUSDm_M15_e971: tr=1061 pf=0.99 sh=-0.19 dd=9.8`
  - `core15_XAUUSDm_M15_dfeb: tr=516 pf=0.90 sh=-1.94 dd=14.1`
  - `core15_XAUUSDm_M15_4190: tr=1005 pf=0.89 sh=-3.13 dd=28.2`
- `pullback_trend`:
  - `pullback_trend_XAUUSDc_M15_5e67: tr=238 pf=0.11 sh=-31.88 dd=90.7`
- `rsi_range`:
  - `rsi_range_XAUUSDc_M15_42cc: tr=262 pf=0.00 sh=-39.78 dd=98.7`
  - `rsi_range_XAUUSDc_M15_8908: tr=262 pf=0.04 sh=-35.77 dd=95.3`

### XAGUSDm M15 artifact examples
- `ma_trend_XAGUSDc_M15_b448: tr=1076 pf=0.15 sh=-51.30 dd=98.3`
- `rsi_range_XAGUSDc_M15_5733: tr=184 pf=0.31 sh=-14.72 dd=54.6`
- `rsi_range_XAGUSDc_M15_3cc1: tr=183 pf=0.31 sh=-15.27 dd=53.7`

These are not “borderline misses”. These are structurally broken templates.

---

## Family-level diagnosis

## 1. `ma_trend`

Representative samples:
- XAU: `ma_short > ma_long and trend_strength > 0.077`
- XAU: `ma_short > ma_long and trend_strength > 0.088`
- XAG: `ma_short > ma_long and trend_strength > 0.33`

Observed issue:
- some XAU samples use extremely low `trend_min` values
- the base MA-trend template is extremely sparse in logic: it often asks for little more than MA ordering + trend threshold
- the exit template is randomly chosen from a generic pool and may not match the actual trade archetype well

Spot replay:
- `core15_XAUUSDm_M15_0025` -> `900 trades`, `PF 0.22`, `Sharpe -35.98`, `DD -68.97%`

Diagnosis:
- the low-threshold versions massively overtrade noise
- because the entry rule is so permissive, small directional fluctuations can repeatedly open positions
- with weak edge and generic exits, that becomes a churn-to-death family rather than a genuine trend specialist

Failure signature:
- **hyperactive degradation**: too many trades, terrible PF, deep but not necessarily instant collapse

## 2. `rsi_range`

Representative samples:
- XAU: `rsi < 35 and trend_strength > -0.08 and trend_strength < 0.08`
- XAG: same range template with generic exits like `rsi > 54` or `trend_strength < 0.1`

Observed issue:
- entry logic assumes the market is safely ranging if `trend_strength` sits inside a narrow band
- but this alone is not enough to protect against persistent directional drift or repeated fading in regime transitions
- exit rules are generic and sometimes weakly anchored to the fade idea

Spot replay:
- `core15_XAUUSDm_M15_007e` -> `175 trades`, `PF 0.30`, `Sharpe -13.77`, `DD -25.93%`
- `rsi_range_XAGUSDc_M15_004b` -> `223 trades`, `PF 0.00`, `Sharpe -37.18`, `DD -100.00%`

Diagnosis:
- this family is effectively fading too often without enough directional vetoes
- once it gets caught repeatedly fading a real move, the generic exits do not rescue it fast enough
- the loss profile is especially severe on XAG in the sampled run

Failure signature:
- **repeated fade liquidation**: medium-to-high trade count with near-total equity collapse

## 3. `pullback_trend`

Representative samples:
- XAU: `ma_short > ma_long and close > ma_long and rsi > 45 and rsi < 62 and trend_strength > 0.31`
- XAG: `ma_short > ma_long and close > open and close > ma_short and trend_strength > 0.34`

Observed issue:
- this family splits into two very different behaviors:
  - some samples become too strict and produce `0 trades`
  - others fire enough to lose badly
- when it does trade, the template can still be too permissive about “pullback quality” and too generic about exits

Artifact evidence:
- `pullback_trend_XAUUSDc_M15_5e67: tr=238 pf=0.11 sh=-31.88 dd=90.7`

Diagnosis:
- the family is not consistently enforcing a true pullback-and-resume structure
- some branches are really just trend-following with shallow confirmation
- if the entry is weak and the exits are generic, it can grind into extreme drawdown quickly

Failure signature:
- **incoherent branch behavior**: some samples go dead, others go destructive

---

## Exit-template problem

A major recurring issue is that all three families inherit from a broad generic exit pool:
- `rsi > {rsi_exit}`
- `rsi < {rsi_exit}`
- `trend_strength < {trend_exit}`
- `trend_strength > {trend_exit}`

Diagnosis:
- these exits are flexible but too unconstrained for family-specific coherence
- random pairing allows mismatch between entry archetype and exit logic

Examples of why this matters:
- a trend-following long can get paired with an exit threshold that does not meaningfully protect against trend failure early enough
- a range-fade setup can get paired with a trend-strength exit that still leaves it fading persistent drift repeatedly
- some exits are effectively very weak sign-flip checks around small values rather than robust invalidation logic

This does not explain all loss by itself, but it likely amplifies the destructive families.

---

## Top recurring causes of catastrophic loss

### Cause 1 — over-permissive trend templates
`ma_trend` in particular can enter on very weak directional evidence and then trade far too often.

### Cause 2 — weak family/exit coherence
The generator samples exits from a generic pool instead of from family-safe exit logic.
That allows structurally mismatched exit behavior.

### Cause 3 — range fade logic lacks enough anti-trend vetoes
`rsi_range` appears too willing to keep fading price action that is not safely mean-reverting.

### Cause 4 — pullback family mixes dead branches and reckless branches
`pullback_trend` currently lacks a tight shared definition of what counts as a valid pullback continuation.

### Cause 5 — catastrophic profiles already show up before later gates
These are not edge-case failures created by walk-forward or MC only.
Many bad families are already visibly broken at cheap prescreen.

---

## Proposed first sanity filters / priors for the next patch batch

These are diagnosis-stage recommendations only.

### `ma_trend`
- raise the floor of `trend_min`, especially for XAU core15 variants
- prevent the most permissive entry template from pairing with the weakest exit variants
- require at least one extra coherence check for the loosest MA-only branch

### `rsi_range`
- add stronger anti-trend vetoes
- restrict exit selection to fade-appropriate exits
- reduce the family’s tolerance for repeated mean-reversion attempts when drift is persistent

### `pullback_trend`
- make pullback structure more explicit instead of allowing overly broad trend continuation proxies
- separate “strict but viable” from “too strict to trade” branches
- tie exits more directly to pullback invalidation / time decay rather than generic random exit sampling

### global D3 repair direction
- stop allowing fully generic exit-template pairing for every family
- add family-specific exit pools or family-specific exit constraints
- reject obviously destructive archetypes earlier if trade count is extreme and PF/DD are already catastrophic

---

## D3a conclusion

The catastrophic-loss diagnosis is strong enough to guide the first repair patch.

Most important conclusion:

> the destructive families are not mostly suffering from lack of opportunity
> they are suffering from overly permissive entries, weak archetype coherence, and overly generic exits

That means the next patch should focus on **family-level sanity priors and exit pairing constraints**, not on broad acceptance loosening.
