import pandas as pd
import pytest

from autonomous_trading_ai.config import MLConfig
from autonomous_trading_ai.ml.dataset import build_ml_dataset, infer_feature_columns


def test_infer_feature_columns_excludes_future_labels_and_execution_fields():
    df = pd.DataFrame(
        {
            "time": pd.date_range("2026-01-01", periods=3, freq="15min", tz="UTC"),
            "rsi": [40.0, 50.0, 60.0],
            "future_return_8": [0.1, 0.2, 0.3],
            "direction_label": ["hold", "buy", "sell"],
            "ticket": [1, 2, 3],
            "note": ["a", "b", "c"],
        }
    )

    assert infer_feature_columns(df, label_columns=["direction_label"]) == ["rsi"]


def test_build_ml_dataset_uses_chronological_splits(tmp_path):
    rows = 30
    df = pd.DataFrame(
        {
            "time": pd.date_range("2026-01-01", periods=rows, freq="15min", tz="UTC"),
            "open": range(rows),
            "high": [x + 2 for x in range(rows)],
            "low": [x - 2 for x in range(rows)],
            "close": range(rows),
            "atr": [1.0] * rows,
            "rsi": [50.0] * rows,
        }
    )
    feature_dir = tmp_path / "data" / "features"
    feature_dir.mkdir(parents=True)
    df.to_parquet(feature_dir / "XAUUSDm_M15_features.parquet")

    cfg = MLConfig(min_training_rows=5, min_validation_rows=3, max_label_lookahead_bars=2, primary_horizon_bars=1)
    dataset = build_ml_dataset("XAUUSDm", "M15", cfg, base_dir=tmp_path)

    assert dataset.feature_columns == ["open", "high", "low", "close", "atr", "rsi"]
    assert dataset.train["time"].max() < dataset.validation["time"].min()
    assert dataset.validation["time"].max() < dataset.test["time"].min()
    assert dataset.train[dataset.label_column].notna().all()


def test_build_ml_dataset_rejects_too_small_data(tmp_path):
    feature_dir = tmp_path / "data" / "features"
    feature_dir.mkdir(parents=True)
    pd.DataFrame({"time": ["2026-01-01"], "close": [1], "high": [1], "low": [1], "atr": [1]}).to_parquet(
        feature_dir / "XAUUSDm_M15_features.parquet"
    )

    with pytest.raises(ValueError, match="too small"):
        build_ml_dataset("XAUUSDm", "M15", MLConfig(min_training_rows=5, min_validation_rows=3), base_dir=tmp_path)
