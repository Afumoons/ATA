import json

import pandas as pd

from autonomous_trading_ai.ml.outcome import label_pending_predictions


def _append_jsonl(path, record):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record) + "\n")


def test_label_pending_predictions_writes_lineage_fields_once(tmp_path):
    prediction_path = tmp_path / "prediction.jsonl"
    outcome_path = tmp_path / "outcome.jsonl"
    bar_times = pd.date_range("2026-01-01", periods=5, freq="15min", tz="UTC")
    _append_jsonl(
        prediction_path,
        {
            "prediction_id": "model-1:XAUUSDm:M15:2026-01-01T00:15:00+00:00",
            "outcome_status": "pending",
            "symbol": "XAUUSDm",
            "timeframe": "M15",
            "model_id": "model-1",
            "bar_time": bar_times[1].isoformat(),
            "predicted_action": "buy",
            "confidence": 0.61,
        },
    )
    frame = pd.DataFrame(
        {
            "time": bar_times,
            "close": [100.0, 101.0, 103.0, 104.0, 105.0],
            "atr": [2.0] * 5,
        }
    )

    first_written = label_pending_predictions(
        prediction_path,
        outcome_path,
        feature_frames={("XAUUSDm", "M15"): frame},
        horizon_bars=2,
        neutral_threshold_atr=0.1,
    )
    second_written = label_pending_predictions(
        prediction_path,
        outcome_path,
        feature_frames={("XAUUSDm", "M15"): frame},
        horizon_bars=2,
        neutral_threshold_atr=0.1,
    )

    assert first_written == 1
    assert second_written == 0
    records = [json.loads(line) for line in outcome_path.read_text(encoding="utf-8").splitlines()]
    assert len(records) == 1
    outcome = records[0]
    assert outcome["prediction_id"] == "model-1:XAUUSDm:M15:2026-01-01T00:15:00+00:00"
    assert outcome["symbol"] == "XAUUSDm"
    assert outcome["timeframe"] == "M15"
    assert outcome["model_id"] == "model-1"
    assert outcome["bar_time"] == bar_times[1].isoformat()
    assert outcome["horizon_bars"] == 2
    assert outcome["predicted_action"] == "buy"
    assert outcome["confidence"] == 0.61
    assert outcome["actual_direction"] == "buy"
    assert outcome["correct_direction"] is True
