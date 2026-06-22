import json
import sys

from autonomous_trading_ai.scripts.ml_audit_quality import main


def _append_jsonl(path, record):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record) + "\n")


def test_ml_audit_quality_filters_to_managed_symbols(tmp_path, monkeypatch, capsys):
    prediction_path = tmp_path / "prediction_journal.jsonl"
    outcome_path = tmp_path / "outcome_journal.jsonl"
    output_path = tmp_path / "audit.json"

    _append_jsonl(
        prediction_path,
        {
            "prediction_id": "xau-1",
            "symbol": "XAUUSDm",
            "timeframe": "M15",
            "model_id": "xau-model",
            "predicted_action": "buy",
            "confidence": 0.9,
            "trade_taken": False,
        },
    )
    _append_jsonl(
        prediction_path,
        {
            "prediction_id": "btc-1",
            "symbol": "BTCUSDm",
            "timeframe": "M15",
            "model_id": "btc-model",
            "predicted_action": "sell",
            "confidence": 0.8,
            "trade_taken": False,
        },
    )
    _append_jsonl(
        prediction_path,
        {
            "prediction_id": "xag-1",
            "symbol": "XAGUSDm",
            "timeframe": "M15",
            "model_id": "xag-model",
            "predicted_action": "buy",
            "confidence": 0.7,
            "trade_taken": False,
        },
    )
    _append_jsonl(
        outcome_path,
        {
            "prediction_id": "xau-1",
            "symbol": "XAUUSDm",
            "timeframe": "M15",
            "model_id": "xau-model",
            "predicted_action": "buy",
            "actual_direction": "buy",
            "correct_direction": True,
            "quality_score": 0.4,
            "confidence": 0.9,
        },
    )
    _append_jsonl(
        outcome_path,
        {
            "prediction_id": "btc-1",
            "symbol": "BTCUSDm",
            "timeframe": "M15",
            "model_id": "btc-model",
            "predicted_action": "sell",
            "actual_direction": "buy",
            "correct_direction": False,
            "quality_score": -0.6,
            "confidence": 0.8,
        },
    )
    _append_jsonl(
        outcome_path,
        {
            "prediction_id": "xag-1",
            "symbol": "XAGUSDm",
            "timeframe": "M15",
            "model_id": "xag-model",
            "predicted_action": "buy",
            "actual_direction": "buy",
            "correct_direction": True,
            "quality_score": 0.9,
            "confidence": 0.7,
        },
    )

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "ml_audit_quality.py",
            "--prediction-journal",
            str(prediction_path),
            "--outcome-journal",
            str(outcome_path),
            "--output",
            str(output_path),
        ],
    )

    exit_code = main()

    assert exit_code == 0
    report = json.loads(capsys.readouterr().out)
    written = json.loads(output_path.read_text(encoding="utf-8"))
    assert report == written
    assert report["overall"]["predictions"] == 2
    assert report["overall"]["resolved_outcomes"] == 2
    assert set(report["by_symbol_timeframe"].keys()) == {"BTCUSDm:M15", "XAUUSDm:M15"}
    assert "XAGUSDm:M15" not in report["by_symbol_timeframe"]
    assert report["by_model"]["xau-model"]["directional_accuracy"] == 1.0
    assert report["by_model"]["btc-model"]["directional_accuracy"] == 0.0
