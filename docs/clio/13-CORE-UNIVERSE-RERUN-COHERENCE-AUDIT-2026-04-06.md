# Core Universe Rerun + Coherence Audit — 2026-04-06

## Scope

Fresh post-repair rerun and coherence audit for the Track D core universe:
- `XAUUSDm M15`
- `BTCUSDm M15`
- `XAGUSDm M15`

This audit was run after the latest BTC parity, XAG repair, and non-XAU metadata leakage fixes.

---

## What was run

### Focused validation

Ran from workspace root with workspace `PYTHONPATH`:

- `python -m pytest autonomous_trading_ai/tests/test_hardening_regime_and_generation.py -q`
- `python -m pytest autonomous_trading_ai/tests/test_live_manifest.py -q`

Result:
- `10 passed`
- `4 passed`

### Fresh research rerun

Ran:

- `python -c "from autonomous_trading_ai.scheduler.main import job_research_strategies; job_research_strategies(); print('job_research_strategies done')"`

Result:
- completed successfully
- refreshed family-stage artifacts for XAU/BTC/XAG under `tmp/research_family_stage_summaries/`
- refreshed `strategies/live_manifest.json`
- refreshed `strategies/strategy_index.json`

---

## Root-cause findings discovered during this audit

### 1. BTC Track D artifact emission regression was real

Observed at first rerun:
- `BTCUSDm_M15.json` was missing even though XAU and XAG artifacts refreshed

Root cause:
- `canonical_symbol('BTCUSDc')` returned `BTCUSDc` instead of `BTCUSDm`
- this prevented the BTC research slot from matching the core summary artifact allowlist

Fix landed:
- added `"BTCUSDc": "BTCUSDm"` to `SYMBOL_ALIASES` in `config.py`

Outcome after rerun:
- `tmp/research_family_stage_summaries/BTCUSDm_M15.json` now emits correctly

### 2. Compact family-stage log summary had an observability bug

Observed:
- compact family-stage log output could show all-zero counts even when the JSON artifact contained correct non-zero stage counts

Root cause:
- `_emit_family_stage_summary()` built the compact log view from the family payload row instead of `row['stages']`

Fix landed:
- compact log summary now reads from `stages`

Outcome after rerun:
- log summary now agrees with the persisted JSON artifact

---

## Fresh family-stage audit

## XAUUSDm M15

Artifact:
- `tmp/research_family_stage_summaries/XAUUSDm_M15.json`

Summary:
- 20 generated
- 20 cheap-prescreen fails
- 0 backtest survivors
- 0 walk-forward survivors
- 0 MC survivors
- 0 accepted/candidate/exploratory/active challengers

Interpretation:
- observability works
- generation diversity exists
- challenger quality is still too weak to survive the first hard gate
- XAU core live slot remains entirely dependent on pre-existing active inventory, not fresh challenger continuity

## BTCUSDm M15

Artifact:
- `tmp/research_family_stage_summaries/BTCUSDm_M15.json`

Summary:
- 20 generated
- 4 cheap-prescreen pass (`mixed:ma_trend+rsi_range` core family)
- 4 backtest pass
- 0 walk-forward pass
- 0 MC pass
- 0 accepted/candidate/exploratory/active challengers
- all 4 promising core-family candidates then died on `low_trade_count` before later stages

Interpretation:
- BTC artifact parity is now fixed
- BTC is the closest core slot to functional challenger continuity
- but it is still not end-to-end healthy because nothing converts into live-side challenger inventory

## XAGUSDm M15

Artifact:
- `tmp/research_family_stage_summaries/XAGUSDm_M15.json`

Summary:
- 20 generated
- 20 cheap-prescreen fails
- 0 backtest survivors
- 0 walk-forward survivors
- 0 MC survivors
- 0 accepted/candidate/exploratory/active challengers

Interpretation:
- XAG observability is healthy
- XAG family metadata repair is holding
- but quality remains materially broken: the slot still dies almost entirely at cheap prescreen

---

## Pool / manifest / observability coherence

## Family-stage observability

Status after fixes:
- `XAUUSDm_M15.json` present
- `BTCUSDm_M15.json` present
- `XAGUSDm_M15.json` present
- compact logs now agree with JSON stage counts

Conclusion:
- Track D family-stage observability is now coherent across the full core universe

## Live manifest

Current manifest facts:
- `entry_count = 32`
- `BTCUSDm`: 16 active entries
- `XAUUSDm`: 16 active entries
- `XAGUSDm`: 0 active entries
- all live manifest families remain `unknown` for both active XAU and active BTC entries

Interpretation:
- runtime manifest is coherent with current pool reality
- but core-universe parity is not yet achieved because XAG has no live footprint at all
- family-aware challenger generation is not yet feeding family-diverse live inventory

## Strategy index / pool state

Current strategy index counts:
- `XAUUSDm`: 673
- `BTCUSDm`: 365
- `XAGUSDm`: 0

Interpretation:
- the index remains effectively two-symbol
- XAG still does not have persistent pool/index continuity
- so the core universe is observably instrumented, but not yet operationally symmetric

---

## How close is the core universe to “all works”?

Short answer:
- **closer, but not close enough**

Detailed judgment:
- **Observability layer:** mostly works now
  - XAU/BTC/XAG artifact emission is coherent after the BTC alias fix
  - compact logs and JSON artifacts now agree
- **BTC slot:** partially works
  - fresh family-stage artifact now emits
  - some candidates survive cheap prescreen/backtest
  - later-stage continuity still fails
- **XAU slot:** stable but stagnant
  - live inventory exists
  - fresh challengers still die immediately
- **XAG slot:** still clearly not working end-to-end
  - no index/live presence
  - fresh challengers still all fail cheap prescreen

Overall score:
- the core universe is now **coherently inspectable**, but not yet **coherently healthy**
- practical status is roughly:
  - observability parity: **good**
  - BTC challenger continuity: **partial**
  - XAU challenger refresh health: **weak**
  - XAG slot viability: **not there yet**

If the target is “all works” meaning:
- artifacts emit
- summaries agree
- pool/manifest/index all reflect the same reality
- each core symbol can produce some credible new challenger flow

then current status is:
- **not yet there**
- best framing: **the instrumentation and audit surface now works; the strategy-quality engine still does not**

---

## Clean checkpoint conclusion

This batch should be treated as a coherent checkpoint because it:
- validated the latest repair surfaces
- exposed and fixed the BTC alias regression
- exposed and fixed the compact summary observability bug
- reran research successfully
- confirmed cross-symbol artifact coherence
- documented the remaining real blocker: strategy-quality survival, especially for XAG and fresh XAU challengers

## Recommended next focus

1. investigate whether BTC `low_trade_count` gating is too strict for otherwise-strong M15 core candidates
2. continue family-specific quality repair for XAG so at least some families survive cheap prescreen
3. inspect why live manifest families remain `unknown` even while family-stage artifacts are family-aware
