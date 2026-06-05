"""Aggregate Stage 1 shadow ML prediction and outcome journals."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any

from autonomous_trading_ai.ml.journal import read_jsonl


def _new_bucket() -> dict[str, Any]:
    return {
        "predictions": 0,
        "resolved_outcomes": 0,
        "pending_outcomes": 0,
        "correct_direction": 0,
        "directional_accuracy": None,
        "average_quality_score": None,
    }


def _finalize_bucket(bucket: dict[str, Any]) -> dict[str, Any]:
    quality_scores = bucket.pop("_quality_scores", [])
    resolved = bucket["resolved_outcomes"]
    bucket["pending_outcomes"] = max(bucket["predictions"] - resolved, 0)
    bucket["directional_accuracy"] = round(bucket["correct_direction"] / resolved, 6) if resolved else None
    bucket["average_quality_score"] = round(sum(quality_scores) / len(quality_scores), 6) if quality_scores else None
    return bucket


def _add_prediction(bucket: dict[str, Any]) -> None:
    bucket["predictions"] += 1


def _add_outcome(bucket: dict[str, Any], outcome: dict[str, Any]) -> None:
    bucket["resolved_outcomes"] += 1
    if outcome.get("correct_direction") is True:
        bucket["correct_direction"] += 1
    if outcome.get("quality_score") is not None:
        bucket.setdefault("_quality_scores", []).append(float(outcome["quality_score"]))


def build_shadow_evaluation_report(prediction_journal_path: Path, outcome_journal_path: Path | None = None) -> dict[str, Any]:
    """Build an aggregate report from shadow prediction and outcome journals.

    The report is audit-only. It never writes to execution state and never
    promotes, sizes, places, or modifies trades.
    """
    predictions = read_jsonl(Path(prediction_journal_path))
    outcomes = read_jsonl(Path(outcome_journal_path)) if outcome_journal_path is not None else []
    outcomes_by_prediction_id = {outcome.get("prediction_id"): outcome for outcome in outcomes}

    overall = _new_bucket()
    by_model = defaultdict(_new_bucket)
    by_symbol_timeframe = defaultdict(_new_bucket)
    trade_taken_count = 0

    for prediction in predictions:
        model_id = str(prediction.get("model_id") or "unknown")
        symbol = str(prediction.get("symbol") or "unknown")
        timeframe = str(prediction.get("timeframe") or "unknown")
        symbol_timeframe = f"{symbol}:{timeframe}"
        prediction_id = prediction.get("prediction_id")

        if prediction.get("trade_taken") is True:
            trade_taken_count += 1

        for bucket in (overall, by_model[model_id], by_symbol_timeframe[symbol_timeframe]):
            _add_prediction(bucket)

        outcome = outcomes_by_prediction_id.get(prediction_id)
        if outcome is None:
            continue
        for bucket in (overall, by_model[model_id], by_symbol_timeframe[symbol_timeframe]):
            _add_outcome(bucket, outcome)

    safety_warnings = []
    if trade_taken_count:
        safety_warnings.append("prediction_journal_contains_trade_taken_records")

    return {
        "stage": "shadow",
        "trade_taken_count": trade_taken_count,
        "safety_warnings": safety_warnings,
        "overall": _finalize_bucket(overall),
        "by_model": {key: _finalize_bucket(value) for key, value in sorted(by_model.items())},
        "by_symbol_timeframe": {key: _finalize_bucket(value) for key, value in sorted(by_symbol_timeframe.items())},
    }
