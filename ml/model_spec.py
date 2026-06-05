"""Serializable Stage 1 ML model artifacts and schemas.

The Stage 1 contract is intentionally conservative: models may emit shadow
BUY/SELL/HOLD predictions, but this module contains no execution hooks.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import joblib
import pandas as pd


FEATURE_SCHEMA_VERSION = "ml-shadow-v1"
VALID_ACTIONS = ("buy", "hold", "sell")


@dataclass
class FeatureSchema:
    version: str
    symbol: str
    timeframe: str
    feature_columns: list[str]
    label_column: str
    created_at: str

    @property
    def schema_hash(self) -> str:
        payload = json.dumps(
            {
                "version": self.version,
                "symbol": self.symbol,
                "timeframe": self.timeframe,
                "feature_columns": self.feature_columns,
                "label_column": self.label_column,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def make_model_id(symbol: str, timeframe: str, created_at: str | None = None) -> str:
    stamp = (created_at or utc_now_iso()).replace(":", "").replace("+", "Z").replace("-", "")
    safe_symbol = symbol.replace("/", "_")
    return f"{safe_symbol}_{timeframe}_shadow_{stamp}"


def save_feature_schema(schema: FeatureSchema, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(schema), indent=2, sort_keys=True), encoding="utf-8")


def load_feature_schema(path: Path) -> FeatureSchema:
    return FeatureSchema(**json.loads(path.read_text(encoding="utf-8")))


@dataclass
class ShadowModelArtifact:
    model_id: str
    symbol: str
    timeframe: str
    estimator: Any
    feature_schema: FeatureSchema
    class_labels: list[str] = field(default_factory=lambda: list(VALID_ACTIONS))
    metrics: dict[str, Any] = field(default_factory=dict)

    def feature_snapshot_hash(self, row: pd.Series) -> str:
        payload = {}
        for column in self.feature_schema.feature_columns:
            value = row.get(column)
            if pd.isna(value):
                payload[column] = None
            elif hasattr(value, "item"):
                payload[column] = value.item()
            else:
                payload[column] = value
        return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode("utf-8")).hexdigest()[:16]


def save_model_artifact(artifact: ShadowModelArtifact, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(artifact, path)


def load_model_artifact(path: Path) -> ShadowModelArtifact:
    artifact = joblib.load(path)
    if not isinstance(artifact, ShadowModelArtifact):
        raise TypeError(f"unexpected model artifact type: {type(artifact)!r}")
    return artifact
