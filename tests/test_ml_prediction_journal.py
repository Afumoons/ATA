from autonomous_trading_ai.ml.journal import MLPredictionRecord, append_prediction, read_jsonl


def _record(confidence=0.64):
    return MLPredictionRecord(
        prediction_id="p1",
        created_at="2026-01-01T00:00:00+00:00",
        bar_time="2026-01-01T00:00:00+00:00",
        symbol="XAUUSDm",
        timeframe="M15",
        model_id="xau_m15_v1",
        model_status="shadow",
        stage="shadow",
        predicted_action="buy",
        confidence=confidence,
        class_probabilities={"buy": confidence, "sell": 0.2, "hold": 1 - confidence - 0.2},
        expected_return_atr=0.18,
        regime="trend_up",
        session="london",
        feature_snapshot_hash="abc123",
        feature_schema_version="v1",
        reason="ok",
    )


def test_append_prediction_writes_shadow_only_pending_record(tmp_path):
    path = tmp_path / "prediction_journal.jsonl"

    written = append_prediction(_record(), path)
    records = read_jsonl(path)

    assert written is True
    assert len(records) == 1
    assert records[0]["trade_taken"] is False
    assert records[0]["gate_decision"] == "shadow_only"
    assert records[0]["gate_reasons"] == ["stage_shadow_no_execution"]
    assert records[0]["outcome_status"] == "pending"


def test_append_prediction_skips_duplicate_unless_forced(tmp_path):
    path = tmp_path / "prediction_journal.jsonl"

    assert append_prediction(_record(), path) is True
    assert append_prediction(_record(), path) is False
    assert append_prediction(_record(confidence=0.7), path, force=True) is True

    assert len(read_jsonl(path)) == 2
