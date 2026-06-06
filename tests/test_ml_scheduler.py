from datetime import datetime, timezone
from pathlib import Path

from autonomous_trading_ai.config import MLConfig
from autonomous_trading_ai.ml import scheduler as ml_scheduler
from autonomous_trading_ai.ml.predict import ShadowPredictionResult


class FakeScheduler:
    def __init__(self):
        self.jobs = []

    def add_job(self, func, trigger, **kwargs):
        self.jobs.append({"func": func, "trigger": trigger, **kwargs})


def test_register_ml_shadow_jobs_is_disabled_by_default():
    fake = FakeScheduler()
    cfg = MLConfig(enabled=False, stage="shadow")

    registered = ml_scheduler.register_ml_shadow_jobs(fake, cfg)

    assert registered is False
    assert fake.jobs == []


def test_register_ml_shadow_jobs_requires_shadow_stage():
    fake = FakeScheduler()
    cfg = MLConfig(enabled=True, stage="advisory")

    registered = ml_scheduler.register_ml_shadow_jobs(fake, cfg)

    assert registered is False
    assert fake.jobs == []


def test_register_ml_shadow_jobs_adds_only_shadow_audit_jobs():
    fake = FakeScheduler()
    cfg = MLConfig(
        enabled=True,
        stage="shadow",
        shadow_predict_interval_minutes=7,
        outcome_label_interval_minutes=17,
        governance_interval_minutes=67,
    )

    registered = ml_scheduler.register_ml_shadow_jobs(fake, cfg)

    assert registered is True
    assert [job["id"] for job in fake.jobs] == [
        "ml_shadow_predict",
        "ml_shadow_label_outcomes",
        "ml_shadow_evaluate",
    ]
    assert [job["trigger"] for job in fake.jobs] == ["interval", "interval", "interval"]
    assert [job["minutes"] for job in fake.jobs] == [7, 17, 67]
    next_runs = [job["next_run_time"] for job in fake.jobs]
    assert all(run.tzinfo == timezone.utc for run in next_runs)
    assert all(isinstance(run, datetime) for run in next_runs)
    assert next_runs[0] < next_runs[1] < next_runs[2]
    assert (next_runs[1] - next_runs[0]).total_seconds() == 2
    assert (next_runs[2] - next_runs[1]).total_seconds() == 2
    assert [job["func"] for job in fake.jobs] == [
        ml_scheduler.job_ml_shadow_predict,
        ml_scheduler.job_ml_shadow_label_outcomes,
        ml_scheduler.job_ml_shadow_evaluate,
    ]


def test_shadow_prediction_cycle_aggregates_fail_closed_results(monkeypatch, tmp_path):
    calls = []

    def fake_run_shadow_prediction(**kwargs):
        calls.append(kwargs)
        return ShadowPredictionResult(attempted=1, written=0, skipped=1, reasons=["no_shadow_model"])

    monkeypatch.setattr(ml_scheduler, "run_shadow_prediction", fake_run_shadow_prediction)
    cfg = MLConfig(enabled=True, stage="shadow", managed_symbols=["XAUUSDm", "BTCUSDm"], timeframe="M15")

    summary = ml_scheduler.run_shadow_prediction_cycle(
        cfg,
        registry_path=tmp_path / "registry.json",
        prediction_journal_path=tmp_path / "predictions.jsonl",
    )

    assert summary.status == "ok"
    assert summary.attempted == 2
    assert summary.written == 0
    assert summary.skipped == 2
    assert summary.reasons == ["XAUUSDm:no_shadow_model", "BTCUSDm:no_shadow_model"]
    assert [call["symbol"] for call in calls] == ["XAUUSDm", "BTCUSDm"]
    assert all(call["config"] is cfg for call in calls)


def test_shadow_label_cycle_loads_features_and_writes_only_outcomes(monkeypatch, tmp_path):
    loaded = []
    label_args = {}

    def fake_load_feature_frame(symbol, timeframe, base_dir=None):
        loaded.append((symbol, timeframe, base_dir))
        return f"frame:{symbol}:{timeframe}"

    def fake_label_pending_predictions(**kwargs):
        label_args.update(kwargs)
        return 3

    monkeypatch.setattr(ml_scheduler, "load_feature_frame", fake_load_feature_frame)
    monkeypatch.setattr(ml_scheduler, "label_pending_predictions", fake_label_pending_predictions)
    cfg = MLConfig(enabled=True, stage="shadow", managed_symbols=["XAUUSDm"], timeframe="M15")

    summary = ml_scheduler.run_shadow_outcome_label_cycle(
        cfg,
        base_dir=tmp_path / "features",
        prediction_journal_path=tmp_path / "predictions.jsonl",
        outcome_journal_path=tmp_path / "outcomes.jsonl",
    )

    assert loaded == [("XAUUSDm", "M15", tmp_path / "features")]
    assert label_args["prediction_journal_path"] == tmp_path / "predictions.jsonl"
    assert label_args["outcome_journal_path"] == tmp_path / "outcomes.jsonl"
    assert label_args["feature_frames"] == {("XAUUSDm", "M15"): "frame:XAUUSDm:M15"}
    assert summary.written == 3
    assert summary.skipped == 0


def test_shadow_evaluation_cycle_writes_report_and_surfaces_safety_warning(monkeypatch, tmp_path):
    report = {
        "stage": "shadow",
        "trade_taken_count": 1,
        "safety_warnings": ["prediction_journal_contains_trade_taken_records"],
        "overall": {"predictions": 4},
        "by_model": {},
        "by_symbol_timeframe": {},
    }

    def fake_build_shadow_evaluation_report(prediction_journal_path, outcome_journal_path):
        assert prediction_journal_path == tmp_path / "predictions.jsonl"
        assert outcome_journal_path == tmp_path / "outcomes.jsonl"
        return report

    monkeypatch.setattr(ml_scheduler, "build_shadow_evaluation_report", fake_build_shadow_evaluation_report)
    cfg = MLConfig(enabled=True, stage="shadow")
    output_path = tmp_path / "reports" / "shadow_evaluation_latest.json"

    summary = ml_scheduler.run_shadow_evaluation_cycle(
        cfg,
        prediction_journal_path=tmp_path / "predictions.jsonl",
        outcome_journal_path=tmp_path / "outcomes.jsonl",
        output_path=output_path,
    )

    assert summary.status == "warning"
    assert summary.attempted == 4
    assert summary.written == 1
    assert summary.reasons == ["prediction_journal_contains_trade_taken_records"]
    assert output_path.exists()
    assert '"trade_taken_count": 1' in output_path.read_text(encoding="utf-8")
