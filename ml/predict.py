"""Stage 1 shadow prediction runner.

This module only journals predictions. It deliberately has no broker/execution
integration and forces no-trade gate fields through ``MLPredictionRecord``.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from autonomous_trading_ai.config import MLConfig, ml_config
from autonomous_trading_ai.ml.dataset import load_feature_frame
from autonomous_trading_ai.ml.journal import MLPredictionRecord, append_prediction
from autonomous_trading_ai.ml.model_spec import ShadowModelArtifact, load_model_artifact
from autonomous_trading_ai.ml.registry import ModelMetadata, get_shadow_models


_DEFAULT_REGISTRY_PATH = Path(__file__).resolve().parent / "registry.json"
_DEFAULT_PREDICTION_JOURNAL_PATH = Path(__file__).resolve().parent / "prediction_journal.jsonl"


@dataclass
class ShadowPredictionResult:
    attempted: int
    written: int
    skipped: int
    reasons: list[str]


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _latest_closed_feature_row(features: pd.DataFrame) -> pd.Series:
    if features.empty:
        raise ValueError("feature frame is empty")
    df = features.copy()
    if "time" in df.columns:
        df["time"] = pd.to_datetime(df["time"], utc=True)
        df = df.sort_values("time").reset_index(drop=True)
    return df.iloc[-1]


def _bar_time(row: pd.Series) -> str:
    value = row.get("time")
    if value is None:
        return _utc_now_iso()
    return pd.Timestamp(value).tz_convert("UTC").isoformat() if pd.Timestamp(value).tzinfo else pd.Timestamp(value).tz_localize("UTC").isoformat()


def _class_probabilities(artifact: ShadowModelArtifact, row: pd.Series) -> dict[str, float]:
    x = pd.DataFrame([{column: row.get(column) for column in artifact.feature_schema.feature_columns}])
    estimator = artifact.estimator
    if not hasattr(estimator, "predict_proba"):
        prediction = str(estimator.predict(x)[0])
        return {label: 1.0 if label == prediction else 0.0 for label in artifact.class_labels}
    probs = estimator.predict_proba(x)[0]
    classes = [str(label) for label in estimator.classes_]
    return {label: float(prob) for label, prob in zip(classes, probs, strict=False)}


def _expected_return_proxy(probabilities: dict[str, float]) -> float:
    return float(probabilities.get("buy", 0.0) - probabilities.get("sell", 0.0))


def _latest_shadow_model(symbol: str, timeframe: str, registry_path: Path | None = None) -> ModelMetadata | None:
    models = get_shadow_models(symbol, timeframe, registry_path=registry_path or _DEFAULT_REGISTRY_PATH)
    if not models:
        return None
    return sorted(models, key=lambda item: item.created_at)[-1]


def build_prediction_record(
    artifact: ShadowModelArtifact,
    metadata: ModelMetadata,
    row: pd.Series,
    config: MLConfig,
) -> MLPredictionRecord:
    probabilities = _class_probabilities(artifact, row)
    if not probabilities:
        raise ValueError(f"model {metadata.model_id} returned no probabilities")
    predicted_action = max(probabilities, key=probabilities.get)
    confidence = float(probabilities[predicted_action])
    bar_time = _bar_time(row)
    prediction_id = f"{metadata.model_id}:{artifact.symbol}:{artifact.timeframe}:{bar_time}"
    regime = row.get("regime") if "regime" in row.index else row.get("regime_label") if "regime_label" in row.index else None
    session = row.get("session") if "session" in row.index else row.get("session_label") if "session_label" in row.index else None
    return MLPredictionRecord(
        prediction_id=prediction_id,
        created_at=_utc_now_iso(),
        bar_time=bar_time,
        symbol=artifact.symbol,
        timeframe=artifact.timeframe,
        model_id=metadata.model_id,
        model_status=metadata.status,
        stage="shadow",
        predicted_action=str(predicted_action),
        confidence=confidence,
        class_probabilities=probabilities,
        expected_return_atr=_expected_return_proxy(probabilities),
        regime=None if regime is None or (isinstance(regime, float) and math.isnan(regime)) else str(regime),
        session=None if session is None or (isinstance(session, float) and math.isnan(session)) else str(session),
        feature_snapshot_hash=artifact.feature_snapshot_hash(row),
        feature_schema_version=artifact.feature_schema.version,
        reason="shadow_prediction_only",
    )


def run_shadow_prediction(
    symbol: str,
    timeframe: str | None = None,
    config: MLConfig | None = None,
    base_dir: Path | None = None,
    registry_path: Path | None = None,
    prediction_journal_path: Path | None = None,
    feature_frame: pd.DataFrame | None = None,
) -> ShadowPredictionResult:
    """Run one shadow prediction and append it to the prediction journal.

    Fail-closed behavior: missing/disabled config, missing model, missing
    features, schema mismatch, or duplicate journal entry all result in no trade
    and a skipped result rather than an exception escaping to an execution path.
    """
    cfg = config or ml_config
    tf = timeframe or cfg.timeframe
    reasons: list[str] = []
    if cfg.stage != "shadow":
        return ShadowPredictionResult(attempted=0, written=0, skipped=1, reasons=["stage_not_shadow"])
    if not cfg.enabled:
        return ShadowPredictionResult(attempted=0, written=0, skipped=1, reasons=["ml_disabled"])

    metadata = _latest_shadow_model(symbol, tf, registry_path=registry_path)
    if metadata is None:
        return ShadowPredictionResult(attempted=0, written=0, skipped=1, reasons=["no_shadow_model"])

    try:
        artifact = load_model_artifact(Path(metadata.artifact_path))
        if artifact.symbol != symbol or artifact.timeframe != tf:
            return ShadowPredictionResult(attempted=1, written=0, skipped=1, reasons=["model_scope_mismatch"])
        features = feature_frame if feature_frame is not None else load_feature_frame(symbol, tf, base_dir=base_dir)
        row = _latest_closed_feature_row(features)
        missing = [column for column in artifact.feature_schema.feature_columns if column not in row.index]
        if missing:
            return ShadowPredictionResult(attempted=1, written=0, skipped=1, reasons=[f"missing_features:{','.join(missing[:5])}"])
        record = build_prediction_record(artifact, metadata, row, cfg)
        if not math.isfinite(record.confidence) or not 0.0 <= record.confidence <= 1.0:
            return ShadowPredictionResult(attempted=1, written=0, skipped=1, reasons=["invalid_confidence"])
        if any((not math.isfinite(float(value)) or float(value) < 0.0 or float(value) > 1.0) for value in record.class_probabilities.values()):
            return ShadowPredictionResult(attempted=1, written=0, skipped=1, reasons=["invalid_class_probabilities"])
        path = Path(prediction_journal_path) if prediction_journal_path is not None else _DEFAULT_PREDICTION_JOURNAL_PATH
        written = append_prediction(record, path=path)
        if not written:
            reasons.append("duplicate_prediction")
        return ShadowPredictionResult(attempted=1, written=1 if written else 0, skipped=0 if written else 1, reasons=reasons)
    except Exception as exc:  # fail closed for scheduler usage
        return ShadowPredictionResult(attempted=1, written=0, skipped=1, reasons=[f"fail_closed:{type(exc).__name__}:{exc}"])
