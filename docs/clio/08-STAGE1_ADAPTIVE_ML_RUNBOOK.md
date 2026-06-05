# Stage 1 Adaptive ML Shadow Runbook

Purpose: give operators a repeatable command sequence for Stage 1 adaptive ML work without allowing ML to place, modify, size, or route live trades.

Stage 1 invariant:

- training may write shadow model artifacts and registry metadata
- prediction may write append-only shadow prediction journal records
- labeling may write append-only shadow outcome journal records
- evaluation may write aggregate JSON reports
- nothing in this runbook may call broker execution, live order modification, position sizing, or strategy promotion

## Environment wrapper

Run commands from the repository root. In Hermes/MSYS environments, clear inherited Python home variables before using the project venv:

```bash
unset PYTHONHOME UV_INTERNAL__PYTHONHOME
export PYTHONPATH=/c/laragon/www
PY=.venv/Scripts/python.exe
```

If the repo is run from WSL instead of Git Bash/MSYS, keep the same project venv command style only when the Windows venv is reachable from the current shell.

## 1. Dry-run dataset readiness

This checks whether feature files can build leakage-safe train/validation/test splits. It does not write model artifacts.

```bash
$PY scripts/ml_train_shadow_model.py \
  --symbol XAUUSDm \
  --timeframe M15 \
  --dry-run
```

Expected safe output shape:

```text
dry-run XAUUSDm M15: features=<n> train=<n> validation=<n> test=<n>
```

Stop and inspect data freshness if feature files are missing, split sizes are tiny, or the command fails.

## 2. Train a shadow model

Only run this after the dry-run dataset check is healthy. The trained model remains in the shadow registry bucket and must not promote a champion in Stage 1.

```bash
$PY scripts/ml_train_shadow_model.py \
  --symbol XAUUSDm \
  --timeframe M15 \
  --model-kind logistic_regression
```

Expected safe output shape:

```text
trained shadow model <model_id> for XAUUSDm M15
  artifact: <path>
  metrics: {...}
```

## 3. Dry-run shadow prediction gates

This exercises the prediction path using a temporary journal. It must not write prediction records to the configured journal.

```bash
$PY scripts/ml_predict_shadow.py \
  --symbol XAUUSDm \
  --timeframe M15 \
  --enable-shadow \
  --dry-run
```

Expected safe output shape:

```text
dry-run XAUUSDm M15: attempted=<n> written=<n> skipped=<n> reasons={...}
```

If the command skips because ML is disabled and `--enable-shadow` was omitted, rerun with `--enable-shadow`. That flag only enables Stage 1 journaling for this command; it still never permits execution.

## 4. Write shadow predictions

Run this only after the dry-run prediction gates are understood.

```bash
$PY scripts/ml_predict_shadow.py \
  --symbol XAUUSDm \
  --timeframe M15 \
  --enable-shadow
```

All records written by this command must contain:

- `stage = shadow`
- `trade_taken = false`
- `gate_decision = shadow_only`
- `outcome_status = pending`

## 5. Dry-run outcome labeling

This resolves eligible pending predictions into a temporary outcome journal first.

```bash
$PY scripts/ml_label_outcomes.py \
  --prediction-journal ml/journals/shadow_predictions.jsonl \
  --symbol XAUUSDm \
  --timeframe M15 \
  --dry-run
```

Expected safe output shape:

```text
dry-run outcomes_written=<n>
```

## 6. Write shadow outcome labels

Run this after dry-run outcome labeling confirms the available candles can resolve pending predictions.

```bash
$PY scripts/ml_label_outcomes.py \
  --prediction-journal ml/journals/shadow_predictions.jsonl \
  --outcome-journal ml/journals/shadow_outcomes.jsonl \
  --symbol XAUUSDm \
  --timeframe M15
```

Outcome records should preserve prediction lineage fields so evaluation can audit every label back to the original prediction.

## 7. Evaluate shadow performance

Evaluation aggregates prediction and outcome journals into an operator-readable JSON report.

```bash
$PY scripts/ml_evaluate_shadow.py \
  --prediction-journal ml/journals/shadow_predictions.jsonl \
  --outcome-journal ml/journals/shadow_outcomes.jsonl \
  --output ml/reports/shadow_evaluation_latest.json
```

Review at least:

- `overall.directional_accuracy`
- `overall.pending_outcomes`
- `overall.average_quality_score`
- `by_model`
- `by_symbol_timeframe`
- `safety_warnings`
- `trade_taken_count`

`trade_taken_count` must stay `0`. Any non-zero value is a Stage 1 safety violation and should block scheduler integration.

## Operator stop conditions

Stop before scheduler integration if any of these are true:

- prediction or outcome records show `trade_taken = true`
- a command path references broker order placement or live order modification
- model registry tries to promote a champion automatically
- evaluation has too few resolved outcomes to interpret
- quality or accuracy metrics are unstable across runs
- feature data is stale or missing for the target symbol/timeframe

## Suggested focused verification

```bash
unset PYTHONHOME UV_INTERNAL__PYTHONHOME
PYTHONPATH=/c/laragon/www .venv/Scripts/python.exe -m pytest \
  tests/test_ml_config.py \
  tests/test_ml_dataset.py \
  tests/test_ml_train_shadow.py \
  tests/test_ml_shadow_predict.py \
  tests/test_ml_outcomes.py \
  tests/test_ml_shadow_evaluation.py \
  tests/test_stage1_ml_runbook_docs.py \
  -q
```
