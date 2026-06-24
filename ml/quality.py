"""Phase 2 ML quality decisions for shadow-only audits.

This module turns validation metrics and shadow outcome metrics into a
next-action recommendation without touching live execution or broker logic.
"""

from __future__ import annotations

from typing import Any

from autonomous_trading_ai.config import MLConfig, ml_config


def _truthy_reason(condition: bool, reason: str, reasons: list[str]) -> None:
    if condition:
        reasons.append(reason)


def assess_model_action(
    validation_metrics: dict[str, Any],
    shadow_metrics: dict[str, Any],
    config: MLConfig | None = None,
) -> dict[str, Any]:
    """Return a conservative next-action recommendation for a shadow model.

    The recommendation is intentionally simple and explainable:
    - ``keep_shadow_only`` when validation and shadow quality both clear the bar
    - ``retrain`` when the model is directionally usable but calibration or
      validation quality still needs work
    - ``revise_labels_features`` when the model is severely underperforming
    """
    cfg = config or ml_config
    reasons: list[str] = []

    accuracy = float(validation_metrics.get("accuracy", 0.0) or 0.0)
    macro_f1 = float(validation_metrics.get("macro_f1", 0.0) or 0.0)
    profit_factor = float(validation_metrics.get("profit_factor_proxy", 0.0) or 0.0)
    expectancy_atr = float(validation_metrics.get("expectancy_atr", 0.0) or 0.0)

    shadow_directional_accuracy = float(shadow_metrics.get("directional_accuracy", 0.0) or 0.0)
    calibration = shadow_metrics.get("confidence_calibration") if isinstance(shadow_metrics, dict) else None
    confidence_gap = float(
        (calibration or {}).get("confidence_gap", shadow_metrics.get("confidence_gap", 0.0)) or 0.0
    )
    brier_score = float((calibration or {}).get("brier_score", shadow_metrics.get("brier_score", 0.0)) or 0.0)

    _truthy_reason(accuracy < cfg.min_validation_accuracy, "validation_accuracy_below_threshold", reasons)
    _truthy_reason(macro_f1 < cfg.min_validation_macro_f1, "validation_macro_f1_below_threshold", reasons)
    _truthy_reason(profit_factor < cfg.min_validation_profit_factor_proxy, "validation_profit_factor_proxy_below_threshold", reasons)
    _truthy_reason(expectancy_atr < cfg.min_validation_expectancy_atr, "validation_expectancy_atr_below_threshold", reasons)
    _truthy_reason(shadow_directional_accuracy < cfg.decay_min_directional_accuracy, "shadow_directional_accuracy_too_low", reasons)
    _truthy_reason(confidence_gap > 0.12, "confidence_gap_too_wide", reasons)
    _truthy_reason(brier_score > cfg.decay_max_brier_score, "confidence_brier_score_too_high", reasons)

    severe = any(
        [
            accuracy < cfg.min_validation_accuracy * 0.9,
            macro_f1 < cfg.min_validation_macro_f1 * 0.9,
            profit_factor < max(0.8, cfg.min_validation_profit_factor_proxy * 0.8),
            expectancy_atr < -0.1,
            shadow_directional_accuracy < 0.25,
            confidence_gap > 0.30,
            brier_score > cfg.decay_max_brier_score * 1.5,
        ]
    )

    moderate_shortfall = any(
        [
            accuracy < cfg.min_validation_accuracy,
            macro_f1 < cfg.min_validation_macro_f1,
            profit_factor < cfg.min_validation_profit_factor_proxy,
            expectancy_atr < cfg.min_validation_expectancy_atr,
            shadow_directional_accuracy < cfg.decay_min_directional_accuracy,
            confidence_gap > 0.12,
            brier_score > cfg.decay_max_brier_score,
        ]
    )

    if severe:
        next_action = "revise_labels_features"
    elif moderate_shortfall:
        next_action = "retrain"
    else:
        next_action = "keep_shadow_only"

    promotion_ready = next_action == "keep_shadow_only" and not reasons and shadow_directional_accuracy >= 0.5 and confidence_gap <= 0.08 and brier_score <= 0.12

    return {
        "next_action": next_action,
        "promotion_ready": promotion_ready,
        "reasons": reasons,
        "metrics": {
            "validation": {
                "accuracy": accuracy,
                "macro_f1": macro_f1,
                "profit_factor_proxy": profit_factor,
                "expectancy_atr": expectancy_atr,
            },
            "shadow": {
                "directional_accuracy": shadow_directional_accuracy,
                "confidence_gap": confidence_gap,
                "brier_score": brier_score,
            },
        },
        "thresholds": {
            "min_validation_accuracy": cfg.min_validation_accuracy,
            "min_validation_macro_f1": cfg.min_validation_macro_f1,
            "min_validation_profit_factor_proxy": cfg.min_validation_profit_factor_proxy,
            "min_validation_expectancy_atr": cfg.min_validation_expectancy_atr,
            "decay_min_directional_accuracy": cfg.decay_min_directional_accuracy,
            "decay_max_brier_score": cfg.decay_max_brier_score,
        },
    }
