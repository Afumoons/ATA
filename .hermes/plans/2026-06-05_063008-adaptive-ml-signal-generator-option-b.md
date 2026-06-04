# Adaptive ML Signal Generator (FreqAI-like Option B) Implementation Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** Build an adaptive prediction modeling system for ATA where ML can eventually become a direct BUY/SELL/HOLD signal generator that improves over time through prediction journaling, outcome feedback, scheduled retraining, champion/challenger validation, guarded promotion, and rollback.

**Architecture:** Add an ML subsystem that starts fully read-only/shadow and progresses through four explicit maturity stages: shadow prediction, advisory agreement, gated autonomous ML execution, and full adaptive model routing. The ML subsystem must integrate with ATA's existing specialist-strategy + routing-layer architecture, not replace governance, risk, live decay, walk-forward validation, or auditability.

**Tech Stack:** Python 3.11, pandas/parquet feature data, scikit-learn initially (HistGradientBoosting / RandomForest / LogisticRegression calibration), joblib/pickle model artifacts, JSONL audit journals, existing ATA modules (`research.features`, `research.regime`, `execution.signals`, `scheduler.main`, `config.py`, `ui_api`). Optional future dependency: LightGBM/XGBoost only after sklearn baseline is proven.

---

## Current Context From Repo Inspection

Repo path: `C:\laragon\www\autonomous_trading_ai`

Observed existing foundations:

- `research/features.py` already computes leakage-aware features and explicitly avoids future-looking Ichimoku Chikou leakage.
- `research/regime.py` already has regime labeling/model-output fields.
- `backtests/walkforward.py`, `backtests/monte_carlo.py`, and `backtests/evaluation.py` exist for validation.
- `strategies/generator.py`, `strategies/evolution.py`, and `strategies/pool.py` already support generated strategy lifecycle.
- `scheduler/main.py` already orchestrates data update, feature generation, evolution, walk-forward, Monte Carlo, live monitoring, live decay, and execution.
- `execution/signals.py` is the likely entry point for live strategy signal evaluation and broker execution.
- `execution/live_decay.py`, `execution/strategy_live_stats.py`, and `execution/trade_context_journal.py` provide useful live-performance infrastructure.
- `config.py` centralizes governance/routing/risk knobs and should receive ML settings.
- There is no detected `pyproject.toml`, `requirements.txt`, or lock file, so dependency changes must be handled carefully and documented.

Important ATA constraints:

- Existing architecture is specialist-strategy + routing-layer, not universal strategy search.
- Risk posture is intentionally aggressive; do not silently change existing drawdown/daily-limit settings.
- ML must fail closed. If model is missing, stale, invalid, or below threshold, ATA should skip ML-driven entries or fall back to non-ML behavior depending on stage.
- All ML decisions must be auditable with model version, features, confidence, expected return/risk, regime, gate reasons, and actual outcome later.

---

## Four-Stage Rollout Summary

### Stage 1 — Shadow Prediction Only

ML model predicts BUY/SELL/HOLD and confidence on every closed bar, but cannot influence live trading. It writes prediction journals and later outcome labels.

**Purpose:** Build evidence and calibration without risking capital.

### Stage 2 — Advisory Agreement Mode

ML becomes a filter/advisor for existing rule strategies. It does not create trades by itself. A rule-based signal must agree with ML direction and confidence.

**Purpose:** Let ML improve selectivity while rule strategies remain primary.

### Stage 3 — Gated Autonomous ML Execution

ML may generate its own trade signals, but only under strict gates: model health, confidence, regime fit, spread, risk, decay, champion status, and feature freshness.

**Purpose:** Controlled autonomous ML entries with hard kill-switches.

### Stage 4 — Full Adaptive Model Routing

Multiple specialist ML models compete by symbol/regime/session. ATA routes to the best healthy champion model, continuously benchmarks challengers in shadow, retrains periodically, and rolls back automatically on decay.

**Purpose:** Long-term maturity: the system becomes smarter because it collects data, validates itself, promotes only better models, and remembers performance by context.

---

## Global Design Principles

1. **No direct full-auto first.** Every model must pass shadow → advisory → gated → adaptive lifecycle.
2. **Champion/challenger only.** Never deploy a newly trained model directly. New models must beat current champion on out-of-sample metrics and shadow/live calibration.
3. **Walk-forward first.** Validation must use time-aware splits, not random splits.
4. **No leakage.** Labels may use future outcomes; features may not.
5. **Separate market edge from execution quality.** Journal both predicted market move and actual broker execution result.
6. **Fail closed.** Missing model, stale features, invalid confidence, or data anomalies must skip ML action, not trade blindly.
7. **Audit everything.** Every prediction, gate, promotion, rollback, and outcome must be JSONL-audited.
8. **Small account protection.** Live trade outcomes are valuable for calibration, but historical market data should remain the main training source until live sample size is statistically meaningful.
9. **Specialist routing.** Prefer many small specialist models over one universal model.
10. **Minimal dependencies first.** Start with sklearn models; add LightGBM/XGBoost only if justified by benchmark.

---

## Proposed File/Directory Layout

Create:

```text
ml/
  __init__.py
  config.py
  dataset.py
  labels.py
  features.py
  model_spec.py
  train.py
  predict.py
  registry.py
  journal.py
  outcome.py
  validation.py
  gates.py
  routing.py
  promotion.py
  decay.py
  reports.py
  artifacts/
    .gitkeep
  registry.json

scripts/
  ml_train_model.py
  ml_predict_shadow.py
  ml_label_outcomes.py
  ml_promote_challenger.py
  ml_governance_report.py
  ml_backfill_journal.py

tests/
  test_ml_labels.py
  test_ml_dataset.py
  test_ml_registry.py
  test_ml_prediction_journal.py
  test_ml_gates.py
  test_ml_promotion.py
  test_ml_outcome_labeling.py
  test_ml_execution_integration.py
  test_ml_scheduler_jobs.py
```

Modify:

```text
config.py
scheduler/main.py
execution/signals.py
ui_api/app.py
ui_api/models.py
ui_api/adapters.py
.gitignore
```

Generated runtime artifacts:

```text
ml/artifacts/{symbol}/{timeframe}/{model_id}/model.joblib
ml/artifacts/{symbol}/{timeframe}/{model_id}/metadata.json
ml/artifacts/{symbol}/{timeframe}/{model_id}/feature_schema.json
ml/artifacts/{symbol}/{timeframe}/{model_id}/validation_report.json
ml/prediction_journal.jsonl
ml/outcome_journal.jsonl
ml/promotion_audit.jsonl
ml/gate_audit.jsonl
ml/decay_audit.jsonl
ml/training_runs.jsonl
```

Important: Do not commit generated artifacts except `.gitkeep` and possibly a small test fixture under `tests/fixtures/`.

---

## Config Design

Add `MLConfig` to `config.py`.

Recommended initial defaults:

```python
@dataclass
class MLConfig:
    enabled: bool = False
    stage: str = "shadow"  # shadow|advisory|gated_autonomous|adaptive_routing
    managed_symbols: list[str] = field(default_factory=lambda: ["XAUUSDm", "BTCUSDm", "XAGUSDm"])
    timeframe: str = "M15"

    # Data freshness / safety
    max_feature_age_minutes: int = 30
    min_training_rows: int = 1000
    min_validation_rows: int = 300
    min_shadow_predictions_for_promotion: int = 300
    min_live_outcomes_for_live_calibration: int = 30

    # Labeling horizons
    prediction_horizons_bars: tuple[int, ...] = (4, 8, 16)
    primary_horizon_bars: int = 8
    neutral_return_threshold_atr: float = 0.10
    tp_atr_mult: float = 1.0
    sl_atr_mult: float = 0.8
    max_label_lookahead_bars: int = 16

    # Model thresholds
    min_shadow_confidence: float = 0.50
    min_advisory_confidence: float = 0.56
    min_gated_autonomous_confidence: float = 0.62
    min_adaptive_confidence: float = 0.65
    max_confidence_without_calibration: float = 0.70

    # Promotion thresholds
    min_validation_accuracy: float = 0.42  # 3-class baseline should be compared dynamically too
    min_validation_macro_f1: float = 0.35
    min_validation_profit_factor_proxy: float = 1.05
    min_validation_expectancy_atr: float = 0.02
    max_validation_drawdown_proxy_atr: float = 12.0
    min_challenger_improvement_pct: float = 5.0

    # Drift / decay
    decay_window_predictions: int = 200
    decay_min_samples: int = 50
    decay_max_brier_score: float = 0.26
    decay_min_directional_accuracy: float = 0.38
    decay_max_consecutive_bad_windows: int = 2

    # Scheduler intervals
    shadow_predict_interval_minutes: int = 5
    outcome_label_interval_minutes: int = 15
    retrain_interval_hours: int = 24
    governance_interval_minutes: int = 60

    # Risk coupling for ML-generated entries
    ml_max_open_positions_total: int = 2
    ml_max_open_positions_per_symbol: int = 1
    ml_risk_multiplier: float = 0.50
    ml_disable_on_news_lockout: bool = True
    ml_disable_on_wide_spread: bool = True

ml_config = MLConfig()
```

Rationale:

- `enabled=False` and `stage="shadow"` guarantee no immediate live behavior change.
- Confidence thresholds increase as autonomy increases.
- `ml_risk_multiplier=0.50` ensures direct ML entries start at reduced risk compared with normal strategy entries.
- Live daily risk posture is left untouched.

---

# Stage 1 — Shadow Prediction Only

## Objective

Build a prediction system that runs beside ATA without influencing trading. It trains baseline models, generates predictions per closed bar, logs all predictions, labels outcomes after enough bars, and produces a daily quality report.

## Stage 1 Acceptance Criteria

- Models can be trained from existing feature parquet without data leakage.
- Prediction command writes `ml/prediction_journal.jsonl`.
- Outcome labeler later writes/updates outcomes without rewriting history unsafely.
- Scheduler can run shadow predictions when `ml_config.enabled=True` and `stage="shadow"`.
- No code path can place ML-generated trades in Stage 1.
- Tests cover labels, dataset split, registry, prediction journal, and fail-closed behavior.

---

## Task 1.1: Create ML Package Skeleton

**Objective:** Add the ML module directory and import-safe stubs.

**Files:**
- Create: `ml/__init__.py`
- Create: `ml/artifacts/.gitkeep`
- Modify: `.gitignore`

**Steps:**

1. Create `ml/__init__.py` with package docstring.
2. Create empty `ml/artifacts/.gitkeep`.
3. Add generated artifact ignores to `.gitignore`:

```gitignore
ml/artifacts/**
!ml/artifacts/.gitkeep
ml/*.jsonl
ml/registry.json
```

**Verification:**

Run:

```bash
python -m pytest tests/test_bugfix_batch_20260406.py -q
```

Expected: existing tests still pass or fail only for pre-existing environment setup issues.

---

## Task 1.2: Add ML Config

**Objective:** Centralize all ML settings in `config.py`.

**Files:**
- Modify: `config.py`
- Test: `tests/test_ml_config.py`

**Implementation notes:**

- Add `MLConfig` dataclass after `RoutingConfig` or before global config instances.
- Export `ml_config = MLConfig()` near other global configs.
- Validate `stage` values in a helper if existing config style allows it.

**Tests:**

```python
def test_ml_config_defaults_are_safe():
    from autonomous_trading_ai.config import ml_config
    assert ml_config.enabled is False
    assert ml_config.stage == "shadow"
    assert ml_config.min_gated_autonomous_confidence > ml_config.min_advisory_confidence
    assert ml_config.ml_risk_multiplier <= 0.5
```

**Verification:**

```bash
python -m pytest tests/test_ml_config.py -q
```

---

## Task 1.3: Implement Leakage-Safe Labels

**Objective:** Convert historical feature rows into future outcome labels for BUY/SELL/HOLD without leaking future into features.

**Files:**
- Create: `ml/labels.py`
- Test: `tests/test_ml_labels.py`

**Label types:**

1. `future_return_{horizon}`: close-to-close return over N bars.
2. `direction_label`: `buy`, `sell`, or `hold` based on ATR-normalized future return.
3. `tp_sl_label`: which side hits first within max lookahead: `buy_tp`, `sell_tp`, `none`, optionally `ambiguous` when both hit same bar.
4. `trade_quality_label`: expected trade quality score in ATR units.

**Core functions:**

```python
def add_future_return_labels(df: pd.DataFrame, horizons: tuple[int, ...]) -> pd.DataFrame: ...
def add_direction_label(df: pd.DataFrame, horizon: int, neutral_threshold_atr: float) -> pd.DataFrame: ...
def add_tp_sl_first_touch_labels(df: pd.DataFrame, tp_atr_mult: float, sl_atr_mult: float, max_lookahead_bars: int) -> pd.DataFrame: ...
def drop_unlabelable_tail(df: pd.DataFrame, max_lookahead_bars: int) -> pd.DataFrame: ...
```

**Important rules:**

- Labels may use future `high/low/close`; feature columns may not.
- Tail rows without enough future bars must be marked unlabeled and excluded from training.
- Same-bar TP+SL ambiguity must not be counted as a confident win. Treat as `ambiguous` or conservative loss depending on objective.

**Tests:**

- Deterministic tiny dataframe where future return label is known.
- Tail rows become unlabeled.
- Same-bar TP and SL hit produces `ambiguous`.
- No generated feature column includes future label names.

**Verification:**

```bash
python -m pytest tests/test_ml_labels.py -q
```

---

## Task 1.4: Build Dataset Assembler

**Objective:** Load ATA feature parquet and produce train/validation/test datasets with time-aware splits.

**Files:**
- Create: `ml/dataset.py`
- Test: `tests/test_ml_dataset.py`

**Core functions:**

```python
@dataclass
class MLDataset:
    symbol: str
    timeframe: str
    feature_columns: list[str]
    train: pd.DataFrame
    validation: pd.DataFrame
    test: pd.DataFrame
    label_column: str


def load_feature_frame(symbol: str, timeframe: str, base_dir: Path | None = None) -> pd.DataFrame: ...
def infer_feature_columns(df: pd.DataFrame, label_columns: Iterable[str]) -> list[str]: ...
def build_ml_dataset(symbol: str, timeframe: str, config: MLConfig, base_dir: Path | None = None) -> MLDataset: ...
```

**Feature exclusion list:**

Exclude:

- `time`
- raw label/future columns
- object/string columns unless explicitly encoded
- any column matching `future_`, `_label`, `target`, `pnl`, `result`, `ticket`, `order`, `profit`

Keep:

- OHLCV-derived features if available
- regime/session/news columns only if known at bar close

**Split rule:**

Use chronological split, e.g. 60% train, 20% validation, 20% test, or existing walk-forward helper if easy to reuse.

**Tests:**

- Split preserves chronological order.
- Label/future columns are excluded from features.
- Empty/too-small dataset raises clear error.

**Verification:**

```bash
python -m pytest tests/test_ml_dataset.py -q
```

---

## Task 1.5: Implement Model Spec and Baseline Training

**Objective:** Train a simple robust baseline classifier/regressor using sklearn-compatible API.

**Files:**
- Create: `ml/model_spec.py`
- Create: `ml/train.py`
- Create: `scripts/ml_train_model.py`
- Test: `tests/test_ml_training_smoke.py`

**Initial model candidates:**

- `HistGradientBoostingClassifier` for 3-class direction.
- `LogisticRegression` with `StandardScaler` as calibration baseline.
- Optional `RandomForestClassifier` only if runtime acceptable.

**Model output:**

```python
@dataclass
class TrainedModelBundle:
    model_id: str
    symbol: str
    timeframe: str
    label_column: str
    feature_columns: list[str]
    model: Any
    metrics: dict[str, Any]
    created_at: str
```

**Training script CLI:**

```bash
python scripts/ml_train_model.py --symbol XAUUSDm --timeframe M15 --model-kind hist_gradient_boosting --stage challenger
```

**Verification:**

```bash
python scripts/ml_train_model.py --symbol XAUUSDm --timeframe M15 --dry-run
python -m pytest tests/test_ml_training_smoke.py -q
```

If local feature parquet is missing, the smoke test must use synthetic fixture data, not live broker data.

---

## Task 1.6: Add Model Registry

**Objective:** Track model artifacts, metadata, champion/challenger status, validation metrics, and deployment stage.

**Files:**
- Create: `ml/registry.py`
- Test: `tests/test_ml_registry.py`

**Registry schema:** `ml/registry.json`

```json
{
  "version": 1,
  "models": {
    "XAUUSDm:M15": {
      "champion_model_id": null,
      "challenger_model_ids": [],
      "shadow_model_ids": [],
      "disabled_model_ids": []
    }
  },
  "model_metadata": {
    "model_id": {
      "symbol": "XAUUSDm",
      "timeframe": "M15",
      "artifact_path": "ml/artifacts/XAUUSDm/M15/.../model.joblib",
      "feature_schema_path": ".../feature_schema.json",
      "validation_report_path": ".../validation_report.json",
      "status": "challenger",
      "stage_allowed": "shadow",
      "created_at": "...",
      "metrics": {}
    }
  }
}
```

**Core functions:**

```python
def load_registry(path: Path | None = None) -> MLRegistry: ...
def save_registry(registry: MLRegistry, path: Path | None = None) -> None: ...
def register_model(bundle: TrainedModelBundle, status: str = "challenger") -> str: ...
def get_champion(symbol: str, timeframe: str) -> ModelMetadata | None: ...
def get_shadow_models(symbol: str, timeframe: str) -> list[ModelMetadata]: ...
```

**Tests:**

- Atomic save/load.
- Register challenger.
- Promote champion updates old champion to previous/disabled according to policy.
- Missing registry returns empty structure.

**Verification:**

```bash
python -m pytest tests/test_ml_registry.py -q
```

---

## Task 1.7: Implement Prediction API

**Objective:** Load a registered model and generate auditable predictions on the latest closed feature row.

**Files:**
- Create: `ml/predict.py`
- Test: `tests/test_ml_predict.py`

**Prediction result:**

```python
@dataclass
class MLPrediction:
    prediction_id: str
    time: str
    symbol: str
    timeframe: str
    model_id: str
    model_status: str
    stage: str
    bar_time: str
    predicted_action: str  # buy|sell|hold
    confidence: float
    class_probabilities: dict[str, float]
    expected_return_atr: float | None
    regime: str | None
    session: str | None
    feature_snapshot_hash: str
    feature_schema_version: str
    reason: str
```

**Fail-closed cases:**

- No champion/shadow model → no prediction with `reason="no_model"`.
- Feature schema mismatch → no tradeable prediction with `reason="feature_schema_mismatch"`.
- Feature age too old → no tradeable prediction with `reason="stale_features"`.
- Confidence NaN/out-of-range → no tradeable prediction with `reason="invalid_confidence"`.

**Verification:**

```bash
python -m pytest tests/test_ml_predict.py -q
```

---

## Task 1.8: Implement Prediction Journal

**Objective:** Append every prediction to JSONL with atomic, parseable records.

**Files:**
- Create: `ml/journal.py`
- Create: `scripts/ml_predict_shadow.py`
- Test: `tests/test_ml_prediction_journal.py`

**Journal paths:**

- `ml/prediction_journal.jsonl`
- `ml/gate_audit.jsonl`

**Journal record fields:**

```json
{
  "prediction_id": "...",
  "created_at": "...",
  "bar_time": "...",
  "symbol": "XAUUSDm",
  "timeframe": "M15",
  "model_id": "...",
  "stage": "shadow",
  "predicted_action": "buy",
  "confidence": 0.64,
  "class_probabilities": {"buy": 0.64, "sell": 0.21, "hold": 0.15},
  "expected_return_atr": 0.18,
  "regime": "trend_up",
  "session": "london",
  "trade_taken": false,
  "gate_decision": "shadow_only",
  "gate_reasons": ["stage_shadow_no_execution"],
  "outcome_status": "pending"
}
```

**Duplicate control:**

Do not append duplicate predictions for same `symbol + timeframe + model_id + bar_time + stage` unless explicitly forced.

**Verification:**

```bash
python scripts/ml_predict_shadow.py --symbol XAUUSDm --timeframe M15 --dry-run
python -m pytest tests/test_ml_prediction_journal.py -q
```

---

## Task 1.9: Implement Outcome Labeler

**Objective:** Convert pending shadow predictions into actual outcomes once future bars are available.

**Files:**
- Create: `ml/outcome.py`
- Create: `scripts/ml_label_outcomes.py`
- Test: `tests/test_ml_outcome_labeling.py`

**Outcome fields:**

```json
{
  "prediction_id": "...",
  "resolved_at": "...",
  "actual_direction": "buy",
  "actual_return_atr": 0.32,
  "would_tp_before_sl": true,
  "would_sl_before_tp": false,
  "ambiguous_same_bar": false,
  "correct_direction": true,
  "quality_score": 0.32,
  "execution_adjusted_pnl": null,
  "source": "market_shadow"
}
```

**Rules:**

- Stage 1 outcomes are market-simulation outcomes, not broker PnL.
- Later stages add `execution_adjusted_pnl` when a real trade was taken.
- Never train on predictions from future relative to the target period.

**Verification:**

```bash
python scripts/ml_label_outcomes.py --symbol XAUUSDm --timeframe M15 --dry-run
python -m pytest tests/test_ml_outcome_labeling.py -q
```

---

## Task 1.10: Add Shadow Scheduler Job

**Objective:** Let ATA run shadow prediction and outcome labeling periodically.

**Files:**
- Modify: `scheduler/main.py`
- Test: `tests/test_ml_scheduler_jobs.py`

**Implementation notes:**

- Import ML modules lazily to avoid breaking scheduler if optional ML dependency is missing.
- Add scheduler jobs only when `ml_config.enabled is True`.
- Stage `shadow` should run:
  - `ml_predict_shadow` every `shadow_predict_interval_minutes`
  - `ml_label_outcomes` every `outcome_label_interval_minutes`
  - `ml_governance_report` every `governance_interval_minutes`

**Fail-closed behavior:**

Scheduler ML job exceptions must log errors but not kill core ATA scheduler.

**Verification:**

```bash
python -m pytest tests/test_ml_scheduler_jobs.py -q
```

---

## Task 1.11: Stage 1 Governance Report

**Objective:** Summarize model quality, calibration, sample size, stale data, and readiness for Stage 2.

**Files:**
- Create: `ml/reports.py`
- Create: `scripts/ml_governance_report.py`
- Optional Modify: `ui_api/app.py`, `ui_api/models.py`, `ui_api/adapters.py`

**Report fields:**

- Predictions count by symbol/model.
- Pending vs resolved outcomes.
- Directional accuracy by symbol/regime/session.
- Brier score/calibration approximation.
- Confidence buckets: 0.50-0.55, 0.55-0.60, etc.
- Buy/sell/hold confusion matrix.
- Expected-return vs actual-return correlation.
- Readiness recommendation: `not_ready`, `watch`, `ready_for_advisory`.

**Verification:**

```bash
python scripts/ml_governance_report.py --days 7
```

Expected: human-readable CLI summary plus JSON report under `ml/reports/` if implemented.

---

# Stage 2 — Advisory Agreement Mode

## Objective

Allow ML to filter existing rule-based ATA strategy signals, but not generate independent entries. ML must agree with a rule signal before the trade is allowed when advisory mode is enabled.

## Stage 2 Acceptance Criteria

- Existing rule strategies can still run normally when ML is disabled.
- In `stage="advisory"`, ML can allow/skip a rule signal based on direction agreement and confidence.
- All skipped signals are audited with reasons.
- Advisory mode has per-symbol/model kill switch.
- No ML-only trades are possible in Stage 2.

---

## Task 2.1: Add ML Gate Decision Model

**Objective:** Standardize gate decisions for shadow/advisory/gated/adaptive stages.

**Files:**
- Create: `ml/gates.py`
- Test: `tests/test_ml_gates.py`

**Core dataclass:**

```python
@dataclass
class MLGateDecision:
    allowed: bool
    stage: str
    action: str  # allow|skip|shadow|fallback
    reasons: list[str]
    confidence: float | None
    model_id: str | None
    prediction_id: str | None
```

**Advisory gate rules:**

- If ML disabled → `allowed=True`, reason `ml_disabled`.
- If stage != advisory → do not apply advisory filter.
- If no model/prediction → conservative configurable behavior; default should be `allowed=False` only if advisory strict mode is enabled. Recommended default for first rollout: `allowed=True` with audit `ml_unavailable_fallback_rule_signal` until Afu explicitly enables strict advisory.
- If rule signal direction equals ML action and confidence >= `min_advisory_confidence` → allow.
- If ML says hold or opposite direction → skip.

**Config addition:**

```python
advisory_strict_requires_model: bool = False
advisory_skip_on_opposite_signal: bool = True
advisory_skip_on_hold_signal: bool = False  # start less strict, tune later
```

**Verification:**

```bash
python -m pytest tests/test_ml_gates.py -q
```

---

## Task 2.2: Integrate Advisory Gate Into `execution/signals.py`

**Objective:** Apply ML agreement check just before broker execution for rule-based strategy signals.

**Files:**
- Modify: `execution/signals.py`
- Test: `tests/test_ml_execution_integration.py`

**Where to integrate:**

Find the point where a `StrategyDefinition` signal has produced a buy/sell decision and before calling `execute_trade`.

**Required audit fields:**

- strategy name
- symbol/timeframe
- rule signal direction
- ML prediction id
- ML model id
- ML action/confidence
- gate decision/reasons
- whether broker order was attempted

**Safety:**

- If ML module import fails and `ml_config.enabled=False`, behavior must be unchanged.
- If `ml_config.enabled=True` and stage is advisory, fail according to config (`advisory_strict_requires_model`).

**Verification:**

```bash
python -m pytest tests/test_ml_execution_integration.py tests/test_live_signal_hardening.py -q
```

---

## Task 2.3: Advisory Quality Report

**Objective:** Measure whether ML filtering improves rule-strategy results before allowing autonomy.

**Files:**
- Modify: `ml/reports.py`
- Test: `tests/test_ml_reports.py`

**Metrics:**

- Rule signals allowed by ML vs skipped by ML.
- Hypothetical result of skipped signals.
- Result of allowed signals.
- Difference in expectancy, drawdown proxy, and trade count.
- Per-strategy and per-family impact.

**Stage 2 promotion to Stage 3 requirements:**

- At least `min_shadow_predictions_for_promotion` resolved advisory decisions.
- Allowed bucket has better expectancy than skipped/opposite bucket.
- No severe concentration in one symbol/session.
- Model has stable calibration in last N predictions.

---

# Stage 3 — Gated Autonomous ML Execution

## Objective

Permit ML-generated entries without a rule-strategy signal, but only through a strict autonomous ML gate and reduced-risk execution path.

## Stage 3 Acceptance Criteria

- ML can produce candidate trade plans but cannot bypass ATA risk manager, spread checks, position limits, news lockout, live decay, or broker validation.
- Every ML trade uses a synthetic strategy identity like `ml_signal:{symbol}:{model_id}` for attribution.
- ML entries are limited by separate max open positions and risk multiplier.
- Automatic rollback disables model if decay rules trigger.

---

## Task 3.1: Create ML Signal Strategy Identity

**Objective:** Represent ML-generated entries in ATA's existing attribution systems.

**Files:**
- Create: `ml/routing.py`
- Modify: `execution/signals.py` or create `execution/ml_signals.py`
- Test: `tests/test_ml_execution_integration.py`

**Identity format:**

```text
ml_signal:{symbol}:{timeframe}:{model_id}
```

**Metadata:**

```json
{
  "family": "ml_signal_generator",
  "symbol": "XAUUSDm",
  "timeframe": "M15",
  "model_id": "...",
  "stage": "gated_autonomous",
  "regime": "trend_up",
  "session": "london"
}
```

**Verification:**

- Live stats can attribute ML trades separately from generated rule strategies.
- Ticket map can store ML strategy identity.

---

## Task 3.2: Implement Autonomous ML Gate

**Objective:** Decide whether a direct ML prediction may become a trade.

**Files:**
- Modify: `ml/gates.py`
- Test: `tests/test_ml_gates.py`

**Gates:**

1. `ml_config.enabled=True`
2. `stage in {"gated_autonomous", "adaptive_routing"}`
3. champion model only, not challenger
4. feature freshness OK
5. confidence >= stage threshold
6. prediction action not HOLD
7. model not decayed/disabled
8. spread not wide
9. no news lockout if enabled
10. max ML open positions not exceeded
11. symbol-specific position cap not exceeded
12. existing risk manager permits trade
13. current market regime is allowed by model metadata
14. model validation report is not stale
15. recent confidence calibration is within tolerance

**Fail-closed:**

Any missing required input should skip with explicit reason.

---

## Task 3.3: Build ML Trade Plan Generator

**Objective:** Convert an allowed ML prediction into a broker-safe trade plan.

**Files:**
- Create: `execution/ml_signals.py`
- Test: `tests/test_ml_execution_integration.py`

**Trade sizing:**

- Use existing risk manager if possible.
- Apply `ml_risk_multiplier` to reduce position size.
- SL/TP should be ATR-based initially:
  - SL = `sl_atr_mult`
  - TP = `tp_atr_mult` or expected-return-based with cap.
- Do not allow trade without valid SL.

**Audit:**

Write to `ml/gate_audit.jsonl` and existing execution audit/trades log.

---

## Task 3.4: Integrate ML Execution Scheduler

**Objective:** Run ML candidate generation on each execution interval without disrupting rule-based execution.

**Files:**
- Modify: `scheduler/main.py`
- Modify: `execution/signals.py` or call `execution/ml_signals.py`
- Test: `tests/test_ml_scheduler_jobs.py`

**Design:**

- Stage 3 can run after normal strategy signals or before, but should respect global open-position caps.
- Recommended: run rule strategies first, then ML if capacity remains. This avoids ML crowding out proven rule strategies.

**Verification:**

```bash
python -m pytest tests/test_ml_scheduler_jobs.py tests/test_execution_pool_selection.py -q
```

---

## Task 3.5: Add ML Decay and Auto-Rollback

**Objective:** Disable or downgrade models whose live/shadow performance degrades.

**Files:**
- Create: `ml/decay.py`
- Modify: `scheduler/main.py`
- Test: `tests/test_ml_decay.py`

**Decay triggers:**

- Consecutive bad windows above threshold.
- Directional accuracy below minimum in recent resolved predictions.
- Brier score above maximum.
- Live ML trades show loss streak or negative expectancy after minimum sample.
- Prediction confidence remains high while outcomes are poor.

**Actions:**

- `watch`: report only.
- `downgrade_to_advisory`: no direct ML trades.
- `disable_model`: model removed from champion role.
- `rollback_to_previous_champion`: if previous champion exists and is healthy.

**Audit record:**

```json
{
  "time": "...",
  "model_id": "...",
  "action": "rollback_to_previous_champion",
  "reason": "decay_brier_score_and_live_loss_streak",
  "metrics": {}
}
```

---

# Stage 4 — Full Adaptive Model Routing

## Objective

Evolve from one model per symbol into a managed ensemble of specialist models by symbol/regime/session, with champion/challenger promotion and continuous shadow benchmarking.

## Stage 4 Acceptance Criteria

- Registry supports multiple specialists per symbol/timeframe/context.
- Router chooses a healthy model based on current regime/session and historical context performance.
- Retraining creates challengers, not automatic champions.
- Promotion requires out-of-sample + shadow/live evidence.
- Rollback is automatic and audited.
- UI/API/reporting shows model health and routing decisions.

---

## Task 4.1: Extend Registry for Specialist Contexts

**Objective:** Track models by context key, not just symbol/timeframe.

**Files:**
- Modify: `ml/registry.py`
- Test: `tests/test_ml_registry.py`

**Context key:**

```text
{symbol}:{timeframe}:{regime}:{session}:{model_family}
```

Examples:

```text
XAUUSDm:M15:trend_up:london:direction_hgb
BTCUSDm:M15:high_vol:new_york:direction_hgb
XAGUSDm:M15:range:asia:direction_logreg
```

**Fallback routing:**

1. exact symbol+timeframe+regime+session specialist
2. symbol+timeframe+regime specialist
3. symbol+timeframe generalist
4. no model → skip ML autonomous trade

---

## Task 4.2: Adaptive Router

**Objective:** Choose the best healthy model for current context.

**Files:**
- Modify: `ml/routing.py`
- Test: `tests/test_ml_routing.py`

**Routing score:**

```text
score = validation_score
      * calibration_score
      * recent_shadow_score
      * live_expectancy_score
      * context_match_bonus
      * freshness_factor
      * decay_penalty
```

**Constraints:**

- Decayed/disabled models score zero.
- Challengers may be used for shadow benchmarking only unless explicitly promoted.
- If top score is below threshold, skip direct ML trade.

---

## Task 4.3: Scheduled Retraining Pipeline

**Objective:** Periodically retrain challengers using rolling historical windows plus validated live outcomes.

**Files:**
- Modify: `ml/train.py`
- Create: `scripts/ml_retrain_all.py`
- Modify: `scheduler/main.py`
- Test: `tests/test_ml_retraining.py`

**Training data strategy:**

- Use rolling historical market data as primary source.
- Use live outcomes for calibration weighting only until live sample is large.
- Keep at least two validation regimes/windows, not only newest data.
- Do not train on unresolved prediction outcomes.

**Cadence:**

- Daily retrain is acceptable for M15 models.
- Avoid retraining every candle.

**Output:**

- new model status = `challenger`
- eligible stage = `shadow`
- write `ml/training_runs.jsonl`

---

## Task 4.4: Promotion Engine

**Objective:** Promote challenger to champion only when it beats incumbent with robust evidence.

**Files:**
- Create: `ml/promotion.py`
- Create: `scripts/ml_promote_challenger.py`
- Test: `tests/test_ml_promotion.py`

**Promotion criteria:**

- New challenger beats champion by `min_challenger_improvement_pct` on validation composite.
- New challenger passes minimum directional accuracy/macro F1/profit-factor proxy.
- Shadow predictions show acceptable calibration.
- No leakage flags.
- No insufficient-trade/sample warnings.
- Performance is not concentrated in one tiny window.

**Composite score example:**

```text
0.30 * directional_accuracy_score
0.20 * macro_f1_score
0.20 * expectancy_atr_score
0.15 * calibration_score
0.10 * drawdown_proxy_score
0.05 * coverage_score
```

**Audit:**

Every promotion/rejection writes full reasons to `ml/promotion_audit.jsonl`.

---

## Task 4.5: UI/API ML Observability

**Objective:** Expose ML state in ATA dashboard/API.

**Files:**
- Modify: `ui_api/app.py`
- Modify: `ui_api/models.py`
- Modify: `ui_api/adapters.py`
- Test: `tests/test_ml_ui_api.py`

**Endpoints:**

```text
GET /api/ml/summary
GET /api/ml/models
GET /api/ml/predictions/recent
GET /api/ml/gates/recent
GET /api/ml/promotions/recent
GET /api/ml/decay/summary
```

**Summary fields:**

- current stage
- ML enabled/disabled
- champions by context
- challengers in shadow
- resolved prediction accuracy
- recent gate skips by reason
- live ML PnL summary if available
- readiness recommendation

---

## Task 4.6: Operator Governance Report

**Objective:** Give Afu a concise recurring report on whether ML is getting smarter or decaying.

**Files:**
- Modify: `ml/reports.py`
- Optional: Hermes cron/job prompt later, not in repo unless already managed there.

**Report format:**

- Status umum: OK / watch / degraded / disabled.
- Model champions: symbol/context/model/version.
- Top improvements: where challenger beats champion.
- Top risks: decay, overconfidence, sample size, drift.
- Gate summary: allowed/skipped/reasons.
- Outcome summary: confidence bucket vs actual result.
- Promotion/rollback actions.
- Needs Afu: approval for stage upgrade or risk changes.

---

# Validation Strategy

## Unit Tests

Run focused tests after each task:

```bash
python -m pytest tests/test_ml_labels.py -q
python -m pytest tests/test_ml_dataset.py -q
python -m pytest tests/test_ml_registry.py -q
python -m pytest tests/test_ml_gates.py -q
python -m pytest tests/test_ml_promotion.py -q
```

## Integration Tests

```bash
python -m pytest tests/test_ml_execution_integration.py tests/test_ml_scheduler_jobs.py -q
```

## Existing Regression Tests

At minimum:

```bash
python -m pytest tests/test_live_signal_hardening.py tests/test_execution_pool_selection.py tests/test_live_decay.py -q
```

If runtime allows, run full suite:

```bash
python -m pytest -q
```

## Manual Dry Runs

```bash
python scripts/ml_train_model.py --symbol XAUUSDm --timeframe M15 --dry-run
python scripts/ml_predict_shadow.py --symbol XAUUSDm --timeframe M15 --dry-run
python scripts/ml_label_outcomes.py --symbol XAUUSDm --timeframe M15 --dry-run
python scripts/ml_governance_report.py --days 7
```

## Promotion Readiness Checklist

Do not move to the next stage unless:

- All tests pass.
- Journal records are parseable.
- Model predictions are not duplicated per bar.
- Outcome labeling resolves correctly after lookahead window.
- No data leakage warning.
- Feature schema mismatch is detected.
- Confidence buckets are calibrated enough.
- Shadow/advisory evidence shows positive expectancy improvement.
- Rollback path has been tested.

---

# Risk Mitigation Matrix

## Overfitting

Mitigations:

- Walk-forward/time split only.
- Champion/challenger validation.
- Minimum sample sizes.
- Penalize low trade count and concentration.
- Same-bar ambiguity handled conservatively.
- Daily retrain only, not every candle.

## Market Regime Shift

Mitigations:

- Regime/session specialist routing.
- Drift/decay monitor.
- Rolling windows plus long-term validation.
- Auto-downgrade and rollback.

## Bad Model Directly Trading

Mitigations:

- Stage lifecycle.
- `enabled=False` default.
- Confidence thresholds.
- Risk multiplier.
- ML-specific open-position caps.
- Fail-closed gates.

## Data Leakage

Mitigations:

- Feature exclusion rules.
- Label-generation tests.
- Tail-row removal.
- No future/target column in feature schema.
- Audit feature schema per model artifact.

## Execution/Broker Noise Confused With Market Edge

Mitigations:

- Separate market shadow outcomes from execution-adjusted PnL.
- Journal spread/slippage/session/news where possible.
- Evaluate both raw prediction correctness and live broker result.

## Small Account / Sparse Live Data

Mitigations:

- Historical data primary training source.
- Live data used for calibration and validation first.
- Minimum live outcome threshold before live-performance-driven promotion.

## Operational Complexity

Mitigations:

- Start with sklearn baseline.
- JSONL and registry first; database later only if needed.
- Keep stage flags explicit.
- Add UI/API summary only after core journals are stable.

---

# Dependency Plan

Because no `pyproject.toml`, `requirements.txt`, or lock file was detected, first implementation should check what packages already exist in the active environment.

Recommended minimal dependencies:

- required: `pandas`, `numpy` (already implied by repo)
- required for initial ML: `scikit-learn`, `joblib`
- optional later: `lightgbm`, `xgboost`, `optuna`

Before adding dependencies:

```bash
python - <<'PY'
import importlib.util
for name in ['pandas', 'numpy', 'sklearn', 'joblib']:
    print(name, bool(importlib.util.find_spec(name)))
PY
```

If `sklearn`/`joblib` missing, decide the project's dependency management first. Do not silently vendor packages.

---

# Suggested Implementation Order

1. Stage 1 skeleton/config/labels/dataset.
2. Stage 1 baseline training/registry/prediction/journal/outcome/report.
3. Stage 1 scheduler integration.
4. Let shadow run until enough resolved predictions exist.
5. Stage 2 advisory gate + execution integration.
6. Let advisory run until enough evidence exists.
7. Stage 3 autonomous gate/trade plan/risk-limited execution.
8. Stage 3 decay/rollback.
9. Stage 4 specialist registry/router/retraining/promotion/UI.

Do not implement Stage 3 before Stage 1 and Stage 2 reports prove the model adds value.

---

# Commit Strategy

Commit after each meaningful slice:

```bash
git add config.py ml tests scripts
git commit -m "feat: add ml shadow prediction foundation"

git add ml/labels.py ml/dataset.py tests/test_ml_labels.py tests/test_ml_dataset.py
git commit -m "feat: add leakage-safe ml dataset labels"

git add ml/train.py ml/registry.py scripts/ml_train_model.py tests
git commit -m "feat: add ml training and registry"

git add ml/predict.py ml/journal.py scripts/ml_predict_shadow.py tests
git commit -m "feat: add ml shadow prediction journal"

git add ml/gates.py execution/signals.py tests
git commit -m "feat: add advisory ml signal gate"
```

Do not commit generated `ml/*.jsonl`, model artifacts, or local reports unless explicitly intended.

---

# Open Questions For Afu Before Stage 3 Only

No clarification is needed for Stage 1 planning/implementation. Before enabling Stage 3 live ML entries, ask Afu explicitly:

1. Which symbols can ML trade directly first? Recommended: XAUUSDm only, then BTCUSDm, then XAGUSDm.
2. What ML risk multiplier is acceptable? Recommended start: 0.25–0.50 of normal risk.
3. Should ML autonomous entries be allowed during news lockout? Recommended: no.
4. Should ML entries count toward same global max open positions? Recommended: yes, plus stricter ML-specific caps.
5. What minimum shadow/advisory sample size should be required before live direct ML? Recommended: at least 300 resolved predictions per symbol and 30+ real advisory/live outcomes.

---

# Final Definition of Done

This feature is done when ATA can demonstrate the full learning loop safely:

```text
features → ML prediction → journal → outcome label → quality report → retrain challenger → validate vs champion → promote or reject → gated execution → live outcome → decay/rollback
```

And when the system can answer these operator questions with real data:

- Which model is active for XAU/BTC/XAG right now?
- Why did ML buy/sell/hold/skip the latest bar?
- Is the model improving or decaying?
- Did the latest challenger beat the champion?
- What happened to predictions from the last 7/30 days?
- Did ML improve rule strategy selectivity in advisory mode?
- If ML traded directly, what was its standalone expectancy and drawdown?

Only after those answers are reliable should ATA be considered an adaptive ML signal generator that can become smarter and more mature over time.
