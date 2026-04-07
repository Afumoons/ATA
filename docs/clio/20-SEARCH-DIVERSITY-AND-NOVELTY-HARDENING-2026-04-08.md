# 20 – Search Diversity, Novelty Gating, Pool Cleanup & Motif-Aware Selection (2026-04-08)

## Summary

This document captures the RC1–RC5 remediation work implemented on 2026-04-08.

The system previously suffered from:

1. **template overload / low semantic diversity**
2. **parent-selection inbreeding loops**
3. **late duplicate detection after expensive compute**
4. **entry/exit semantic mismatch from random exit sampling**
5. **scalar scoring that rewarded broad mediocrity over sharp specialists**

That combination created a large but misleading strategy inventory dominated by
variants of the same logic.

## Implemented Changes

### Phase 1 — Research Hardening

Implemented in code and committed earlier on 2026-04-08:

- **pre-backtest structural dedup** against both pool and generated archive
- **family-stratified parent selection** instead of pure top-score parent cut
- **structural mutation path** in evolution, not only parameter mutation
- **family-compatible exit sampling** using weighted exit-template selection
- **specialist-aware scoring** with a bonus for strong regime sharpness
- **penalty for mediocre-everywhere strategies**
- **family oversaturation guard** for generated archive growth

### Phase 2 — Semantic Novelty Gating

Implemented in code and committed earlier on 2026-04-08:

- **semantic fingerprinting / similarity scoring**
- **near-duplicate gate** before full backtest
- **research novelty score** persisted into backtest/evaluation stats
- **clone-similarity penalty** and **novelty bonus** in evaluation

This moved the system from exact dedup only to approximate semantic duplicate
handling.

### Phase 3 — Motif-Aware Multi-Objective Selection

Implemented in code and committed earlier on 2026-04-08:

- **canonical motif mapping** (e.g. `trend_continuation`, `trend_pullback`,
  `range_fade`, `volatility_breakout`, `compression_expansion`,
  `session_breakout`, `structure_confluence`)
- **motif-aware semantic similarity**
- **research motif tagging** persisted into stats
- **motif-aware live manifest / strategy index**
- **bucketed live selection** balancing:
  - specialist candidates
  - novel candidates
  - robust candidates
- **motif cap** in live selection, in addition to family/regime caps

This turned the live selection layer from a mostly scalar rank cut into a more
portfolio-aware inventory selection process.

## Pool Cleanup Performed

The historical pool state was also cleaned on 2026-04-08.

### Structural pool dedup result

- before cleanup: **200 strategies**
- structural duplicates removed: **98**
- after cleanup: **102 strategies**

Retention rule:

1. keep the higher status rank (`active > exploratory > candidate > disabled > retired`)
2. break ties by score

### Metadata repair result

The historical pool had broken/missing `family` metadata (`unknown` in all
records at field level).

A metadata rebuild pass was applied to populate:

- `stats.family`
- `stats.playbook_type`
- `stats.motif`
- `stats.strategy.family`
- `stats.strategy.playbook_type`
- `stats.strategy.motif`
- `stats.strategy.params.family`
- `stats.strategy.params.playbook_type`
- `stats.strategy.params.motif`

### Runtime artifact rebuild result

After pool cleanup and metadata repair, runtime artifacts were rebuilt:

- `live_manifest.json` rebuilt with **32 entries**
- `strategy_index.json` rebuilt with **102 entries**

## Practical Outcome

The system should now be thought of as:

- **more compute-efficient**
- **less clone-tolerant**
- **more novelty-aware**
- **more specialist-aware**
- **more motif-aware**
- **more portfolio-aware in live selection**

This does **not** mean the historical pool instantly became diverse.
It means the engine is now materially better positioned to produce a healthier
pool over subsequent research cycles.

## Known Limitation After Cleanup

The cleaned historical pool still shows very strong legacy concentration in old
logic families when inferred from rules. In practice, the historical inventory
remains dominated by descendants of:

- `ma_trend`
- `rsi_range`

That is expected: the engine has been fixed, but the historical pool was built
under older search dynamics.

## Recommended Next Step

Run fresh research cycles and audit:

- family distribution
n- motif distribution
- novelty-score distribution
- acceptance by family/motif
- live-manifest composition by family/motif

The value of the 2026-04-08 hardening work will show up most clearly after new
inventory is generated under the upgraded pipeline.
