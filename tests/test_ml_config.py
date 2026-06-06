from autonomous_trading_ai.config import ml_config, validate_ml_stage


def test_ml_config_stage1_operator_enabled_is_shadow_only():
    assert ml_config.enabled is True
    assert ml_config.stage == "shadow"
    assert ml_config.min_gated_autonomous_confidence > ml_config.min_advisory_confidence
    assert ml_config.min_adaptive_confidence > ml_config.min_gated_autonomous_confidence
    assert ml_config.ml_risk_multiplier <= 0.5
    assert "XAUUSDm" in ml_config.managed_symbols


def test_validate_ml_stage_rejects_unknown_stage():
    assert validate_ml_stage("shadow") == "shadow"
    try:
        validate_ml_stage("unsafe_auto")
    except ValueError as exc:
        assert "unsupported ML stage" in str(exc)
    else:
        raise AssertionError("unknown stage should fail closed")
