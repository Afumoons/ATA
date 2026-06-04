"""Append-only JSONL journals for Stage 1 ML shadow predictions."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


DEFAULT_PREDICTION_JOURNAL = Path(__file__).resolve().parent / "prediction_journal.jsonl"


@dataclass
class MLPredictionRecord:
    prediction_id: str
    created_at: str
    bar_time: str
    symbol: str
    timeframe: str
    model_id: str
    model_status: str
    stage: str
    predicted_action: str
    confidence: float
    class_probabilities: dict[str, float]
    expected_return_atr: float | None
    regime: str | None
    session: str | None
    feature_snapshot_hash: str
    feature_schema_version: str
    reason: str

    def to_journal_record(self) -> dict[str, Any]:
        record = asdict(self)
        if self.stage == "shadow":
            record.update(
                {
                    "trade_taken": False,
                    "gate_decision": "shadow_only",
                    "gate_reasons": ["stage_shadow_no_execution"],
                    "outcome_status": "pending",
                }
            )
        else:
            record.setdefault("trade_taken", False)
            record.setdefault("gate_decision", "fail_closed")
            record.setdefault("gate_reasons", ["stage_not_enabled_for_execution"])
            record.setdefault("outcome_status", "pending")
        return record


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not Path(path).exists():
        return []
    records: list[dict[str, Any]] = []
    with Path(path).open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def _dedupe_key(record: dict[str, Any]) -> tuple[Any, ...]:
    return (
        record.get("symbol"),
        record.get("timeframe"),
        record.get("model_id"),
        record.get("bar_time"),
        record.get("stage"),
    )


def append_prediction(record: MLPredictionRecord, path: Path | None = None, force: bool = False) -> bool:
    journal_path = Path(path) if path is not None else DEFAULT_PREDICTION_JOURNAL
    journal_path.parent.mkdir(parents=True, exist_ok=True)
    payload = record.to_journal_record()
    if not force:
        key = _dedupe_key(payload)
        for existing in read_jsonl(journal_path):
            if _dedupe_key(existing) == key:
                return False

    line = json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n"
    with journal_path.open("a", encoding="utf-8") as handle:
        handle.write(line)
        handle.flush()
        os.fsync(handle.fileno())
    return True


def append_jsonl(record: dict[str, Any], path: Path) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with Path(path).open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
