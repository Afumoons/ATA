# Tasklist

## 2026-04-06 - Track D next high-impact batch

Completed in this checkpoint:
- [x] audit BTC `low_trade_count` failure mode after the 2026-04-06 coherence audit
- [x] patch inverted BTC challenger research trade floor conservatively
- [x] land XAG viability repair v2 with XAG-only prior changes
- [x] investigate why live manifest families remained mostly `unknown`
- [x] patch live manifest family recovery for legacy rule-only pool records
- [x] run focused tests for the above changes
- [x] rebuild runtime artifacts and verify live manifest `unknown` family count dropped to `0`
- [x] document the batch in `docs/clio/track-d-d5c-btc-gate-xag-v2-and-manifest-family-repair.md`

Still pending:
- [ ] run a fresh full Track D rerun to measure BTC challenger continuity after the gate fix
- [ ] run a fresh full Track D rerun to measure XAG cheap-prescreen survival after repair v2
- [ ] verify whether any XAG candidates now survive into pool/index/live-manifest continuity
