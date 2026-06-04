from autonomous_trading_ai.ml.registry import (
    ModelMetadata,
    load_registry,
    register_model,
    save_registry,
)


def test_missing_registry_returns_empty_structure(tmp_path):
    registry = load_registry(tmp_path / "registry.json")

    assert registry.version == 1
    assert registry.models == {}
    assert registry.model_metadata == {}


def test_register_model_persists_challenger(tmp_path):
    path = tmp_path / "registry.json"
    metadata = ModelMetadata(
        model_id="xau_m15_v1",
        symbol="XAUUSDm",
        timeframe="M15",
        artifact_path="ml/artifacts/XAUUSDm/M15/v1/model.joblib",
        feature_schema_path="ml/artifacts/XAUUSDm/M15/v1/feature_schema.json",
        validation_report_path="ml/artifacts/XAUUSDm/M15/v1/validation_report.json",
        status="challenger",
        stage_allowed="shadow",
        created_at="2026-01-01T00:00:00+00:00",
        metrics={"accuracy": 0.5},
    )

    registry = register_model(metadata, registry_path=path)
    loaded = load_registry(path)

    assert registry.models["XAUUSDm:M15"].challenger_model_ids == ["xau_m15_v1"]
    assert loaded.model_metadata["xau_m15_v1"].metrics["accuracy"] == 0.5


def test_save_load_registry_roundtrip(tmp_path):
    registry = load_registry(tmp_path / "missing.json")
    save_registry(registry, tmp_path / "registry.json")

    loaded = load_registry(tmp_path / "registry.json")

    assert loaded.version == 1
