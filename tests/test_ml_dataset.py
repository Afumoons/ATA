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

    assert all(column in dataset.feature_columns for column in ["open", "high", "low", "close", "atr", "rsi"])
    assert dataset.train["time"].max() < dataset.validation["time"].min()
    assert dataset.validation["time"].max() < dataset.test["time"].min()
    assert dataset.train[dataset.label_column].notna().all()


def test_build_ml_dataset_adds_btc_specific_features(tmp_path):
    rows = 40
    df = pd.DataFrame(
        {
            "time": pd.date_range("2026-01-01", periods=rows, freq="15min", tz="UTC"),
            "open": [100 + i * 0.5 for i in range(rows)],
            "high": [100.8 + i * 0.5 for i in range(rows)],
            "low": [99.2 + i * 0.5 for i in range(rows)],
            "close": [100.3 + i * 0.5 for i in range(rows)],
            "atr": [2.0] * rows,
            "rsi": [50.0] * rows,
            "trend_strength": [0.1 * ((i % 5) - 2) for i in range(rows)],
            "session_vwap": [100.0 + i * 0.4 for i in range(rows)],
            "volatility": [0.01 + i * 0.0001 for i in range(rows)],
        }
    )
    feature_dir = tmp_path / "data" / "features"
    feature_dir.mkdir(parents=True)
    df.to_parquet(feature_dir / "BTCUSDm_M15_features.parquet")

    cfg = MLConfig(min_training_rows=5, min_validation_rows=3, max_label_lookahead_bars=2, primary_horizon_bars=1)
    dataset = build_ml_dataset("BTCUSDm", "M15", cfg, base_dir=tmp_path)

    for column in [
        "btc_return_1",
        "btc_return_2",
        "btc_return_4",
        "btc_return_8",
        "btc_body_atr",
        "btc_range_atr",
        "btc_wick_up_atr",
        "btc_wick_down_atr",
        "btc_trend_accel",
        "btc_vwap_distance_atr",
        "btc_volatility_change",
    ]:
        assert column in dataset.feature_columns
    assert "btc_return_1" not in infer_feature_columns(df, label_columns=["direction_label"])
    assert dataset.train[dataset.label_column].notna().all()


def test_build_ml_dataset_adds_xau_session_and_news_features(tmp_path):
    rows = 40
    df = pd.DataFrame(
        {
            "time": pd.date_range("2026-01-01", periods=rows, freq="15min", tz="UTC"),
            "open": [1800 + i * 0.2 for i in range(rows)],
            "high": [1801 + i * 0.2 for i in range(rows)],
            "low": [1799 + i * 0.2 for i in range(rows)],
            "close": [1800.4 + i * 0.2 for i in range(rows)],
            "atr": [3.0] * rows,
            "rsi": [50.0] * rows,
            "session_vwap": [1800.0 + i * 0.15 for i in range(rows)],
            "news_impact_level": [0, 1, 2, 3] * 10,
            "news_time_delta_min": [240.0, 120.0, 30.0, -15.0] * 10,
            "has_news_window": [False, False, True, True] * 10,
            "in_news_lockout": [False, False, False, True] * 10,
            "regime_confidence": [0.4 + 0.01 * (i % 5) for i in range(rows)],
            "trend_strength": [0.05 * ((i % 7) - 3) for i in range(rows)],
            "volatility": [0.02 + 0.0001 * i for i in range(rows)],
            "vol_regime": ["normal", "normal", "high", "high"] * 10,
        }
    )
    feature_dir = tmp_path / "data" / "features"
    feature_dir.mkdir(parents=True)
    df.to_parquet(feature_dir / "XAUUSDm_M15_features.parquet")

    cfg = MLConfig(min_training_rows=5, min_validation_rows=3, max_label_lookahead_bars=2, primary_horizon_bars=1)
    dataset = build_ml_dataset("XAUUSDm", "M15", cfg, base_dir=tmp_path)

    for column in [
        "xau_hour_sin",
        "xau_hour_cos",
        "xau_dow_sin",
        "xau_dow_cos",
        "xau_london_ny_overlap",
        "xau_london_open_window",
        "xau_ny_open_window",
        "xau_asia_london_transition",
        "xau_news_impact_sq",
        "xau_news_high_impact",
        "xau_news_medium_impact",
        "xau_news_delta_inv",
        "xau_news_urgent",
        "xau_news_stale",
        "xau_news_window_x_impact",
        "xau_news_lockout_x_impact",
        "xau_regime_trend_strength",
        "xau_regime_trend_strength_abs",
        "xau_regime_news_pressure",
    ]:
        assert column in dataset.feature_columns
    assert dataset.train[dataset.label_column].notna().all()


def test_build_ml_dataset_rejects_too_small_data(tmp_path):
    feature_dir = tmp_path / "data" / "features"
    feature_dir.mkdir(parents=True)
    pd.DataFrame({"time": ["2026-01-01"], "close": [1], "high": [1], "low": [1], "atr": [1]}).to_parquet(
        feature_dir / "XAUUSDm_M15_features.parquet"
    )

    with pytest.raises(ValueError, match="too small"):
        build_ml_dataset("XAUUSDm", "M15", MLConfig(min_training_rows=5, min_validation_rows=3), base_dir=tmp_path)
