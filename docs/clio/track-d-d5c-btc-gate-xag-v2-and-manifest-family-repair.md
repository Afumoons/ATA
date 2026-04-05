# Track D5c - BTC gate audit, XAG repair v2, and live manifest family repair

Status: implemented, conservatively validated
Date: 2026-04-06

## Why this batch

Follow-up from `docs/clio/13-CORE-UNIVERSE-RERUN-COHERENCE-AUDIT-2026-04-06.md`:

1. BTC challengers looked promising after backtest but died on `low_trade_count`
2. XAG still failed 20/20 at cheap prescreen
3. live manifest family labels still rendered mostly `unknown`

This batch addresses the most direct causes without broad global relaxation.

## 1) BTC low-trade-count audit result

The BTC challenger gate was effectively inverted.

Previous logic:
- base BTC research min trades = `45`
- challenger branch used `max(60, base_min_trades - 40)`
- for BTC that resolved to `60`

So BTC challengers were being held to a *stricter* floor than ordinary BTC research candidates, not a softer exploratory floor.

That aligns with the rerun audit evidence where the strongest BTC challenger examples passed cheap prescreen and backtest quality but then died only on `low_trade_count` with trade counts in the low 20s.

### Conservative fix

Added `_challenger_research_min_trades(symbol)` in `scheduler/main.py` and wired challenger routing to it:
- `BTCUSDm` challenger floor: `30`
- `XAGUSDm` challenger floor: `25`
- `XAUUSDm` challenger floor: `60` (unchanged in practice)

This keeps BTC/XAG challenger gating softer than incumbent research gating without opening the floodgates globally.

## 2) XAG viability repair v2

Implemented a second XAG-only prior adjustment in `strategies/generator.py`.

Goal:
- reduce XAG zero-trade pressure in breakout/session/compression families
- soften the most obviously over-tight trigger surfaces
- avoid touching XAU/BTC priors

### Changes

For `XAGUSDm M15` only:
- `compression_breakout`
  - `vol_max`: `0.35 .. 0.85` (was `0.28 .. 0.65`)
  - `trend_min`: `0.02 .. 0.10` (was `0.03 .. 0.12`)
  - `time_stop_bars`: includes `12`
- `vol_breakout`
  - `vol_min`: `0.32 .. 0.70` (was `0.40 .. 0.85`)
  - `trend_min`: `0.04 .. 0.14` (was `0.05 .. 0.16`)
  - `time_stop_bars`: includes `10`
- `session_breakout`
  - `vol_min`: `0.32 .. 0.65` (was `0.40 .. 0.80`)
  - `trend_min`: `0.03 .. 0.12` (was `0.04 .. 0.14`)
  - `time_stop_bars`: includes `10`
- `pullback_trend`
  - `trend_min`: `0.08 .. 0.16` (was `0.10 .. 0.20`)
  - slightly tighter exit band
- `ma_trend`
  - `trend_min`: `0.14 .. 0.22` (was `0.16 .. 0.26`)
- `rsi_range`
  - `trend_min`: `0.02 .. 0.07` (was `0.03 .. 0.08`)
  - `trend_exit`: `-0.03 .. 0.03` (was `-0.04 .. 0.04`)
  - `vol_max`: `0.28 .. 0.60` (was `0.22 .. 0.45`)

This is still a prior repair, not a claim that XAG is now coherent end-to-end.
A fresh full rerun is still required to measure whether cheap-prescreen survival improves materially.

## 3) Live manifest family labels: direct cause and fix

Observed persisted reality:
- many legacy active pool records still carried `stats.strategy` with only rules / ATR fields
- family metadata was missing from those old strategy payloads
- manifest building relied on persisted family metadata, so top-level manifest families collapsed to `unknown`

### Fix

In `strategies/live_manifest.py`:
- import the existing template classifier from the generator
- infer family from `long_entry_rule` / `short_entry_rule` when persisted family metadata is missing
- seed minimal `params` with inferred family/playbook when legacy records have empty params

### Result

After rebuilding runtime artifacts from the current persisted pool:
- live manifest entries: `32`
- live manifest entries with family `unknown`: `0`
- BTC manifest families now resolve to concrete labels such as:
  - `ma_trend`
  - `rsi_range`
  - `mixed:ma_trend+rsi_range`
  - `mixed:rsi_range+ma_trend`

## Validation

### Unit / focused validation

Passed:
- `python -m pytest tests/test_hardening_regime_and_generation.py -q`
- `python -m pytest tests/test_live_manifest.py -q`

Coverage added:
- BTC/XAG challenger trade-floor assertions
- updated XAG prior-range assertions
- live manifest recovery of family labels from legacy rule-only payloads

### Runtime validation

Ran a direct runtime artifact rebuild from the current pool and confirmed:
- manifest saved successfully
- strategy index saved successfully
- live manifest `unknown` family count dropped to `0`

### Full rerun status

A full `job_research_strategies()` rerun was started, but intentionally stopped before completion to avoid leaving a half-finished long-running batch in the checkpoint.
This batch should therefore be treated as **code-fixed and conservatively validated**, not yet fully rerun-audited.

## Net effect

- BTC challenger gating is no longer accidentally stricter than normal BTC research gating
- XAG gets a second XAG-only viability repair pass aimed at zero-trade and over-tight-trigger failure modes
- live manifest family labels now recover correctly from the existing legacy pool

## Remaining next step

Run a fresh full Track D rerun and compare:
- BTC challenger post-backtest survival after the trade-floor fix
- XAG cheap-prescreen survival rate after v2 priors
- whether any XAG candidates finally gain pool/index/manifest continuity
