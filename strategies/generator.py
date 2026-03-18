from __future__ import annotations

import json
import random
import uuid
from pathlib import Path
from typing import List, Tuple, Dict, Any

from .base import StrategyDefinition
from ..logging_utils import get_logger

logger = get_logger(__name__)

STRATEGY_DIR = Path(__file__).resolve().parent
GENERATED_DIR = STRATEGY_DIR / "generated"
GENERATED_DIR.mkdir(exist_ok=True)

# ---------------------------------------------------------------------------
# Threshold alignment with regime.py RegimeConfig (ATR-normalised scale).
#
# These must stay in sync with regime.RegimeConfig defaults:
#   trend_up_thresh    = 0.08
#   strong_trend_thresh = 0.30
#
# RSI range templates use TREND_RANGING_BOUND as the flat-market filter so
# that the boundary matches what regime detection considers "ranging".
# ---------------------------------------------------------------------------
_TREND_UP_THRESH = 0.08      # minimum trend_strength to count as trending
_TREND_RANGING_BOUND = 0.08  # used in RSI range templates: |trend_strength| < this = ranging
_STRONG_TREND_THRESH = 0.30  # strong-trend level

# trend_min sampling range aligned to ATR-normalised scale.
# Values above _STRONG_TREND_THRESH start to be rare; going much above 0.5
# means the entry condition almost never fires.
_TREND_MIN_LOW = 0.05
_TREND_MIN_HIGH = 0.50

# trend_exit range: exit when trend_strength falls below this threshold.
# Must be below _TREND_UP_THRESH to avoid immediate exit after entry.
# Clamped to [-0.20, 0.15] to prevent drift during mutation.
_TREND_EXIT_LOW = -0.15
_TREND_EXIT_HIGH = 0.10
_TREND_EXIT_CLAMP_MIN = -0.20
_TREND_EXIT_CLAMP_MAX = 0.15

# ---------------------------------------------------------------------------
# Entry / exit templates
# ---------------------------------------------------------------------------
# RSI range templates use a parameterised trend_strength bound so that it
# can be updated in one place (_TREND_RANGING_BOUND) rather than scattered
# hardcoded values.

_RSI_RANGE_LONG = (
    f"rsi < 35 and trend_strength > -{_TREND_RANGING_BOUND}"
    f" and trend_strength < {_TREND_RANGING_BOUND}"
)
_RSI_RANGE_SHORT = (
    f"rsi > 65 and trend_strength > -{_TREND_RANGING_BOUND}"
    f" and trend_strength < {_TREND_RANGING_BOUND}"
)

# Heavy Ichimoku / Fibonacci templates (disabled for core 15m markets)
_ICHIFIB_LONG_TEMPLATES = [
    "tenkan_sen > kijun_sen and close > senkou_span_a and close > senkou_span_b",
    "fib_zone_382 == 1 and trend_strength > {trend_min}",
]
_ICHIFIB_SHORT_TEMPLATES = [
    "tenkan_sen < kijun_sen and close < senkou_span_a and close < senkou_span_b",
    "fib_zone_618 == 1 and trend_strength < -{trend_min}",
]

# Lighter MA / RSI templates (preferred for core 15m markets)
_LIGHT_LONG_TEMPLATES = [
    _RSI_RANGE_LONG,
    "ma_short > ma_long and trend_strength > {trend_min}",
]
_LIGHT_SHORT_TEMPLATES = [
    _RSI_RANGE_SHORT,
    "ma_short < ma_long and trend_strength < -{trend_min}",
]

EXIT_TEMPLATES = [
    "rsi > {rsi_exit}",
    "rsi < {rsi_exit}",
    "trend_strength < {trend_exit}",
]

# Expose combined lists for backward compatibility (e.g. load_population scans)
LONG_ENTRY_TEMPLATES = _ICHIFIB_LONG_TEMPLATES + _LIGHT_LONG_TEMPLATES
SHORT_ENTRY_TEMPLATES = _ICHIFIB_SHORT_TEMPLATES + _LIGHT_SHORT_TEMPLATES


# ---------------------------------------------------------------------------
# Template classification
# ---------------------------------------------------------------------------

def _classify_template(tpl: str) -> Tuple[str, str]:
    """Return (family, regime_type) for a given entry rule template string."""
    if "tenkan_sen" in tpl or "fib_zone" in tpl:
        return "ichifib", "trend"
    if "ma_short" in tpl and "ma_long" in tpl:
        return "ma_trend", "trend"
    if "rsi" in tpl and "trend_strength" in tpl:
        return "rsi_range", "range"
    return "generic", "unknown"


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
    """Instantiate a StrategyDefinition from templates + params.

    Rules are formatted from the provided params dict so that params and
    rule strings are ALWAYS in sync. This is the single place where
    rule baking happens.
    """
    long_entry_rule = long_tpl.format(**params)
    short_entry_rule = short_tpl.format(**params)
    exit_rule = exit_tpl.format(**params)

    long_family, long_regime = _classify_template(long_tpl)
    short_family, short_regime = _classify_template(short_tpl)

    params = dict(params)  # copy — don't mutate caller's dict
    params["long_family"] = long_family
    params["short_family"] = short_family
    params["regime_type_long"] = long_regime
    params["regime_type_short"] = short_regime
    params["regime_type"] = long_regime if long_regime == short_regime else "mixed"

    # Use a short UUID suffix to avoid name collisions across many cycles.
    # randint(1000, 9999) gives only 9000 possibilities — with population_size=20
    # and research every 30min, collisions happen within hours and silently
    # overwrite better strategies on disk.
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

def random_strategy(symbol: str, timeframe: str) -> StrategyDefinition:
    """Generate a random strategy config.

    For core 15m markets (XAUUSDm / BTCUSDm M15) only lighter MA/RSI
    templates are used. All markets now use ATR-normalised thresholds that
    align with regime.RegimeConfig defaults.
    """
    is_core_15m = symbol in {"XAUUSDm", "BTCUSDm"} and timeframe == "M15"

    # Both core and non-core currently use only light templates.
    # Heavy Ichimoku/Fib templates are available in _ICHIFIB_* for future use.
    long_tpl = random.choice(_LIGHT_LONG_TEMPLATES)
    short_tpl = random.choice(_LIGHT_SHORT_TEMPLATES)
    exit_tpl = random.choice(EXIT_TEMPLATES)

    # ATR-normalised param ranges (aligned with regime.RegimeConfig)
    params: Dict[str, Any] = {
        "trend_min": round(random.uniform(_TREND_MIN_LOW, _TREND_MIN_HIGH), 2),
        "rsi_exit": random.randint(40, 60),
        "trend_exit": round(random.uniform(_TREND_EXIT_LOW, _TREND_EXIT_HIGH), 2),
        "preferred_symbols": [symbol],
        "preferred_timeframes": [timeframe],
        "stop_loss_pips": random.choice([50, 75, 100, 150]),
        "take_profit_pips": random.choice([50, 100, 150, 200]),
    }

    if is_core_15m:
        params["sl_atr_mult"] = random.choice([1.5, 2.0, 2.5])
        params["tp_atr_mult"] = random.choice([2.0, 3.0, 4.0])

    name_prefix = "core15" if is_core_15m else "ichifib"

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
    """Re-generate rule strings from a params dict and fresh template selection.

    Used by evolution (_mutate_strategy, _crossover) to ensure rule strings
    and params are always in sync after modification.
    """
    is_core_15m = symbol in {"XAUUSDm", "BTCUSDm"} and timeframe == "M15"

    long_tpl = random.choice(_LIGHT_LONG_TEMPLATES)
    short_tpl = random.choice(_LIGHT_SHORT_TEMPLATES)
    exit_tpl = random.choice(EXIT_TEMPLATES)

    # Ensure name_prefix reflects market
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
    strat = StrategyDefinition.from_dict(data)
    logger.info("Loaded strategy %s from %s", strat.name, path)
    return strat


def generate_batch(symbol: str, timeframe: str, n: int) -> List[StrategyDefinition]:
    return [random_strategy(symbol, timeframe) for _ in range(n)]


def generate_and_save_batch(symbol: str, timeframe: str, n: int) -> List[Path]:
    return [save_strategy(s) for s in generate_batch(symbol, timeframe, n)]