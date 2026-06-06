"""Stage 1 scheduler helpers for adaptive ML shadow cycles.

These helpers are intentionally audit-only. They run shadow prediction, outcome
labeling, and aggregate evaluation jobs without importing broker execution
paths, changing strategy routing, sizing positions, or promoting models.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from autonomous_trading_ai.config import MLConfig, ml_config
from autonomous_trading_ai.logging_utils import get_logger
from autonomous_trading_ai.ml.dataset import load_feature_frame
from autonomous_trading_ai.ml.evaluate import build_shadow_evaluation_report
from autonomous_trading_ai.ml.journal import DEFAULT_PREDICTION_JOURNAL
from autonomous_trading_ai.ml.outcome import DEFAULT_OUTCOME_JOURNAL, label_pending_predictions
from autonomous_trading_ai.ml.predict import ShadowPredictionResult, run_shadow_prediction

logger = get_logger(__name__)

DEFAULT_SHADOW_EVALUATION_REPORT = Path(__file__).resolve().parent / "reports" / "shadow_evaluation_latest.json"


@dataclass
class MLShadowSchedulerSummary:
    """Small serializable summary returned by Stage 1 shadow scheduler jobs."""

    status: str
    stage: str
    attempted: int = 0
    written: int = 0
    skipped: int = 0
    reasons: list[str] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "stage": self.stage,
            "attempted": self.attempted,
            "written": self.written,
            "skipped": self.skipped,
            "reasons": list(self.reasons),
            "details": dict(self.details),
        }


def _shadow_job_disabled_summary(config: MLConfig) -> MLShadowSchedulerSummary | None:
    if config.stage != "shadow":
        return MLShadowSchedulerSummary(status="skipped", stage=config.stage, skipped=1, reasons=["stage_not_shadow"])
    if not config.enabled:
        return MLShadowSchedulerSummary(status="skipped", stage=config.stage, skipped=1, reasons=["ml_disabled"])
    return None


def run_shadow_prediction_cycle(
    config: MLConfig | None = None,
    *,
    symbols: list[str] | None = None,
    base_dir: Path | None = None,
    registry_path: Path | None = None,
    prediction_journal_path: Path | None = None,
) -> MLShadowSchedulerSummary:
    """Run Stage 1 shadow predictions for configured symbols.

    This function only appends prediction-journal records through
    ``run_shadow_prediction``. That lower-level path forces ``trade_taken=false``
    and ``gate_decision='shadow_only'`` for Stage 1 records.
    """
    cfg = config or ml_config
    disabled = _shadow_job_disabled_summary(cfg)
    if disabled is not None:
        logger.info("ML shadow prediction cycle skipped: %s", disabled.reasons)
        return disabled

    results: dict[str, dict[str, Any]] = {}
    summary = MLShadowSchedulerSummary(status="ok", stage=cfg.stage)
    for symbol in symbols or cfg.managed_symbols:
        result: ShadowPredictionResult = run_shadow_prediction(
            symbol=symbol,
            timeframe=cfg.timeframe,
            config=cfg,
            base_dir=base_dir,
            registry_path=registry_path,
            prediction_journal_path=prediction_journal_path,
        )
        result_dict = {
            "attempted": result.attempted,
            "written": result.written,
            "skipped": result.skipped,
            "reasons": list(result.reasons),
        }
        results[symbol] = result_dict
        summary.attempted += result.attempted
        summary.written += result.written
        summary.skipped += result.skipped
        summary.reasons.extend(f"{symbol}:{reason}" for reason in result.reasons)

    summary.details["symbols"] = results
    logger.info("ML shadow prediction cycle summary: %s", summary.to_dict())
    return summary


def run_shadow_outcome_label_cycle(
    config: MLConfig | None = None,
    *,
    symbols: list[str] | None = None,
    base_dir: Path | None = None,
    prediction_journal_path: Path | None = None,
    outcome_journal_path: Path | None = None,
) -> MLShadowSchedulerSummary:
    """Resolve eligible pending shadow predictions into outcome labels."""
    cfg = config or ml_config
    disabled = _shadow_job_disabled_summary(cfg)
    if disabled is not None:
        logger.info("ML shadow outcome label cycle skipped: %s", disabled.reasons)
        return disabled

    frames = {}
    skipped_symbols: dict[str, str] = {}
    for symbol in symbols or cfg.managed_symbols:
        try:
            frames[(symbol, cfg.timeframe)] = load_feature_frame(symbol, cfg.timeframe, base_dir=base_dir)
        except Exception as exc:  # fail closed: one missing feature file must not crash scheduler
            skipped_symbols[symbol] = f"{type(exc).__name__}:{exc}"
            logger.warning("ML shadow outcome label skip %s %s: %s", symbol, cfg.timeframe, exc)

    written = label_pending_predictions(
        prediction_journal_path=Path(prediction_journal_path) if prediction_journal_path is not None else DEFAULT_PREDICTION_JOURNAL,
        outcome_journal_path=Path(outcome_journal_path) if outcome_journal_path is not None else DEFAULT_OUTCOME_JOURNAL,
        feature_frames=frames,
        horizon_bars=cfg.primary_horizon_bars,
        neutral_threshold_atr=cfg.neutral_return_threshold_atr,
    )
    summary = MLShadowSchedulerSummary(
        status="ok",
        stage=cfg.stage,
        attempted=len(frames),
        written=written,
        skipped=len(skipped_symbols),
        reasons=[f"{symbol}:{reason}" for symbol, reason in skipped_symbols.items()],
        details={"loaded_frames": len(frames), "skipped_symbols": skipped_symbols},
    )
    logger.info("ML shadow outcome label cycle summary: %s", summary.to_dict())
    return summary


def run_shadow_evaluation_cycle(
    config: MLConfig | None = None,
    *,
    prediction_journal_path: Path | None = None,
    outcome_journal_path: Path | None = None,
    output_path: Path | None = None,
) -> MLShadowSchedulerSummary:
    """Write an aggregate Stage 1 shadow evaluation report."""
    cfg = config or ml_config
    disabled = _shadow_job_disabled_summary(cfg)
    if disabled is not None:
        logger.info("ML shadow evaluation cycle skipped: %s", disabled.reasons)
        return disabled

    report = build_shadow_evaluation_report(
        Path(prediction_journal_path) if prediction_journal_path is not None else DEFAULT_PREDICTION_JOURNAL,
        Path(outcome_journal_path) if outcome_journal_path is not None else DEFAULT_OUTCOME_JOURNAL,
    )
    path = Path(output_path) if output_path is not None else DEFAULT_SHADOW_EVALUATION_REPORT
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    warnings = list(report.get("safety_warnings") or [])
    if report.get("trade_taken_count"):
        logger.error("ML shadow evaluation found trade_taken records: %s", report.get("trade_taken_count"))

    summary = MLShadowSchedulerSummary(
        status="warning" if warnings else "ok",
        stage=cfg.stage,
        attempted=int(report.get("overall", {}).get("predictions", 0) or 0),
        written=1,
        skipped=0,
        reasons=warnings,
        details={"output_path": str(path), "trade_taken_count": report.get("trade_taken_count", 0)},
    )
    logger.info("ML shadow evaluation cycle summary: %s", summary.to_dict())
    return summary


def register_ml_shadow_jobs(scheduler: Any, config: MLConfig | None = None) -> bool:
    """Register Stage 1 shadow ML jobs on an APScheduler-like object.

    Returns True only when jobs are registered. Defaults are fail-closed: if ML is
    disabled or the stage is not exactly ``shadow``, no scheduler jobs are added.
    """
    cfg = config or ml_config
    if cfg.stage != "shadow":
        logger.info("ML shadow scheduler jobs not registered: stage=%s", cfg.stage)
        return False
    if not cfg.enabled:
        logger.info("ML shadow scheduler jobs not registered: ml_disabled")
        return False

    first_run = datetime.now(timezone.utc)
    label_first_run = first_run + timedelta(seconds=2)
    evaluate_first_run = first_run + timedelta(seconds=4)

    scheduler.add_job(
        job_ml_shadow_predict,
        "interval",
        minutes=cfg.shadow_predict_interval_minutes,
        id="ml_shadow_predict",
        next_run_time=first_run,
    )
    scheduler.add_job(
        job_ml_shadow_label_outcomes,
        "interval",
        minutes=cfg.outcome_label_interval_minutes,
        id="ml_shadow_label_outcomes",
        next_run_time=label_first_run,
    )
    scheduler.add_job(
        job_ml_shadow_evaluate,
        "interval",
        minutes=cfg.governance_interval_minutes,
        id="ml_shadow_evaluate",
        next_run_time=evaluate_first_run,
    )
    return True


def job_ml_shadow_predict() -> None:
    run_shadow_prediction_cycle()


def job_ml_shadow_label_outcomes() -> None:
    run_shadow_outcome_label_cycle()


def job_ml_shadow_evaluate() -> None:
    run_shadow_evaluation_cycle()
