"""Atomic JSON registry for ML model metadata."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


DEFAULT_REGISTRY_PATH = Path(__file__).resolve().parent / "registry.json"


@dataclass
class ModelGroup:
    champion_model_id: str | None = None
    challenger_model_ids: list[str] = field(default_factory=list)
    shadow_model_ids: list[str] = field(default_factory=list)
    disabled_model_ids: list[str] = field(default_factory=list)


@dataclass
class ModelMetadata:
    model_id: str
    symbol: str
    timeframe: str
    artifact_path: str
    feature_schema_path: str
    validation_report_path: str
    status: str
    stage_allowed: str
    created_at: str
    metrics: dict[str, Any] = field(default_factory=dict)


@dataclass
class MLRegistry:
    version: int = 1
    models: dict[str, ModelGroup] = field(default_factory=dict)
    model_metadata: dict[str, ModelMetadata] = field(default_factory=dict)


def _group_key(symbol: str, timeframe: str) -> str:
    return f"{symbol}:{timeframe}"


def _registry_path(path: Path | None = None) -> Path:
    return Path(path) if path is not None else DEFAULT_REGISTRY_PATH


def load_registry(path: Path | None = None) -> MLRegistry:
    registry_path = _registry_path(path)
    if not registry_path.exists():
        return MLRegistry()
    raw = json.loads(registry_path.read_text(encoding="utf-8"))
    return MLRegistry(
        version=int(raw.get("version", 1)),
        models={key: ModelGroup(**value) for key, value in raw.get("models", {}).items()},
        model_metadata={key: ModelMetadata(**value) for key, value in raw.get("model_metadata", {}).items()},
    )


def save_registry(registry: MLRegistry, path: Path | None = None) -> None:
    registry_path = _registry_path(path)
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": registry.version,
        "models": {key: asdict(value) for key, value in registry.models.items()},
        "model_metadata": {key: asdict(value) for key, value in registry.model_metadata.items()},
    }
    tmp_path = registry_path.with_suffix(registry_path.suffix + ".tmp")
    tmp_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    os.replace(tmp_path, registry_path)


def register_model(metadata: ModelMetadata, registry_path: Path | None = None) -> MLRegistry:
    registry = load_registry(registry_path)
    key = _group_key(metadata.symbol, metadata.timeframe)
    group = registry.models.setdefault(key, ModelGroup())
    registry.model_metadata[metadata.model_id] = metadata

    for bucket in (group.challenger_model_ids, group.shadow_model_ids, group.disabled_model_ids):
        if metadata.model_id in bucket:
            bucket.remove(metadata.model_id)

    if metadata.status == "champion":
        if group.champion_model_id and group.champion_model_id != metadata.model_id:
            group.disabled_model_ids.append(group.champion_model_id)
        group.champion_model_id = metadata.model_id
    elif metadata.status == "shadow":
        group.shadow_model_ids.append(metadata.model_id)
    elif metadata.status == "disabled":
        group.disabled_model_ids.append(metadata.model_id)
    else:
        group.challenger_model_ids.append(metadata.model_id)

    save_registry(registry, registry_path)
    return registry


def get_champion(symbol: str, timeframe: str, registry_path: Path | None = None) -> ModelMetadata | None:
    registry = load_registry(registry_path)
    group = registry.models.get(_group_key(symbol, timeframe))
    if not group or not group.champion_model_id:
        return None
    return registry.model_metadata.get(group.champion_model_id)


def get_shadow_models(symbol: str, timeframe: str, registry_path: Path | None = None) -> list[ModelMetadata]:
    registry = load_registry(registry_path)
    group = registry.models.get(_group_key(symbol, timeframe))
    if not group:
        return []
    return [registry.model_metadata[mid] for mid in group.shadow_model_ids if mid in registry.model_metadata]
