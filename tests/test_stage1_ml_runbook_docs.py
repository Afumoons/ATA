from pathlib import Path


RUNBOOK = Path(__file__).resolve().parents[1] / "docs" / "clio" / "08-STAGE1_ADAPTIVE_ML_RUNBOOK.md"


def test_stage1_ml_runbook_documents_safe_full_cycle_commands():
    text = RUNBOOK.read_text(encoding="utf-8")

    required_commands = [
        "scripts/ml_train_shadow_model.py",
        "scripts/ml_predict_shadow.py",
        "scripts/ml_label_outcomes.py",
        "scripts/ml_evaluate_shadow.py",
    ]
    for command in required_commands:
        assert command in text

    assert "--dry-run" in text
    assert "--enable-shadow" in text
    assert "shadow_evaluation_latest.json" in text
    assert "unset PYTHONHOME UV_INTERNAL__PYTHONHOME" in text


def test_stage1_ml_runbook_keeps_stage1_shadow_only_invariants_visible():
    text = RUNBOOK.read_text(encoding="utf-8")

    required_invariants = [
        "trade_taken = false",
        "gate_decision = shadow_only",
        "outcome_status = pending",
        "trade_taken_count` must stay `0",
        "place, modify, size, or route live trades",
    ]
    for invariant in required_invariants:
        assert invariant in text

    forbidden_live_paths = [
        "external_signal_executor.py",
        "execution/engine.py",
        "place_order",
        "order_send",
        "modify live orders",
    ]
    for forbidden in forbidden_live_paths:
        assert forbidden not in text
