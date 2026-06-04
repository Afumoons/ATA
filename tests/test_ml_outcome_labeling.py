import pandas as pd

from autonomous_trading_ai.ml.outcome import label_pending_predictions
from autonomous_trading_ai.ml.journal import read_jsonl


def test_label_pending_predictions_writes_market_shadow_outcomes(tmp_path):
    pred_path = tmp_path / "prediction_journal.jsonl"
    outcome_path = tmp_path / "outcome_journal.jsonl"
    pred_path.write_text(
        '{"prediction_id":"p1","bar_time":"2026-01-01T00:00:00+00:00","symbol":"XAUUSDm","timeframe":"M15","predicted_action":"buy","outcome_status":"pending"}\n',
        encoding="utf-8",
    )
    features = pd.DataFrame(
        {
            "time": pd.date_range("2026-01-01", periods=4, freq="15min", tz="UTC"),
            "high": [100, 102, 103, 104],
            "low": [100, 99, 100, 101],
            "close": [100, 101, 102, 103],
            "atr": [2, 2, 2, 2],
        }
    )

    written = label_pending_predictions(
        prediction_journal_path=pred_path,
        outcome_journal_path=outcome_path,
        feature_frames={("XAUUSDm", "M15"): features},
        horizon_bars=2,
    )

    records = read_jsonl(outcome_path)
    assert written == 1
    assert records[0]["prediction_id"] == "p1"
    assert records[0]["actual_direction"] == "buy"
    assert records[0]["correct_direction"] is True
    assert records[0]["source"] == "market_shadow"
