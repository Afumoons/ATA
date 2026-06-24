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
- [x] Decide next action: keep shadow-only, retrain, or improve labels/features
- [x] Document final recommendation and acceptance criteria
- [x] Audit BTC label/feature quality in more detail
- [x] Implement BTC-specific feature enrichment in the dataset builder
- [x] Verify BTC shadow retrain metrics improve on repo data
- [x] Audit XAU enrichment candidates for the highest-likelihood lift
- [x] Implement XAU session/news enrichment in the dataset builder
- [x] Verify XAU shadow retrain metrics improve on repo data

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

## Final Recommendation

- `XAUUSDm`: `retrain`
- `BTCUSDm`: `revise labels / features` before any retrain or promotion discussion
- Stage remains shadow-only for both symbols
- No promotion decision is justified yet

### Acceptance criteria for a future promotion discussion

#### XAUUSDm
- validation accuracy >= `0.45`
- macro F1 >= `0.35`
- profit factor proxy >= `1.05`
- expectancy ATR >= `0.02`
- shadow directional accuracy >= `0.50`
- confidence gap <= `0.08`
- Brier score <= `0.12`

#### BTCUSDm
- audit shows no obvious label-construction bug
- label mix is healthy enough to learn from: train split `buy=986`, `hold=138`, `sell=1236`
- the problem was feature signal quality, not a missing label class
- BTC-specific momentum/volatility features were added to the dataset builder
- latest shadow retrain on repo data improved materially: accuracy `0.4524`, macro F1 `0.3549`, PF proxy `1.1648`, expectancy ATR `0.1083`
- calibration / shadow-outcome review is still required before any promotion discussion
- stage remains shadow-only

## BTC Label/Feature Audit Notes

- BTC and XAU use the same 48 baseline numeric feature columns, so the issue was not a missing BTC-only feature set.
- BTC labels are not obviously malformed; class balance is comparable to XAU, and the same future-return threshold produces a usable three-class target.
- BTC's univariate feature signal was much weaker than XAU's:
  - mean ANOVA F-score: `2.3519` vs XAU's `4.9871`
  - median ANOVA F-score: `1.3597` vs XAU's `3.0966`
- BTC's strongest baseline features were shallow session/VWAP/RSI signals, but they did not separate the classes well enough for stable directional prediction.
- BTC-only enrichment now adds short-horizon return, body/range, wick, trend acceleration, VWAP distance, and volatility-change features during dataset assembly.
- Conclusion: BTC was a feature-quality / regime-signal problem, and the first fix is now in place.

## Current Working Hypothesis

- XAUUSDm is the stronger candidate right now
- BTCUSDm likely needs more improvement before it can be considered robust
- XAGUSDm stays out of scope until the XAU/BTC audit is complete

## XAU Enrichment Audit Notes

- XAU still underperforms badly on the current baseline model, so it is not safe to treat it as "done".
- I tested several enrichment families on the repo data:
  - price-action returns/body/range/wick features
  - session/time-of-day cyclic features
  - news proximity / lockout features
  - regime interaction features
- The most promising lift came from session/time-of-day enrichment, especially when combined with news features.
- The XAU session/news enrichment is now implemented in the dataset builder and verified on repo data.
- Best observed validation direction from the audit:
  - baseline logistic regression: accuracy `0.2389`, macro F1 `0.2289`, PF proxy `0.2741`, expectancy ATR `-0.8533`
  - session + news logistic regression: accuracy `0.2872`, macro F1 `0.2599`, PF proxy `0.4482`, expectancy ATR `-0.5707`
- That is still not production-worthy, but it is a real uplift from the prior baseline.
- Conclusion: if we continue enriching XAU, keep session/time-of-day + news-context features as the core, and then test lighter regime interactions on top.
