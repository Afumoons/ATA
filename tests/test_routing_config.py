import pandas as pd

from autonomous_trading_ai.config import RoutingConfig
from autonomous_trading_ai.execution.signals import (
    RoutingContext,
    _passes_regime_confidence_gate,
    _passes_session_gate,
    _passes_volatility_gate,
)


def _stats(meta: dict):
    return {"strategy_explain": {"meta": meta}}


DEFAULT_CONTEXT = RoutingContext(
    regime_label="high_vol",
    candidate_regime_labels=["high_vol", "trending_down"],
    regime_class="volatility_spike",
    regime_type="event_driven",
    regime_confidence=0.40,
    vol_regime="high_vol",
    session="london",
    trend_strength=-1.0,
)


def test_session_gate_requires_best_session_by_default_when_enabled():
    stats = _stats(
        {
            "best_session": "asia",
            "allowed_sessions": ["asia", "london"],
            "blocked_sessions": [],
        }
    )

    ok, reason = _passes_session_gate(
        stats,
        current_session="london",
        routing_cfg=RoutingConfig(require_best_session_for_entry=True),
    )

    assert ok is False
    assert reason == "session_not_best:london:best=asia"


def test_session_gate_can_relax_best_session_requirement():
    stats = _stats(
        {
            "best_session": "asia",
            "allowed_sessions": ["asia", "london"],
            "blocked_sessions": [],
        }
    )

    ok, reason = _passes_session_gate(
        stats,
        current_session="london",
        routing_cfg=RoutingConfig(require_best_session_for_entry=False),
    )

    assert ok is True
    assert reason == "ok"


def test_session_gate_can_disable_allowed_sessions_check():
    stats = _stats(
        {
            "best_session": "asia",
            "allowed_sessions": ["asia"],
            "blocked_sessions": [],
        }
    )

    ok, reason = _passes_session_gate(
        stats,
        current_session="london",
        routing_cfg=RoutingConfig(
            require_best_session_for_entry=False,
            enforce_allowed_sessions=False,
        ),
    )

    assert ok is True
    assert reason == "ok"


def test_regime_confidence_gate_uses_configurable_thresholds():
    ok, reason = _passes_regime_confidence_gate(
        DEFAULT_CONTEXT,
        tier="active",
        routing_cfg=RoutingConfig(min_regime_confidence_active=0.35),
    )

    assert ok is True
    assert reason == "ok"


def test_volatility_gate_can_be_disabled():
    stats = _stats(
        {
            "allowed_regimes": ["ranging"],
            "blocked_regimes": ["high_vol"],
            "best_regime": "ranging",
        }
    )

    blocked, reason = _passes_volatility_gate(
        stats,
        DEFAULT_CONTEXT,
        routing_cfg=RoutingConfig(enforce_volatility_mismatch_gate=True),
    )
    assert blocked is False
    assert reason.startswith("volatility_mismatch")

    ok, reason = _passes_volatility_gate(
        stats,
        DEFAULT_CONTEXT,
        routing_cfg=RoutingConfig(enforce_volatility_mismatch_gate=False),
    )
    assert ok is True
    assert reason == "ok"
