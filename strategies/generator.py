from __future__ import annotations

import json
import random
import uuid
from pathlib import Path
from typing import List, Tuple, Dict, Any, Optional
from collections import Counter

from strategies.base import StrategyDefinition
from logging_utils import get_logger

logger = get_logger(__name__)

STRATEGY_DIR = Path(__file__).resolve().parent
GENERATED_DIR = STRATEGY_DIR / "generated"
GENERATED_DIR.mkdir(exist_ok=True)

# ---------------------------------------------------------------------------
# Threshold alignment with regime.py RegimeConfig (ATR-normalised scale).
# ---------------------------------------------------------------------------
_TREND_UP_THRESH = 0.08
_TREND_RANGING_BOUND = 0.08
_STRONG_TREND_THRESH = 0.30

_TREND_MIN_LOW = 0.05
_TREND_MIN_HIGH = 0.50

_TREND_EXIT_LOW = -0.15
_TREND_EXIT_HIGH = 0.10
_TREND_EXIT_CLAMP_MIN = -0.20
_TREND_EXIT_CLAMP_MAX = 0.15

# ---------------------------------------------------------------------------
# Entry / exit templates
# ---------------------------------------------------------------------------
_RSI_RANGE_LONG = (
    f"rsi < 35 and trend_strength > -{_TREND_RANGING_BOUND}"
    f" and trend_strength < {_TREND_RANGING_BOUND}"
)
_RSI_RANGE_SHORT = (
    f"rsi > 65 and trend_strength > -{_TREND_RANGING_BOUND}"
    f" and trend_strength < {_TREND_RANGING_BOUND}"
)

_ICHIFIB_LONG_TEMPLATES = [
    "tenkan_sen > kijun_sen and close > senkou_span_a and close > senkou_span_b",
    "fib_zone_382 == 1 and trend_strength > {trend_min}",
]
_ICHIFIB_SHORT_TEMPLATES = [
    "tenkan_sen < kijun_sen and close < senkou_span_a and close < senkou_span_b",
    "fib_zone_618 == 1 and trend_strength < -{trend_min}",
]

_LIGHT_LONG_TEMPLATES = [
    _RSI_RANGE_LONG,
    "ma_short > ma_long and trend_strength > {trend_min}",
]
_LIGHT_SHORT_TEMPLATES = [
    _RSI_RANGE_SHORT,
    "ma_short < ma_long and trend_strength < -{trend_min}",
]

_PULLBACK_LONG_TEMPLATES = [
    "ma_short > ma_long and close > ma_long and rsi > 45 and rsi < 62 and trend_strength > {trend_min}",
    "ma_short > ma_long and close > open and close > ma_short and trend_strength > {trend_min}",
]
_PULLBACK_SHORT_TEMPLATES = [
    "ma_short < ma_long and close < ma_long and rsi < 55 and rsi > 38 and trend_strength < -{trend_min}",
    "ma_short < ma_long and close < open and close < ma_short and trend_strength < -{trend_min}",
]

_BREAKOUT_LONG_TEMPLATES = [
    "volatility > vol_min and close > ma_short and trend_strength > {trend_min}",
    "volatility > vol_min and close > ma_short and ma_short > ma_long and trend_strength > {trend_min}",
]
_BREAKOUT_SHORT_TEMPLATES = [
    "volatility > vol_min and close < ma_short and trend_strength < -{trend_min}",
    "volatility > vol_min and close < ma_short and ma_short < ma_long and trend_strength < -{trend_min}",
]

_COMPRESSION_LONG_TEMPLATES = [
    "volatility < vol_max and close > ma_short and trend_strength > {trend_min}",
    "volatility < vol_max and ma_short > ma_long and close > ma_short",
]
_COMPRESSION_SHORT_TEMPLATES = [
    "volatility < vol_max and close < ma_short and trend_strength < -{trend_min}",
    "volatility < vol_max and ma_short < ma_long and close < ma_short",
]

_SESSION_BREAKOUT_LONG_TEMPLATES = [
    "session_london == 1 and volatility > vol_min and close > ma_short and trend_strength > {trend_min}",
    "session_new_york == 1 and volatility > vol_min and close > ma_short and ma_short > ma_long",
]
_SESSION_BREAKOUT_SHORT_TEMPLATES = [
    "session_london == 1 and volatility > vol_min and close < ma_short and trend_strength < -{trend_min}",
    "session_new_york == 1 and volatility > vol_min and close < ma_short and ma_short < ma_long",
]

EXIT_TEMPLATES = [
    "rsi > {rsi_exit}",
    "rsi < {rsi_exit}",
    "trend_strength < {trend_exit}",
    "trend_strength > {trend_exit}",
]

TIME_EXIT_TEMPLATES = [
    "bars_since_entry >= {time_stop_bars}",
]

ATR_INVALIDATION_EXIT_TEMPLATES = [
    "bars_since_entry >= {time_stop_bars} or trend_strength < {trend_exit}",
    "bars_since_entry >= {time_stop_bars} or trend_strength > {trend_exit}",
]

SESSION_GUARD_EXIT_TEMPLATES = [
    "bars_since_entry >= {time_stop_bars} or session_new_york == 1",
    "bars_since_entry >= {time_stop_bars} or session_asia == 1",
]

TREND_EXIT_TEMPLATES = [
    "bars_since_entry >= {time_stop_bars} or trend_strength < {trend_exit}",
    "bars_since_entry >= {time_stop_bars} or trend_strength > {trend_exit}",
    "bars_since_entry >= {time_stop_bars} or rsi > {rsi_exit}",
    "bars_since_entry >= {time_stop_bars} or rsi < {rsi_exit}",
]

FADE_EXIT_TEMPLATES = [
    "rsi > {rsi_exit} or trend_strength < {trend_exit}",
    "rsi < {rsi_exit} or trend_strength > {trend_exit}",
    "bars_since_entry >= {time_stop_bars} or rsi > {rsi_exit}",
    "bars_since_entry >= {time_stop_bars} or rsi < {rsi_exit}",
]

PULLBACK_EXIT_TEMPLATES = [
    "bars_since_entry >= {time_stop_bars} or close < ma_short or trend_strength < {trend_exit}",
    "bars_since_entry >= {time_stop_bars} or close > ma_short or trend_strength > {trend_exit}",
    "bars_since_entry >= {time_stop_bars} or rsi > {rsi_exit}",
    "bars_since_entry >= {time_stop_bars} or rsi < {rsi_exit}",
]

BREAKOUT_EXIT_TEMPLATES = [
    "bars_since_entry >= {time_stop_bars} or trend_strength < {trend_exit}",
    "bars_since_entry >= {time_stop_bars} or trend_strength > {trend_exit}",
    "bars_since_entry >= {time_stop_bars} or close < ma_short",
    "bars_since_entry >= {time_stop_bars} or close > ma_short",
]

# Expose combined lists for backward compatibility
LONG_ENTRY_TEMPLATES = (
    _ICHIFIB_LONG_TEMPLATES
    + _LIGHT_LONG_TEMPLATES
    + _PULLBACK_LONG_TEMPLATES
    + _BREAKOUT_LONG_TEMPLATES
    + _COMPRESSION_LONG_TEMPLATES
    + _SESSION_BREAKOUT_LONG_TEMPLATES
)
SHORT_ENTRY_TEMPLATES = (
    _ICHIFIB_SHORT_TEMPLATES
    + _LIGHT_SHORT_TEMPLATES
    + _PULLBACK_SHORT_TEMPLATES
    + _BREAKOUT_SHORT_TEMPLATES
    + _COMPRESSION_SHORT_TEMPLATES
    + _SESSION_BREAKOUT_SHORT_TEMPLATES
)

XAU_IMPULSE_PULLBACK_LONG_TEMPLATES = [
    "session_london == 1 and close > ma_short and ma_short > ma_long and trend_strength > {trend_min} and volatility > vol_min",
    "close > ma_short and ma_short > ma_long and trend_strength > {trend_min} and fib_zone_382 == 1",
]
XAU_IMPULSE_PULLBACK_SHORT_TEMPLATES = [
    "session_london == 1 and close < ma_short and ma_short < ma_long and trend_strength < -{trend_min} and volatility > vol_min",
    "close < ma_short and ma_short < ma_long and trend_strength < -{trend_min} and fib_zone_618 == 1",
]

XAU_SESSION_CONTINUATION_LONG_TEMPLATES = [
    "session_london == 1 and ma_short > ma_long and close > ma_short and trend_strength > {trend_min}",
    "session_new_york == 1 and ma_short > ma_long and close > ma_short and volatility > vol_min",
]
XAU_SESSION_CONTINUATION_SHORT_TEMPLATES = [
    "session_london == 1 and ma_short < ma_long and close < ma_short and trend_strength < -{trend_min}",
    "session_new_york == 1 and ma_short < ma_long and close < ma_short and volatility > vol_min",
]

FAMILY_LIBRARY: Dict[str, Dict[str, Any]] = {
    "ma_trend": {
        "long": _LIGHT_LONG_TEMPLATES[1:],
        "short": _LIGHT_SHORT_TEMPLATES[1:],
        "regime_type": "trend",
        "playbook_type": "ma_trend",
        "preferred_sessions": ["london", "new_york"],
        "exit_templates": TREND_EXIT_TEMPLATES,
    },
    "rsi_range": {
        "long": _LIGHT_LONG_TEMPLATES[:1],
        "short": _LIGHT_SHORT_TEMPLATES[:1],
        "regime_type": "range",
        "playbook_type": "rsi_range_fade",
        "preferred_sessions": ["asia", "london"],
        "exit_templates": FADE_EXIT_TEMPLATES,
    },
    "pullback_trend": {
        "long": _PULLBACK_LONG_TEMPLATES,
        "short": _PULLBACK_SHORT_TEMPLATES,
        "regime_type": "trend",
        "playbook_type": "pullback_trend",
        "preferred_sessions": ["london"],
        "exit_templates": PULLBACK_EXIT_TEMPLATES,
    },
    "vol_breakout": {
        "long": _BREAKOUT_LONG_TEMPLATES,
        "short": _BREAKOUT_SHORT_TEMPLATES,
        "regime_type": "breakout",
        "playbook_type": "vol_breakout",
        "preferred_sessions": ["london", "new_york"],
        "exit_templates": BREAKOUT_EXIT_TEMPLATES,
    },
    "compression_breakout": {
        "long": _COMPRESSION_LONG_TEMPLATES,
        "short": _COMPRESSION_SHORT_TEMPLATES,
        "regime_type": "breakout",
        "playbook_type": "compression_expansion",
        "preferred_sessions": ["asia", "london"],
        "exit_templates": BREAKOUT_EXIT_TEMPLATES,
    },
    "session_breakout": {
        "long": _SESSION_BREAKOUT_LONG_TEMPLATES,
        "short": _SESSION_BREAKOUT_SHORT_TEMPLATES,
        "regime_type": "breakout",
        "playbook_type": "session_breakout",
        "preferred_sessions": ["london", "new_york"],
        "exit_templates": BREAKOUT_EXIT_TEMPLATES + SESSION_GUARD_EXIT_TEMPLATES,
    },
    "xau_impulse_pullback": {
        "long": XAU_IMPULSE_PULLBACK_LONG_TEMPLATES,
        "short": XAU_IMPULSE_PULLBACK_SHORT_TEMPLATES,
        "regime_type": "trend",
        "playbook_type": "xau_impulse_pullback",
        "preferred_sessions": ["london", "new_york"],
        "exit_templates": ATR_INVALIDATION_EXIT_TEMPLATES + PULLBACK_EXIT_TEMPLATES,
        "allowed_symbols": ["XAUUSDm"],
    },
    "xau_session_continuation": {
        "long": XAU_SESSION_CONTINUATION_LONG_TEMPLATES,
        "short": XAU_SESSION_CONTINUATION_SHORT_TEMPLATES,
        "regime_type": "trend",
        "playbook_type": "xau_session_continuation",
        "preferred_sessions": ["london", "new_york"],
        "exit_templates": ATR_INVALIDATION_EXIT_TEMPLATES + SESSION_GUARD_EXIT_TEMPLATES + TIME_EXIT_TEMPLATES,
        "allowed_symbols": ["XAUUSDm"],
    },
}

CORE_M15_FAMILY_WEIGHTS: Dict[str, float] = {
    "ma_trend": 0.14,
    "rsi_range": 0.14,
    "pullback_trend": 0.22,
    "vol_breakout": 0.16,
    "compression_breakout": 0.14,
    "session_breakout": 0.12,
    "xau_impulse_pullback": 0.05,
    "xau_session_continuation": 0.03,
}

XAG_M15_FAMILY_WEIGHTS: Dict[str, float] = {
    "ma_trend": 0.08,
    "rsi_range": 0.07,
    "pullback_trend": 0.16,
    "vol_breakout": 0.26,
    "compression_breakout": 0.21,
    "session_breakout": 0.22,
}


def _weighted_choice(weights: Dict[str, float]) -> str:
    labels = list(weights.keys())
    vals = list(weights.values())
    return random.choices(labels, weights=vals, k=1)[0]


def _normalize_family_for_market(family: str, symbol: str) -> str:
    family_meta = FAMILY_LIBRARY.get(family, {})
    allowed_symbols = set(family_meta.get("allowed_symbols", []) or [])
    if allowed_symbols and symbol not in allowed_symbols:
        return "pullback_trend" if family == "xau_impulse_pullback" else "session_breakout"
    return family


# ---------------------------------------------------------------------------
# Template classification
# ---------------------------------------------------------------------------

def _classify_template(tpl: str) -> Tuple[str, str]:
    if "session_london" in tpl or "session_new_york" in tpl:
        return "session_breakout", "breakout"
    if "tenkan_sen" in tpl or "fib_zone" in tpl:
        return "ichifib", "trend"
    if "volatility < vol_max" in tpl:
        return "compression_breakout", "breakout"
    if "volatility > vol_min" in tpl:
        return "vol_breakout", "breakout"
    if "close > open" in tpl or "close < open" in tpl:
        return "pullback_trend", "trend"
    if "ma_short" in tpl and "ma_long" in tpl:
        return "ma_trend", "trend"
    if "rsi" in tpl and "trend_strength" in tpl:
        return "rsi_range", "range"
    return "generic", "unknown"


def _sample_family_params(family: str, symbol: str, timeframe: str) -> Dict[str, Any]:
    family = _normalize_family_for_market(family, symbol)
    params: Dict[str, Any] = {
        "trend_min": round(random.uniform(_TREND_MIN_LOW, _TREND_MIN_HIGH), 2),
        "rsi_exit": random.randint(40, 60),
        "trend_exit": round(random.uniform(_TREND_EXIT_LOW, _TREND_EXIT_HIGH), 2),
        "preferred_symbols": [symbol],
        "preferred_timeframes": [timeframe],
        "stop_loss_pips": random.choice([50, 75, 100, 150]),
        "take_profit_pips": random.choice([50, 100, 150, 200]),
        "vol_min": round(random.uniform(0.4, 1.2), 3),
        "vol_max": round(random.uniform(0.15, 0.8), 3),
        "time_stop_bars": random.choice([4, 6, 8, 12]),
        "preferred_sessions": [],
        "family": family,
        "playbook_type": family,
        "primary_market_condition": family,
    }

    family_meta = FAMILY_LIBRARY.get(family, {})
    if family_meta:
        params["preferred_sessions"] = list(family_meta.get("preferred_sessions", []) or [])
        params["playbook_type"] = str(family_meta.get("playbook_type", family))
        params["primary_market_condition"] = str(family_meta.get("regime_type", "unknown"))

    if family == "rsi_range":
        params["trend_min"] = round(random.uniform(0.04, 0.12), 2)
        params["trend_exit"] = round(random.uniform(-0.06, 0.06), 2)
        params["rsi_exit"] = random.randint(48, 58)
        params["vol_max"] = round(random.uniform(0.18, 0.55), 3)
        params["stop_loss_pips"] = random.choice([50, 75, 100])
        params["take_profit_pips"] = random.choice([50, 75, 100, 125])
        params["time_stop_bars"] = random.choice([4, 6, 8])
    elif family == "vol_breakout":
        params["vol_min"] = round(random.uniform(0.55, 1.15), 3)
        params["trend_min"] = round(random.uniform(0.08, 0.24), 2)
        params["time_stop_bars"] = random.choice([3, 4, 6, 8])
    elif family == "session_breakout":
        params["vol_min"] = round(random.uniform(0.55, 1.10), 3)
        params["trend_min"] = round(random.uniform(0.06, 0.20), 2)
        params["time_stop_bars"] = random.choice([3, 4, 6, 8])
    elif family == "compression_breakout":
        params["vol_max"] = round(random.uniform(0.20, 0.55), 3)
        params["trend_min"] = round(random.uniform(0.05, 0.18), 2)
        params["time_stop_bars"] = random.choice([4, 6, 8])
    elif family == "pullback_trend":
        params["trend_min"] = round(random.uniform(0.12, 0.28), 2)
        params["trend_exit"] = round(random.uniform(-0.08, 0.04), 2)
        params["rsi_exit"] = random.randint(50, 60)
        params["time_stop_bars"] = random.choice([6, 8, 10, 12])
    elif family == "ma_trend":
        params["trend_min"] = round(random.uniform(0.10, 0.26), 2)
        params["trend_exit"] = round(random.uniform(-0.08, 0.05), 2)
        params["time_stop_bars"] = random.choice([4, 6, 8, 12])

    is_core_15m = symbol in {"XAUUSDm", "BTCUSDm"} and timeframe == "M15"
    if is_core_15m:
        if family in {"vol_breakout", "session_breakout"}:
            params["sl_atr_mult"] = random.choice([1.8, 2.0, 2.2, 2.5])
            params["tp_atr_mult"] = random.choice([2.5, 3.0, 3.5, 4.0])
        elif family == "rsi_range":
            params["sl_atr_mult"] = random.choice([1.2, 1.5, 1.8])
            params["tp_atr_mult"] = random.choice([1.5, 2.0, 2.5])
        else:
            params["sl_atr_mult"] = random.choice([1.5, 1.8, 2.0, 2.2])
            params["tp_atr_mult"] = random.choice([2.0, 2.5, 3.0, 3.5])

    if symbol == "XAUUSDm" and timeframe == "M15":
        params["microstructure_profile"] = "xau_m15"
        params["stop_loss_pips"] = random.choice([150, 200, 250, 300])
        params["take_profit_pips"] = random.choice([200, 250, 300, 400, 500])
        if family in {"xau_impulse_pullback", "xau_session_continuation"}:
            params["trend_min"] = round(random.uniform(0.08, 0.18), 2)
            params["trend_exit"] = round(random.uniform(-0.08, 0.03), 2)
            params["vol_min"] = round(random.uniform(0.55, 1.05), 3)
            params["time_stop_bars"] = random.choice([3, 4, 6, 8])
            params["sl_atr_mult"] = random.choice([1.8, 2.0, 2.2, 2.5])
            params["tp_atr_mult"] = random.choice([2.5, 3.0, 3.5, 4.0])
        elif family == "pullback_trend":
            params["trend_min"] = round(random.uniform(0.10, 0.20), 2)
            params["time_stop_bars"] = random.choice([4, 6, 8])
        elif family == "vol_breakout":
            params["trend_min"] = round(random.uniform(0.08, 0.20), 2)
            params["vol_min"] = round(random.uniform(0.65, 1.10), 3)
        elif family == "session_breakout":
            params["trend_min"] = round(random.uniform(0.06, 0.18), 2)
            params["vol_min"] = round(random.uniform(0.60, 1.00), 3)
        elif family == "ma_trend":
            params["trend_min"] = round(random.uniform(0.10, 0.18), 2)
        elif family == "rsi_range":
            params["vol_max"] = round(random.uniform(0.18, 0.35), 3)

    if symbol == "XAGUSDm" and timeframe == "M15":
        params["microstructure_profile"] = "xag_m15"
        params["stop_loss_pips"] = random.choice([75, 100, 125])
        params["take_profit_pips"] = random.choice([125, 150, 200, 250])
        if family == "compression_breakout":
            params["vol_max"] = round(random.uniform(0.003, 0.008), 4)
            params["trend_min"] = round(random.uniform(0.01, 0.08), 2)
            params["trend_exit"] = round(random.uniform(-0.03, 0.02), 2)
            params["time_stop_bars"] = random.choice([8, 10, 12])
        elif family == "vol_breakout":
            params["vol_min"] = round(random.uniform(0.003, 0.007), 4)
            params["trend_min"] = round(random.uniform(0.03, 0.12), 2)
            params["trend_exit"] = round(random.uniform(-0.04, 0.03), 2)
            params["time_stop_bars"] = random.choice([6, 8, 10])
        elif family == "session_breakout":
            params["vol_min"] = round(random.uniform(0.0025, 0.0065), 4)
            params["trend_min"] = round(random.uniform(0.02, 0.10), 2)
            params["trend_exit"] = round(random.uniform(-0.04, 0.02), 2)
            params["time_stop_bars"] = random.choice([6, 8, 10, 12])
        elif family == "pullback_trend":
            params["trend_min"] = round(random.uniform(0.12, 0.22), 2)
            params["trend_exit"] = round(random.uniform(-0.04, 0.01), 2)
            params["rsi_exit"] = random.randint(52, 58)
            params["time_stop_bars"] = random.choice([6, 8, 10])
        elif family == "ma_trend":
            params["trend_min"] = round(random.uniform(0.16, 0.26), 2)
            params["trend_exit"] = round(random.uniform(-0.04, 0.02), 2)
            params["time_stop_bars"] = random.choice([6, 8, 10])
        elif family == "rsi_range":
            params["trend_min"] = round(random.uniform(0.01, 0.05), 2)
            params["trend_exit"] = round(random.uniform(-0.02, 0.02), 2)
            params["rsi_exit"] = random.randint(50, 54)
            params["vol_max"] = round(random.uniform(0.24, 0.48), 3)
            params["time_stop_bars"] = random.choice([4, 6, 8])

    if symbol == "BTCUSDm" and timeframe == "M15":
        params["microstructure_profile"] = "btc_m15"
        if family == "ma_trend":
            params["trend_min"] = round(random.uniform(0.14, 0.24), 3)
            params["trend_exit"] = round(random.uniform(-0.04, 0.03), 3)
            params["rsi_exit"] = random.randint(52, 58)
            params["sl_atr_mult"] = random.choice([2.2, 2.5, 2.8])
            params["tp_atr_mult"] = random.choice([3.5, 4.0, 4.5])
            params["stop_loss_pips"] = random.choice([100, 125, 150])
            params["take_profit_pips"] = random.choice([200, 250, 300])
            params["time_stop_bars"] = random.choice([6, 8, 10])
        elif family == "rsi_range":
            params["trend_min"] = round(random.uniform(0.02, 0.07), 3)
            params["trend_exit"] = round(random.uniform(-0.03, 0.03), 3)
            params["rsi_exit"] = random.randint(50, 56)
            params["sl_atr_mult"] = random.choice([1.5, 1.8, 2.0])
            params["tp_atr_mult"] = random.choice([2.0, 2.5, 3.0])
            params["stop_loss_pips"] = random.choice([75, 100, 125])
            params["take_profit_pips"] = random.choice([150, 200, 250])
            params["time_stop_bars"] = random.choice([4, 6, 8])

    params["family"] = family
    params["playbook_type"] = str((FAMILY_LIBRARY.get(family, {}) or {}).get("playbook_type", family))
    params["primary_market_condition"] = str((FAMILY_LIBRARY.get(family, {}) or {}).get("regime_type", params.get("primary_market_condition", "unknown")))

    return params


def _weighted_template_choice(templates: List[str], weighted_terms: Dict[str, float]) -> str:
    if not templates:
        raise ValueError("templates must not be empty")
    weights = []
    for tpl in templates:
        score = 1.0
        for term, bonus in weighted_terms.items():
            if term and term in tpl:
                score += bonus
        weights.append(max(0.05, score))
    return random.choices(list(templates), weights=weights, k=1)[0]


_EXIT_COMPATIBILITY_WEIGHTS: Dict[str, Dict[str, float]] = {
    "ma_trend": {
        "bars_since_entry": 1.2,
        "trend_strength": 1.0,
        "close < ma_short": 0.8,
        "close > ma_short": 0.8,
        "rsi >": -0.35,
        "rsi <": -0.35,
    },
    "pullback_trend": {
        "bars_since_entry": 1.1,
        "close < ma_short": 1.1,
        "close > ma_short": 1.1,
        "trend_strength": 0.7,
        "rsi >": -0.15,
        "rsi <": -0.15,
    },
    "vol_breakout": {
        "bars_since_entry": 1.0,
        "trend_strength": 1.0,
        "close < ma_short": 0.9,
        "close > ma_short": 0.9,
        "rsi >": -0.45,
        "rsi <": -0.45,
    },
    "compression_breakout": {
        "bars_since_entry": 1.0,
        "trend_strength": 0.9,
        "close < ma_short": 0.8,
        "close > ma_short": 0.8,
        "rsi >": -0.25,
        "rsi <": -0.25,
    },
    "session_breakout": {
        "bars_since_entry": 1.0,
        "session_new_york": 0.6,
        "session_asia": 0.6,
        "trend_strength": 0.9,
        "close < ma_short": 0.7,
        "close > ma_short": 0.7,
        "rsi >": -0.35,
        "rsi <": -0.35,
    },
    "rsi_range": {
        "rsi >": 1.0,
        "rsi <": 1.0,
        "bars_since_entry": 0.7,
        "trend_strength": 0.4,
        "close < ma_short": -0.2,
        "close > ma_short": -0.2,
    },
    "xau_impulse_pullback": {
        "bars_since_entry": 1.1,
        "trend_strength": 1.0,
        "close < ma_short": 1.0,
        "close > ma_short": 1.0,
        "rsi >": -0.25,
        "rsi <": -0.25,
    },
    "xau_session_continuation": {
        "bars_since_entry": 1.0,
        "session_new_york": 0.8,
        "session_asia": 0.8,
        "trend_strength": 0.9,
        "rsi >": -0.30,
        "rsi <": -0.30,
    },
}


def _pick_family_templates(family: str, symbol: Optional[str] = None) -> tuple[str, str, str]:
    if symbol is not None:
        family = _normalize_family_for_market(family, symbol)
    family_meta = FAMILY_LIBRARY.get(family) or FAMILY_LIBRARY["ma_trend"]

    if symbol == "XAGUSDm" and family == "session_breakout":
        long_templates = [
            "session_london == 1 and volatility > vol_min and trend_strength > {trend_min}",
            "session_new_york == 1 and volatility > vol_min and close > ma_short and trend_strength > {trend_min}",
        ]
        short_templates = [
            "session_london == 1 and volatility > vol_min and trend_strength < -{trend_min}",
            "session_new_york == 1 and volatility > vol_min and close < ma_short and trend_strength < -{trend_min}",
        ]
        exit_templates = list(family_meta.get("exit_templates", EXIT_TEMPLATES))
        exit_tpl = _weighted_template_choice(exit_templates, _EXIT_COMPATIBILITY_WEIGHTS.get(family, {}))
        return random.choice(long_templates), random.choice(short_templates), exit_tpl

    if symbol == "XAGUSDm" and family == "vol_breakout":
        long_templates = [
            "volatility > vol_min and trend_strength > {trend_min}",
            "volatility > vol_min and close > ma_short and trend_strength > {trend_min}",
        ]
        short_templates = [
            "volatility > vol_min and trend_strength < -{trend_min}",
            "volatility > vol_min and close < ma_short and trend_strength < -{trend_min}",
        ]
        exit_templates = list(family_meta.get("exit_templates", EXIT_TEMPLATES))
        exit_tpl = _weighted_template_choice(exit_templates, _EXIT_COMPATIBILITY_WEIGHTS.get(family, {}))
        return random.choice(long_templates), random.choice(short_templates), exit_tpl

    long_tpl = random.choice(list(family_meta.get("long", _LIGHT_LONG_TEMPLATES)))
    short_tpl = random.choice(list(family_meta.get("short", _LIGHT_SHORT_TEMPLATES)))
    exit_tpl = _weighted_template_choice(list(family_meta.get("exit_templates", EXIT_TEMPLATES)), _EXIT_COMPATIBILITY_WEIGHTS.get(family, {}))
    return long_tpl, short_tpl, exit_tpl


# ---------------------------------------------------------------------------
# Core generation helper
# ---------------------------------------------------------------------------

def _build_strategy_from_templates(
    symbol: str,
    timeframe: str,
    long_tpl: str,
    short_tpl: str,
    exit_tpl: str,
    params: Dict[str, Any],
    name_prefix: str,
) -> StrategyDefinition:
    long_entry_rule = long_tpl.format(**params)
    short_entry_rule = short_tpl.format(**params)
    exit_rule = exit_tpl.format(**params)

    long_family, long_regime = _classify_template(long_tpl)
    short_family, short_regime = _classify_template(short_tpl)
    exit_family, _ = _classify_template(exit_tpl)

    params = dict(params)
    params["long_family"] = long_family
    params["short_family"] = short_family
    params["exit_family"] = exit_family
    params["regime_type_long"] = long_regime
    params["regime_type_short"] = short_regime
    params["regime_type"] = long_regime if long_regime == short_regime else "mixed"
    params["family"] = params.get("family") or (long_family if long_family == short_family else "mixed")
    params.setdefault("playbook_type", params["family"])
    params["has_time_stop"] = "bars_since_entry" in exit_rule
    params["has_session_exit_guard"] = ("session_new_york" in exit_rule) or ("session_asia" in exit_rule)
    params["exit_archetype"] = (
        "session_guard" if params["has_session_exit_guard"]
        else "time_stop" if params["has_time_stop"]
        else "state_change"
    )

    uid = uuid.uuid4().hex[:4]
    name = f"{name_prefix}_{symbol}_{timeframe}_{uid}"

    sl_atr_mult = params.get("sl_atr_mult")
    tp_atr_mult = params.get("tp_atr_mult")
    stop_loss_pips = params.get("stop_loss_pips", random.choice([50, 75, 100, 150]))
    take_profit_pips = params.get("take_profit_pips", random.choice([50, 100, 150, 200]))

    return StrategyDefinition(
        name=name,
        symbol=symbol,
        timeframe=timeframe,
        long_entry_rule=long_entry_rule,
        short_entry_rule=short_entry_rule,
        exit_rule=exit_rule,
        stop_loss_pips=float(stop_loss_pips),
        take_profit_pips=float(take_profit_pips),
        sl_atr_mult=sl_atr_mult,
        tp_atr_mult=tp_atr_mult,
        params=params,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def random_strategy(symbol: str, timeframe: str, family: Optional[str] = None) -> StrategyDefinition:
    """Generate a deterministic-rule strategy.

    Core M15 markets use a broader but still deterministic family set so the
    search space contains genuinely different playbooks, not just MA/RSI cousins.
    """
    is_core_15m = symbol in {"XAUUSDm", "BTCUSDm"} and timeframe == "M15"
    is_xag_m15 = symbol == "XAGUSDm" and timeframe == "M15"

    if family is None:
        if is_core_15m:
            family = _weighted_choice(CORE_M15_FAMILY_WEIGHTS)
        elif is_xag_m15:
            family = _weighted_choice(XAG_M15_FAMILY_WEIGHTS)
        else:
            family = random.choice(list(FAMILY_LIBRARY.keys()))

    family = _normalize_family_for_market(family, symbol)
    long_tpl, short_tpl, exit_tpl = _pick_family_templates(family, symbol=symbol)
    params = _sample_family_params(family, symbol, timeframe)

    name_prefix = "core15" if is_core_15m else family

    strat = _build_strategy_from_templates(
        symbol=symbol,
        timeframe=timeframe,
        long_tpl=long_tpl,
        short_tpl=short_tpl,
        exit_tpl=exit_tpl,
        params=params,
        name_prefix=name_prefix,
    )

    logger.info("Generated strategy %s", strat.to_dict())
    return strat


def rebuild_strategy_from_params(
    symbol: str,
    timeframe: str,
    params: Dict[str, Any],
    name_prefix: str = "core15",
) -> StrategyDefinition:
    """Re-generate rule strings from params while preserving family intent."""
    is_core_15m = symbol in {"XAUUSDm", "BTCUSDm"} and timeframe == "M15"

    family = str((params or {}).get("family") or (params or {}).get("playbook_type") or "ma_trend")
    if family not in FAMILY_LIBRARY:
        family = "ma_trend"
    family = _normalize_family_for_market(family, symbol)

    params = dict(params)
    base_params = _sample_family_params(family, symbol, timeframe)
    base_params.update(params)
    params = base_params
    params["family"] = family
    params["playbook_type"] = str((FAMILY_LIBRARY.get(family, {}) or {}).get("playbook_type", family))
    params["primary_market_condition"] = str((FAMILY_LIBRARY.get(family, {}) or {}).get("regime_type", params.get("primary_market_condition", "unknown")))

    long_tpl, short_tpl, exit_tpl = _pick_family_templates(family, symbol=symbol)

    if is_core_15m:
        name_prefix = "core15"

    return _build_strategy_from_templates(
        symbol=symbol,
        timeframe=timeframe,
        long_tpl=long_tpl,
        short_tpl=short_tpl,
        exit_tpl=exit_tpl,
        params=params,
        name_prefix=name_prefix,
    )


def save_strategy(strategy: StrategyDefinition) -> Path:
    path = GENERATED_DIR / f"{strategy.name}.json"
    with path.open("w", encoding="utf-8") as f:
        json.dump(strategy.to_dict(), f, indent=2)
    logger.info("Saved strategy %s to %s", strategy.name, path)
    return path


def load_strategy(path: Path) -> StrategyDefinition:
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    return StrategyDefinition.from_dict(data)


def load_all_strategies() -> List[StrategyDefinition]:
    if not GENERATED_DIR.exists():
        return []
    out: List[StrategyDefinition] = []
    for path in GENERATED_DIR.glob("*.json"):
        try:
            out.append(load_strategy(path))
        except Exception:
            logger.exception("Failed to load strategy from %s", path)
    return out


def generated_family_counts(symbol: Optional[str] = None, timeframe: Optional[str] = None) -> Counter:
    counts: Counter = Counter()
    for strat in load_all_strategies():
        if symbol is not None and strat.symbol != symbol:
            continue
        if timeframe is not None and strat.timeframe != timeframe:
            continue
        counts[str((getattr(strat, 'params', {}) or {}).get('family') or (getattr(strat, 'params', {}) or {}).get('playbook_type') or 'unknown')] += 1
    return counts
