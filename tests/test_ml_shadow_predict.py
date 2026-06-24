import pandas as pd

from autonomous_trading_ai.config import MLConfig
from autonomous_trading_ai.ml.journal import read_jsonl
from autonomous_trading_ai.ml.predict import run_shadow_prediction
from autonomous_trading_ai.ml.train import train_shadow_model


def _feature_frame(rows=70):
    close = [100.0 + ((i % 12) - 6) * 0.35 + i * 0.03 for i in range(rows)]
    times = pd.date_range("2026-01-01", periods=rows, freq="15min", tz="UTC")
    hour = times.hour + times.minute / 60.0
    dow = times.dayofweek
    news_impact = [0, 1, 2, 3] * (rows // 4) + [0] * (rows % 4)
    news_delta = [240.0, 120.0, 30.0, -15.0] * (rows // 4) + [240.0] * (rows % 4)
    has_news = [False, False, True, True] * (rows // 4) + [False] * (rows % 4)
    in_lockout = [False, False, False, True] * (rows // 4) + [False] * (rows % 4)
    regime_confidence = [0.45 + 0.01 * (i % 5) for i in range(rows)]
    trend_strength = [((i % 13) - 6) / 10 for i in range(rows)]
    session_vwap = [100.0 + i * 0.02 for i in range(rows)]
    session_vwap_dist_atr = [((x - vwap) / 1.0) for x, vwap in zip(close, session_vwap, strict=False)]
    df = pd.DataFrame(
        {
            "time": times,
            "open": close,
            "high": [x + 1.0 for x in close],
            "low": [x - 1.0 for x in close],
            "close": close,
            "atr": [1.0] * rows,
            "rsi": [30.0 + (i % 40) for i in range(rows)],
            "trend_strength": trend_strength,
            "session_vwap": session_vwap,
            "session_vwap_dist_atr": session_vwap_dist_atr,
            "news_impact_level": news_impact,
            "news_time_delta_min": news_delta,
            "has_news_window": has_news,
            "in_news_lockout": in_lockout,
            "regime_confidence": regime_confidence,
            "vol_regime": ["normal", "normal", "high", "high"] * (rows // 4) + ["normal"] * (rows % 4),
            "regime": ["trending_down"] * rows,
            "session_label": ["asia"] * rows,
        }
    )
    df["xau_hour_sin"] = pd.Series(hour, index=df.index).pipe(lambda s: __import__('numpy').sin(2.0 * __import__('numpy').pi * s / 24.0))
    df["xau_hour_cos"] = pd.Series(hour, index=df.index).pipe(lambda s: __import__('numpy').cos(2.0 * __import__('numpy').pi * s / 24.0))
    df["xau_dow_sin"] = pd.Series(dow, index=df.index).pipe(lambda s: __import__('numpy').sin(2.0 * __import__('numpy').pi * s / 7.0))
    df["xau_dow_cos"] = pd.Series(dow, index=df.index).pipe(lambda s: __import__('numpy').cos(2.0 * __import__('numpy').pi * s / 7.0))
    df["xau_london_ny_overlap"] = ((times.hour >= 13) & (times.hour < 17)).astype(int)
    df["xau_london_open_window"] = ((times.hour >= 7) & (times.hour < 11)).astype(int)
    df["xau_ny_open_window"] = ((times.hour >= 13) & (times.hour < 17)).astype(int)
    df["xau_asia_london_transition"] = ((times.hour >= 7) & (times.hour < 10)).astype(int)
    df["xau_news_impact_sq"] = pd.Series(news_impact, index=df.index) ** 2
    df["xau_news_high_impact"] = (pd.Series(news_impact, index=df.index) >= 3).astype(int)
    df["xau_news_medium_impact"] = (pd.Series(news_impact, index=df.index) >= 2).astype(int)
    df["xau_news_delta_inv"] = 1.0 / (1.0 + pd.Series(news_delta, index=df.index).abs())
    df["xau_news_urgent"] = (pd.Series(news_delta, index=df.index).abs() <= 30.0).astype(int)
    df["xau_news_stale"] = (pd.Series(news_delta, index=df.index).abs() >= 180.0).astype(int)
    df["xau_news_window_x_impact"] = pd.Series(has_news, index=df.index).astype(int) * pd.Series(news_impact, index=df.index)
    df["xau_news_lockout_x_impact"] = pd.Series(in_lockout, index=df.index).astype(int) * pd.Series(news_impact, index=df.index)
    df["xau_regime_trend_strength"] = pd.Series(regime_confidence, index=df.index) * pd.Series(trend_strength, index=df.index)
    df["xau_regime_trend_strength_abs"] = pd.Series(regime_confidence, index=df.index) * pd.Series(trend_strength, index=df.index).abs()
    df["xau_regime_news_pressure"] = pd.Series(regime_confidence, index=df.index) * pd.Series(news_impact, index=df.index)
    return df


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
