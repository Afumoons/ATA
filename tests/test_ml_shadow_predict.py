import pandas as pd

from autonomous_trading_ai.config import MLConfig
from autonomous_trading_ai.ml.journal import read_jsonl
from autonomous_trading_ai.ml.predict import run_shadow_prediction
from autonomous_trading_ai.ml.train import train_shadow_model


def _feature_frame(rows=70):
    close = [100.0 + ((i % 12) - 6) * 0.35 + i * 0.03 for i in range(rows)]
    return pd.DataFrame(
        {
            "time": pd.date_range("2026-01-01", periods=rows, freq="15min", tz="UTC"),
            "open": close,
            "high": [x + 1.0 for x in close],
            "low": [x - 1.0 for x in close],
            "close": close,
            "atr": [1.0] * rows,
            "rsi": [30.0 + (i % 40) for i in range(rows)],
            "trend_strength": [((i % 13) - 6) / 10 for i in range(rows)],
            "session_label": ["asia"] * rows,
        }
    )


def test_shadow_prediction_disabled_fails_closed(tmp_path):
    result = run_shadow_prediction("XAUUSDm", "M15", config=MLConfig(enabled=False), prediction_journal_path=tmp_path / "pred.jsonl")
    assert result.written == 0
    assert result.reasons == ["ml_disabled"]


def test_shadow_prediction_journals_no_trade_record(tmp_path):
    feature_dir = tmp_path / "data" / "features"
    feature_dir.mkdir(parents=True)
    features = _feature_frame()
    features.to_parquet(feature_dir / "XAUUSDm_M15_features.parquet")

    cfg = MLConfig(
        enabled=True,
        min_training_rows=20,
        min_validation_rows=10,
        primary_horizon_bars=2,
        prediction_horizons_bars=(2, 4),
        max_label_lookahead_bars=4,
    )
    registry_path = tmp_path / "registry.json"
    metadata = train_shadow_model(
        "XAUUSDm",
        "M15",
        config=cfg,
        base_dir=tmp_path,
        artifact_dir=tmp_path / "artifacts",
        registry_path=registry_path,
    )
    journal_path = tmp_path / "prediction.jsonl"

    result = run_shadow_prediction(
        "XAUUSDm",
        "M15",
        config=cfg,
        base_dir=tmp_path,
        registry_path=registry_path,
        prediction_journal_path=journal_path,
    )
    duplicate = run_shadow_prediction(
        "XAUUSDm",
        "M15",
        config=cfg,
        base_dir=tmp_path,
        registry_path=registry_path,
        prediction_journal_path=journal_path,
    )

    assert result.written == 1
    assert duplicate.written == 0
    assert duplicate.reasons == ["duplicate_prediction"]
    records = read_jsonl(journal_path)
    assert len(records) == 1
    record = records[0]
    assert record["model_id"] == metadata.model_id
    assert record["trade_taken"] is False
    assert record["gate_decision"] == "shadow_only"
    assert record["outcome_status"] == "pending"
    assert record["predicted_action"] in {"buy", "sell", "hold"}
    assert 0.0 <= record["confidence"] <= 1.0
