import pandas as pd

from autonomous_trading_ai.config import MLConfig
from autonomous_trading_ai.ml.registry import get_shadow_models
from autonomous_trading_ai.ml.train import train_shadow_model


def _feature_frame(rows=60):
    close = [100.0 + ((i % 9) - 4) * 0.4 + i * 0.05 for i in range(rows)]
    return pd.DataFrame(
        {
            "time": pd.date_range("2026-01-01", periods=rows, freq="15min", tz="UTC"),
            "open": close,
            "high": [x + 1.0 for x in close],
            "low": [x - 1.0 for x in close],
            "close": close,
            "atr": [1.0] * rows,
            "rsi": [35.0 + (i % 30) for i in range(rows)],
            "trend_strength": [((i % 11) - 5) / 10 for i in range(rows)],
        }
    )


def test_train_shadow_model_registers_shadow_artifact(tmp_path):
    feature_dir = tmp_path / "data" / "features"
    feature_dir.mkdir(parents=True)
    _feature_frame().to_parquet(feature_dir / "XAUUSDm_M15_features.parquet")

    cfg = MLConfig(
        enabled=True,
        min_training_rows=20,
        min_validation_rows=10,
        primary_horizon_bars=2,
        prediction_horizons_bars=(2, 4),
        max_label_lookahead_bars=4,
    )
    registry_path = tmp_path / "registry.json"
    artifact_dir = tmp_path / "artifacts"

    metadata = train_shadow_model(
        "XAUUSDm",
        "M15",
        config=cfg,
        base_dir=tmp_path,
        artifact_dir=artifact_dir,
        registry_path=registry_path,
    )

    assert metadata.status == "shadow"
    assert metadata.stage_allowed == "shadow"
    assert (artifact_dir / metadata.model_id / "model.joblib").exists()
    assert metadata.metrics["validation_rows"] >= cfg.min_validation_rows
    assert metadata.metrics["model_kind"] == "logistic_regression"
    assert get_shadow_models("XAUUSDm", "M15", registry_path=registry_path)[0].model_id == metadata.model_id


def test_train_shadow_model_supports_hist_gradient_boosting(tmp_path):
    feature_dir = tmp_path / "data" / "features"
    feature_dir.mkdir(parents=True)
    _feature_frame(rows=80).to_parquet(feature_dir / "BTCUSDm_M15_features.parquet")

    cfg = MLConfig(
        enabled=True,
        min_training_rows=20,
        min_validation_rows=10,
        primary_horizon_bars=2,
        prediction_horizons_bars=(2, 4),
        max_label_lookahead_bars=4,
    )

    metadata = train_shadow_model(
        "BTCUSDm",
        "M15",
        config=cfg,
        base_dir=tmp_path,
        artifact_dir=tmp_path / "artifacts",
        registry_path=tmp_path / "registry.json",
        model_kind="hist_gradient_boosting",
    )

    assert metadata.status == "shadow"
    assert metadata.metrics["model_kind"] == "hist_gradient_boosting"
