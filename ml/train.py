"""Train Stage 1 shadow-only ML signal models.

Training registers models as ``status='shadow'``. It never promotes models to
champion and never enables live execution.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, f1_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from autonomous_trading_ai.config import MLConfig, ml_config
from autonomous_trading_ai.ml.dataset import MLDataset, build_ml_dataset
from autonomous_trading_ai.ml.model_spec import (
    FEATURE_SCHEMA_VERSION,
    FeatureSchema,
    ShadowModelArtifact,
    make_model_id,
    save_feature_schema,
    save_model_artifact,
    utc_now_iso,
)
from autonomous_trading_ai.ml.registry import ModelMetadata, register_model


_DEFAULT_ARTIFACT_DIR = Path(__file__).resolve().parent / "artifacts"
_DEFAULT_REGISTRY_PATH = Path(__file__).resolve().parent / "registry.json"


def _xy(frame: pd.DataFrame, dataset: MLDataset) -> tuple[pd.DataFrame, pd.Series]:
    return frame[dataset.feature_columns], frame[dataset.label_column].astype(str)


def _profit_factor_proxy(y_true: pd.Series, y_pred: list[str], returns_atr: pd.Series) -> float:
    gains = 0.0
    losses = 0.0
    for truth, pred, ret in zip(y_true, y_pred, returns_atr, strict=False):
        if pd.isna(ret):
            continue
        quality = float(ret) if pred == "buy" else -float(ret) if pred == "sell" else -abs(float(ret))
        if quality > 0:
            gains += quality
        elif quality < 0:
            losses += abs(quality)
    if losses == 0:
        return float("inf") if gains > 0 else 0.0
    return gains / losses


def _expectancy_atr(y_pred: list[str], returns_atr: pd.Series) -> float:
    scores: list[float] = []
    for pred, ret in zip(y_pred, returns_atr, strict=False):
        if pd.isna(ret):
            continue
        scores.append(float(ret) if pred == "buy" else -float(ret) if pred == "sell" else -abs(float(ret)))
    return float(sum(scores) / len(scores)) if scores else 0.0


def _validation_metrics(dataset: MLDataset, estimator: Pipeline, config: MLConfig) -> dict[str, Any]:
    x_val, y_val = _xy(dataset.validation, dataset)
    y_pred = list(estimator.predict(x_val))
    future_return_col = f"future_return_{config.primary_horizon_bars}"
    returns = pd.to_numeric(dataset.validation[future_return_col], errors="coerce")
    return {
        "validation_rows": int(len(dataset.validation)),
        "test_rows_reserved": int(len(dataset.test)),
        "accuracy": float(accuracy_score(y_val, y_pred)),
        "macro_f1": float(f1_score(y_val, y_pred, average="macro", zero_division=0)),
        "profit_factor_proxy": float(_profit_factor_proxy(y_val, y_pred, returns)),
        "expectancy_atr": float(_expectancy_atr(y_pred, returns)),
        "classes": sorted(set(y_val) | set(y_pred)),
    }


def _build_estimator(model_kind: str) -> Pipeline:
    if model_kind == "logistic_regression":
        return Pipeline(
            steps=[
                ("imputer", SimpleImputer(strategy="median")),
                ("scaler", StandardScaler()),
                (
                    "classifier",
                    LogisticRegression(max_iter=1000, class_weight="balanced", random_state=42),
                ),
            ]
        )
    if model_kind == "hist_gradient_boosting":
        return Pipeline(
            steps=[
                ("imputer", SimpleImputer(strategy="median")),
                ("classifier", HistGradientBoostingClassifier(max_iter=100, random_state=42)),
            ]
        )
    raise ValueError(f"unsupported Stage 1 model_kind: {model_kind}")


def train_shadow_model(
    symbol: str,
    timeframe: str | None = None,
    config: MLConfig | None = None,
    base_dir: Path | None = None,
    artifact_dir: Path | None = None,
    registry_path: Path | None = None,
    model_kind: str = "logistic_regression",
) -> ModelMetadata:
    """Train and register a shadow model for a symbol/timeframe."""
    cfg = config or ml_config
    tf = timeframe or cfg.timeframe
    dataset = build_ml_dataset(symbol, tf, cfg, base_dir=base_dir)
    x_train, y_train = _xy(dataset.train, dataset)
    if y_train.nunique() < 2:
        raise ValueError(f"cannot train {symbol} {tf}: need at least two label classes")

    estimator = _build_estimator(model_kind)
    estimator.fit(x_train, y_train)
    metrics = _validation_metrics(dataset, estimator, cfg)
    metrics["model_kind"] = model_kind

    created_at = utc_now_iso()
    model_id = make_model_id(symbol, tf, created_at=created_at)
    root_artifact_dir = Path(artifact_dir) if artifact_dir is not None else _DEFAULT_ARTIFACT_DIR
    model_dir = root_artifact_dir / model_id
    artifact_path = model_dir / "model.joblib"
    schema_path = model_dir / "feature_schema.json"
    report_path = model_dir / "validation_report.json"

    schema = FeatureSchema(
        version=FEATURE_SCHEMA_VERSION,
        symbol=symbol,
        timeframe=tf,
        feature_columns=dataset.feature_columns,
        label_column=dataset.label_column,
        created_at=created_at,
    )
    artifact = ShadowModelArtifact(
        model_id=model_id,
        symbol=symbol,
        timeframe=tf,
        estimator=estimator,
        feature_schema=schema,
        class_labels=sorted(estimator.classes_.tolist()),
        metrics=metrics,
    )
    save_model_artifact(artifact, artifact_path)
    save_feature_schema(schema, schema_path)
    report_path.write_text(pd.Series(metrics).to_json(indent=2), encoding="utf-8")

    metadata = ModelMetadata(
        model_id=model_id,
        symbol=symbol,
        timeframe=tf,
        artifact_path=str(artifact_path),
        feature_schema_path=str(schema_path),
        validation_report_path=str(report_path),
        status="shadow",
        stage_allowed="shadow",
        created_at=created_at,
        metrics=metrics,
    )
    register_model(metadata, registry_path=registry_path or _DEFAULT_REGISTRY_PATH)
    return metadata
