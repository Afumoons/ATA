"""Aggregate Stage 1 shadow ML prediction and outcome journals."""

from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from autonomous_trading_ai.ml.journal import read_jsonl


_CONFIDENCE_BIN_EDGES = (0.0, 0.2, 0.4, 0.6, 0.8, 1.0)


def _new_bucket() -> dict[str, Any]:
    return {
        "predictions": 0,
        "resolved_outcomes": 0,
        "pending_outcomes": 0,
        "correct_direction": 0,
        "directional_accuracy": None,
        "average_quality_score": None,
        "average_confidence": None,
        "confidence_brier_score": None,
        "confidence_calibration": [],
        "confusion_matrix": {},
        "class_metrics": {},
        "_quality_scores": [],
        "_confidence_scores": [],
        "_correct_flags": [],
        "_confusion_counts": defaultdict(Counter),
    }


def _finalize_confusion(confusion_counts: defaultdict[str, Counter]) -> tuple[dict[str, dict[str, int]], dict[str, dict[str, Any]]]:
    labels = sorted(set(confusion_counts.keys()) | {pred for row in confusion_counts.values() for pred in row})
    confusion_matrix: dict[str, dict[str, int]] = {
        actual: {predicted: int(confusion_counts[actual].get(predicted, 0)) for predicted in labels}
        for actual in labels
    }
    class_metrics: dict[str, dict[str, Any]] = {}
    for label in labels:
        tp = int(confusion_counts[label].get(label, 0))
        actual_total = int(sum(confusion_counts[label].values()))
        predicted_total = int(sum(row.get(label, 0) for row in confusion_counts.values()))
        precision = round(tp / predicted_total, 6) if predicted_total else None
        recall = round(tp / actual_total, 6) if actual_total else None
        if precision is None or recall is None or precision + recall == 0:
            f1 = None
        else:
            f1 = round(2 * precision * recall / (precision + recall), 6)
        class_metrics[label] = {
            "tp": tp,
            "actual": actual_total,
            "predicted": predicted_total,
            "precision": precision,
            "recall": recall,
            "f1": f1,
        }
    return confusion_matrix, class_metrics


def _finalize_confidence_bucket(scores: list[float], correct_flags: list[int]) -> dict[str, Any] | None:
    if not scores:
        return None
    count = len(scores)
    correct = sum(correct_flags)
    avg_confidence = round(sum(scores) / count, 6)
    accuracy = round(correct / count, 6)
    brier = round(sum((score - flag) ** 2 for score, flag in zip(scores, correct_flags, strict=False)) / count, 6)
    bins: list[dict[str, Any]] = []
    for index, lower in enumerate(_CONFIDENCE_BIN_EDGES[:-1]):
        upper = _CONFIDENCE_BIN_EDGES[index + 1]
        if index == len(_CONFIDENCE_BIN_EDGES) - 2:
            members = [i for i, score in enumerate(scores) if lower <= score <= upper]
        else:
            members = [i for i, score in enumerate(scores) if lower <= score < upper]
        if not members:
            bins.append(
                {
                    "range": [lower, upper],
                    "count": 0,
                    "accuracy": None,
                    "average_confidence": None,
                    "calibration_gap": None,
                }
            )
            continue
        bin_scores = [scores[i] for i in members]
        bin_correct = [correct_flags[i] for i in members]
        bin_avg_confidence = sum(bin_scores) / len(bin_scores)
        bin_accuracy = sum(bin_correct) / len(bin_correct)
        bins.append(
            {
                "range": [lower, upper],
                "count": len(members),
                "accuracy": round(bin_accuracy, 6),
                "average_confidence": round(bin_avg_confidence, 6),
                "calibration_gap": round(bin_avg_confidence - bin_accuracy, 6),
            }
        )
    return {
        "count": count,
        "average_confidence": avg_confidence,
        "accuracy": accuracy,
        "brier_score": brier,
        "confidence_gap": round(avg_confidence - accuracy, 6),
        "bins": bins,
    }


def _finalize_bucket(bucket: dict[str, Any]) -> dict[str, Any]:
    quality_scores = bucket.pop("_quality_scores", [])
    confidence_scores = bucket.pop("_confidence_scores", [])
    correct_flags = bucket.pop("_correct_flags", [])
    confusion_counts = bucket.pop("_confusion_counts", defaultdict(Counter))
    resolved = bucket["resolved_outcomes"]
    bucket["pending_outcomes"] = max(bucket["predictions"] - resolved, 0)
    bucket["directional_accuracy"] = round(bucket["correct_direction"] / resolved, 6) if resolved else None
    bucket["average_quality_score"] = round(sum(quality_scores) / len(quality_scores), 6) if quality_scores else None
    bucket["average_confidence"] = round(sum(confidence_scores) / len(confidence_scores), 6) if confidence_scores else None
    if confidence_scores:
        bucket["confidence_brier_score"] = round(
            sum((score - flag) ** 2 for score, flag in zip(confidence_scores, correct_flags, strict=False)) / len(confidence_scores),
            6,
        )
    else:
        bucket["confidence_brier_score"] = None
    confusion_matrix, class_metrics = _finalize_confusion(confusion_counts)
    bucket["confusion_matrix"] = confusion_matrix
    bucket["class_metrics"] = class_metrics
    confidence_calibration = _finalize_confidence_bucket(confidence_scores, correct_flags)
    bucket["confidence_calibration"] = confidence_calibration or []
    return bucket


def _add_prediction(bucket: dict[str, Any]) -> None:
    bucket["predictions"] += 1


def _add_outcome(bucket: dict[str, Any], prediction: dict[str, Any], outcome: dict[str, Any]) -> None:
    bucket["resolved_outcomes"] += 1
    if outcome.get("correct_direction") is True:
        bucket["correct_direction"] += 1
    if outcome.get("quality_score") is not None:
        bucket.setdefault("_quality_scores", []).append(float(outcome["quality_score"]))
    confidence = outcome.get("confidence", prediction.get("confidence"))
    if confidence is not None:
        bucket.setdefault("_confidence_scores", []).append(float(confidence))
        correct_flag = 1 if outcome.get("correct_direction") is True else 0 if outcome.get("correct_direction") is False else int(
            str(outcome.get("predicted_action") or prediction.get("predicted_action") or "")
            == str(outcome.get("actual_direction") or "")
        )
        bucket.setdefault("_correct_flags", []).append(correct_flag)
    predicted_action = str(outcome.get("predicted_action") or prediction.get("predicted_action") or "unknown")
    actual_direction = str(outcome.get("actual_direction") or "unknown")
    bucket.setdefault("_confusion_counts", defaultdict(Counter))[actual_direction][predicted_action] += 1


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
            _add_outcome(bucket, prediction, outcome)

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
