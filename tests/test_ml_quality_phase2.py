from autonomous_trading_ai.config import MLConfig
from autonomous_trading_ai.ml.quality import assess_model_action


def test_assess_model_action_retrains_on_moderate_validation_shortfall():
    cfg = MLConfig()
    result = assess_model_action(
        validation_metrics={
            "accuracy": 0.432,
            "macro_f1": 0.325,
            "profit_factor_proxy": 0.964,
            "expectancy_atr": -0.024,
        },
        shadow_metrics={
            "directional_accuracy": 0.425386,
            "average_quality_score": -0.104026,
            "confidence_calibration": {
                "confidence_gap": 0.181,
                "brier_score": 0.19045,
                "accuracy": 0.425386,
            },
        },
        config=cfg,
    )

    assert result["next_action"] == "retrain"
    assert result["promotion_ready"] is False
    assert "validation_profit_factor_proxy_below_threshold" in result["reasons"]
    assert "confidence_gap_too_wide" in result["reasons"]


def test_assess_model_action_revises_labels_when_shadow_quality_is_severe():
    cfg = MLConfig()
    result = assess_model_action(
        validation_metrics={
            "accuracy": 0.3405,
            "macro_f1": 0.2745,
            "profit_factor_proxy": 0.5487,
            "expectancy_atr": -0.4408,
        },
        shadow_metrics={
            "directional_accuracy": 0.103064,
            "average_quality_score": -1.153094,
            "confidence_calibration": {
                "confidence_gap": 0.595166,
                "brier_score": 0.471696,
                "accuracy": 0.102635,
            },
        },
        config=cfg,
    )

    assert result["next_action"] == "revise_labels_features"
    assert result["promotion_ready"] is False
    assert "shadow_directional_accuracy_too_low" in result["reasons"]
    assert "confidence_gap_too_wide" in result["reasons"]


def test_assess_model_action_keeps_shadow_only_when_metrics_clear_bar():
    cfg = MLConfig()
    result = assess_model_action(
        validation_metrics={
            "accuracy": 0.58,
            "macro_f1": 0.53,
            "profit_factor_proxy": 1.31,
            "expectancy_atr": 0.12,
        },
        shadow_metrics={
            "directional_accuracy": 0.62,
            "average_quality_score": 0.28,
            "confidence_calibration": {
                "confidence_gap": 0.04,
                "brier_score": 0.10,
                "accuracy": 0.62,
            },
        },
        config=cfg,
    )

    assert result["next_action"] == "keep_shadow_only"
    assert result["promotion_ready"] is True
    assert result["reasons"] == []
