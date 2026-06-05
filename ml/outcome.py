"""Resolve shadow prediction outcomes from later market bars."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from autonomous_trading_ai.ml.journal import append_jsonl, read_jsonl


DEFAULT_OUTCOME_JOURNAL = Path(__file__).resolve().parent / "outcome_journal.jsonl"


def _parse_time(value: object) -> pd.Timestamp:
    return pd.Timestamp(value).tz_convert("UTC") if pd.Timestamp(value).tzinfo else pd.Timestamp(value).tz_localize("UTC")


def _direction(return_atr: float, threshold: float = 0.10) -> str:
    if return_atr > threshold:
        return "buy"
    if return_atr < -threshold:
        return "sell"
    return "hold"


def label_pending_predictions(
    prediction_journal_path: Path,
    outcome_journal_path: Path | None = None,
    feature_frames: dict[tuple[str, str], pd.DataFrame] | None = None,
    horizon_bars: int = 8,
    neutral_threshold_atr: float = 0.10,
) -> int:
    """Append outcomes for pending predictions when future bars are available.

    ``feature_frames`` is injectable for tests and scripts; keys are
    ``(symbol, timeframe)``. Existing outcomes are not duplicated.
    """
    if feature_frames is None:
        feature_frames = {}
    outcome_path = Path(outcome_journal_path) if outcome_journal_path is not None else DEFAULT_OUTCOME_JOURNAL
    existing_outcomes = {record.get("prediction_id") for record in read_jsonl(outcome_path)}
    written = 0

    for prediction in read_jsonl(Path(prediction_journal_path)):
        if prediction.get("outcome_status") != "pending":
            continue
        prediction_id = prediction.get("prediction_id")
        if prediction_id in existing_outcomes:
            continue
        symbol = str(prediction.get("symbol"))
        timeframe = str(prediction.get("timeframe"))
        frame = feature_frames.get((symbol, timeframe))
        if frame is None or frame.empty:
            continue

        df = frame.copy()
        df["time"] = pd.to_datetime(df["time"], utc=True)
        bar_time = _parse_time(prediction.get("bar_time"))
        matches = df.index[df["time"] == bar_time].tolist()
        if not matches:
            continue
        idx = matches[0]
        future_idx = idx + horizon_bars
        if future_idx >= len(df):
            continue

        close = float(df.loc[idx, "close"])
        future_close = float(df.loc[future_idx, "close"])
        atr = float(df.loc[idx, "atr"])
        if atr == 0:
            continue
        actual_return_atr = (future_close - close) / atr
        actual_direction = _direction(actual_return_atr, neutral_threshold_atr)
        predicted_action = prediction.get("predicted_action")
        record = {
            "prediction_id": prediction_id,
            "resolved_at": datetime.now(timezone.utc).isoformat(),
            "symbol": symbol,
            "timeframe": timeframe,
            "model_id": prediction.get("model_id"),
            "bar_time": prediction.get("bar_time"),
            "horizon_bars": horizon_bars,
            "predicted_action": predicted_action,
            "confidence": prediction.get("confidence"),
            "actual_direction": actual_direction,
            "actual_return_atr": actual_return_atr,
            "would_tp_before_sl": None,
            "would_sl_before_tp": None,
            "ambiguous_same_bar": False,
            "correct_direction": predicted_action == actual_direction,
            "quality_score": actual_return_atr if predicted_action == "buy" else -actual_return_atr if predicted_action == "sell" else -abs(actual_return_atr),
            "execution_adjusted_pnl": None,
            "source": "market_shadow",
        }
        append_jsonl(record, outcome_path)
        existing_outcomes.add(prediction_id)
        written += 1
    return written
