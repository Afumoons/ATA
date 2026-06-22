# ML Quality Audit Tasklist — XAUUSDm + BTCUSDm Only

**Goal:** audit the current Stage 1 shadow ML models for XAUUSDm and BTCUSDm, then decide whether the models are good enough to keep as-is, need retraining, or need feature/label fixes before any promotion.

**Scope:**
- Focus only on `XAUUSDm` and `BTCUSDm`
- `XAGUSDm` is intentionally disabled during this audit
- Stage remains shadow-only; no live execution changes from ML

---

## Progress

- [x] Narrow scope to XAUUSDm + BTCUSDm only
- [x] Disable XAGUSDm in default scheduler / ML managed symbols
- [x] Rebuild the ML audit summary for XAUUSDm and BTCUSDm only
- [x] Compare validation metrics vs shadow outcome metrics
- [x] Build the phase-1 audit tooling for confusion matrix, class metrics, and confidence calibration
- [x] Add a symbol-filtered audit CLI so XAU/BTC can be reviewed without XAG noise
- [ ] Decide next action: keep shadow-only, retrain, or improve labels/features
- [ ] Document final recommendation and acceptance criteria

---

## Audit Snapshot

### Validation metrics

- `XAUUSDm:M15`
  - accuracy: `0.4320`
  - macro F1: `0.3254`
  - profit factor proxy: `0.9641`
  - expectancy ATR: `-0.0244`

- `BTCUSDm:M15`
  - accuracy: `0.3405`
  - macro F1: `0.2745`
  - profit factor proxy: `0.5487`
  - expectancy ATR: `-0.4408`

### Shadow outcome metrics

- `XAUUSDm:M15`
  - directional accuracy: `0.425386`
  - average quality score: `-0.104026`
  - predictions: `585`
  - resolved outcomes: `583`

- `BTCUSDm:M15`
  - directional accuracy: `0.103064`
  - average quality score: `-1.153094`
  - predictions: `722`
  - resolved outcomes: `718`

### Quick read

- XAU is the stronger symbol by a wide margin
- BTC is currently very weak on shadow quality
- both symbols still look shadow-only; neither is close to a promotion-ready ML state

---

## Phase 1 Deliverables Completed

### Tooling added
- `ml/evaluate.py`
  - confusion matrix
  - per-class precision / recall / F1
  - confidence summary
  - confidence calibration bins
- `scripts/ml_audit_quality.py`
  - symbol-filtered audit CLI
  - defaults to configured managed symbols
  - can export JSON report

### Tests added
- audit report aggregation coverage
- symbol filtering coverage for XAU/BTC-only audits
- confidence calibration coverage

---

## Audit Questions

1. Which symbol is currently healthier: XAUUSDm or BTCUSDm?
2. Are validation metrics aligned with shadow outcome quality?
3. Is there evidence of weak edge, leakage, or unstable calibration?
4. What is the minimum quality bar before any ML promotion discussion?

---

## Final Output We Want

- Per-symbol scorecard for XAUUSDm and BTCUSDm
- One clear verdict per symbol:
  - keep as-is
  - retrain
  - revise features / labels
- A short next-step plan with the highest-value ML work after the audit

---

## Current Working Hypothesis

- XAUUSDm is the stronger candidate right now
- BTCUSDm likely needs more improvement before it can be considered robust
- XAGUSDm stays out of scope until the XAU/BTC audit is complete
