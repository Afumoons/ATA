import json
import sys

from autonomous_trading_ai.ml.evaluate import build_shadow_evaluation_report


def _append_jsonl(path, record):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record) + "\n")


def test_build_shadow_evaluation_report_aggregates_prediction_and_outcome_journals(tmp_path):
    prediction_path = tmp_path / "prediction_journal.jsonl"
    outcome_path = tmp_path / "outcome_journal.jsonl"
    _append_jsonl(
        prediction_path,
        {
            "prediction_id": "p1",
            "symbol": "XAUUSDm",
            "timeframe": "M15",
            "model_id": "model-a",
            "predicted_action": "buy",
            "confidence": 0.72,
            "outcome_status": "pending",
            "trade_taken": False,
            "gate_decision": "shadow_only",
        },
    )
    _append_jsonl(
        prediction_path,
        {
            "prediction_id": "p2",
            "symbol": "XAUUSDm",
            "timeframe": "M15",
            "model_id": "model-a",
            "predicted_action": "sell",
            "confidence": 0.55,
            "outcome_status": "pending",
            "trade_taken": False,
            "gate_decision": "shadow_only",
        },
    )
    _append_jsonl(
        prediction_path,
        {
            "prediction_id": "p3",
            "symbol": "BTCUSDm",
            "timeframe": "M15",
            "model_id": "model-b",
            "predicted_action": "hold",
            "confidence": 0.51,
            "outcome_status": "pending",
            "trade_taken": False,
            "gate_decision": "shadow_only",
        },
    )
    _append_jsonl(
        outcome_path,
        {
            "prediction_id": "p1",
            "symbol": "XAUUSDm",
            "timeframe": "M15",
            "model_id": "model-a",
            "predicted_action": "buy",
            "actual_direction": "buy",
            "correct_direction": True,
            "quality_score": 0.8,
        },
    )
    _append_jsonl(
        outcome_path,
        {
            "prediction_id": "p2",
            "symbol": "XAUUSDm",
            "timeframe": "M15",
            "model_id": "model-a",
            "predicted_action": "sell",
            "actual_direction": "buy",
            "correct_direction": False,
            "quality_score": -0.3,
        },
    )

    report = build_shadow_evaluation_report(prediction_path, outcome_path)

    assert report["stage"] == "shadow"
    assert report["trade_taken_count"] == 0
    assert report["overall"] == {
        "predictions": 3,
        "resolved_outcomes": 2,
        "pending_outcomes": 1,
        "correct_direction": 1,
        "directional_accuracy": 0.5,
        "average_quality_score": 0.25,
    }
    assert report["by_model"]["model-a"]["predictions"] == 2
    assert report["by_model"]["model-a"]["resolved_outcomes"] == 2
    assert report["by_model"]["model-a"]["directional_accuracy"] == 0.5
    assert report["by_model"]["model-b"]["pending_outcomes"] == 1
    assert report["by_symbol_timeframe"]["XAUUSDm:M15"]["resolved_outcomes"] == 2
    assert report["by_symbol_timeframe"]["BTCUSDm:M15"]["pending_outcomes"] == 1


def test_build_shadow_evaluation_report_flags_non_shadow_trade_records(tmp_path):
    prediction_path = tmp_path / "prediction_journal.jsonl"
    outcome_path = tmp_path / "outcome_journal.jsonl"
    _append_jsonl(
        prediction_path,
        {
            "prediction_id": "p-live-leak",
            "symbol": "XAUUSDm",
            "timeframe": "M15",
            "model_id": "model-a",
            "predicted_action": "buy",
            "trade_taken": True,
            "gate_decision": "executed",
        },
    )

    report = build_shadow_evaluation_report(prediction_path, outcome_path)

    assert report["trade_taken_count"] == 1
    assert report["safety_warnings"] == ["prediction_journal_contains_trade_taken_records"]


def test_ml_evaluate_shadow_cli_prints_and_optionally_writes_report(tmp_path, monkeypatch, capsys):
    from autonomous_trading_ai.scripts.ml_evaluate_shadow import main

    prediction_path = tmp_path / "prediction_journal.jsonl"
    outcome_path = tmp_path / "outcome_journal.jsonl"
    output_path = tmp_path / "shadow_report.json"
    _append_jsonl(
        prediction_path,
        {
            "prediction_id": "p1",
            "symbol": "XAUUSDm",
            "timeframe": "M15",
            "model_id": "model-a",
            "predicted_action": "buy",
            "trade_taken": False,
        },
    )
    _append_jsonl(
        outcome_path,
        {
            "prediction_id": "p1",
            "symbol": "XAUUSDm",
            "timeframe": "M15",
            "model_id": "model-a",
            "correct_direction": True,
            "quality_score": 0.4,
        },
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "ml_evaluate_shadow.py",
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
    printed = json.loads(capsys.readouterr().out)
    written = json.loads(output_path.read_text(encoding="utf-8"))
    assert printed["overall"]["resolved_outcomes"] == 1
    assert written == printed
