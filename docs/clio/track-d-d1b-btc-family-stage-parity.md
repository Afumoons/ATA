# Track D1b — BTC family-stage observability parity

Date: 2026-04-05
Owner: Clio Nova
Status: implemented, conservative parity extension

## Scope

This batch extends Track D family-stage JSON artifact emission to `BTCUSDm M15` so the official core-focus universe has comparable observability coverage:
- `XAUUSDm`
- `BTCUSDm`
- `XAGUSDm`

It does **not** change BTC generation priors, acceptance gates, or pool logic.
It is an observability-only parity step.

## What changed

Implemented in `scheduler/main.py`:
- expanded `RESEARCH_FAMILY_SUMMARY_SYMBOLS` from `{XAUUSDm, XAGUSDm}` to `{XAUUSDm, BTCUSDm, XAGUSDm}`

Result:
- `job_research_strategies()` will now persist the same family-stage JSON artifact for BTC that Track D already emits for XAU/XAG
- BTC diagnostics now have the same artifact-level surface for before/after comparison, family bottleneck inspection, and rerun audit notes

## New artifact path

After the next research rerun, Track D should emit:
- `tmp/research_family_stage_summaries/BTCUSDm_M15.json`

alongside:
- `tmp/research_family_stage_summaries/XAUUSDm_M15.json`
- `tmp/research_family_stage_summaries/XAGUSDm_M15.json`

## Why this is needed

The post-D4a rerun audit identified an explicit parity gap:
- BTC had functioning generation/pool/manifest continuity
- but BTC still lacked first-class Track D family-stage JSON artifacts

That made BTC harder to compare against XAU/XAG on the same diagnostic surface.

## Why this is conservative

This step intentionally does not:
- alter BTC strategy generation
- change research thresholds
- change acceptance or manifest behavior

It only closes the observability gap identified in `docs/clio/12-POST-D4A-RERUN-AUDIT.md`.
