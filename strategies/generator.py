from __future__ import annotations

import json
import random
from pathlib import Path
from typing import List, Tuple

from .base import StrategyDefinition
from ..logging_utils import get_logger

logger = get_logger(__name__)

STRATEGY_DIR = Path(__file__).resolve().parent
GENERATED_DIR = STRATEGY_DIR / "generated"
GENERATED_DIR.mkdir(exist_ok=True)


# Entry templates
# NOTE: Ordering and content are used for lightweight family classification
# in random_strategy; if you change these, also update the classification
# logic below.

# Ichimoku: bullish alignment above the cloud (heavy template)
LONG_ENTRY_TEMPLATES = [
    "tenkan_sen > kijun_sen and close > senkou_span_a and close > senkou_span_b",
    # Fib + trend (heavy template)
    "fib_zone_382 == 1 and trend_strength > {trend_min}",
]

SHORT_ENTRY_TEMPLATES = [
    # Ichimoku: bearish alignment below the cloud (heavy template)
    "tenkan_sen < kijun_sen and close < senkou_span_a and close < senkou_span_b",
    # Fib + trend (heavy template)
    "fib_zone_618 == 1 and trend_strength < -{trend_min}",
]

# Range / mean reversion: fade extremes when trend_strength is low (lighter, RSI-based)
LONG_ENTRY_TEMPLATES.append(
    "rsi < 35 and trend_strength > -0.1 and trend_strength < 0.1"
)

SHORT_ENTRY_TEMPLATES.append(
    "rsi > 65 and trend_strength > -0.1 and trend_strength < 0.1"
)

# MA-based trend continuation (lighter, trend-follow)
LONG_ENTRY_TEMPLATES.append(
    "ma_short > ma_long and trend_strength > {trend_min}"
)

SHORT_ENTRY_TEMPLATES.append(
    "ma_short < ma_long and trend_strength < -{trend_min}"
)

EXIT_TEMPLATES = [
    "rsi > {rsi_exit}",
    "rsi < {rsi_exit}",
    "trend_strength < {trend_exit}",
]


def _classify_template(tpl: str) -> Tuple[str, str]:
    """Return (family, regime_type) for a given entry rule template.

    This is a lightweight heuristic used to tag generated strategies with
    metadata inside `StrategyDefinition.params` so that later phases
    (regime-aware selection, governance) can reason about families.
    """
    if "tenkan_sen" in tpl or "fib_zone" in tpl:
        return "ichifib", "trend"
    if "ma_short" in tpl and "ma_long" in tpl:
        return "ma_trend", "trend"
    if "rsi" in tpl and "trend_strength" in tpl:
        # mean-reversion in low-trend conditions
        return "rsi_range", "range"
    return "generic", "unknown"


def random_strategy(symbol: str, timeframe: str) -> StrategyDefinition:
    """Generate a strategy config.

    Phase 3 tweak: for key markets (XAUUSDm/BTCUSDm on M15), bias away
    from heavy Ichimoku/Fibonacci templates and toward simpler
    MA/RSI-based structures, while still allowing the legacy templates
    for other markets.
    """

    is_core_15m = symbol in {"XAUUSDm", "BTCUSDm"} and timeframe == "M15"

    # Split templates by family so we can bias selection
    def _split_templates(templates):
        heavy = []   # ichimoku / fib
        light = []   # ma/RSI-based
        for tpl in templates:
            family, _ = _classify_template(tpl)
            if family == "ichifib":
                heavy.append(tpl)
            else:
                light.append(tpl)
        return heavy, light

    long_heavy, long_light = _split_templates(LONG_ENTRY_TEMPLATES)
    short_heavy, short_light = _split_templates(SHORT_ENTRY_TEMPLATES)

    if is_core_15m:
        # For core 15m markets, use only the lighter MA/RSI templates.
        long_pool = long_light or LONG_ENTRY_TEMPLATES
        short_pool = short_light or SHORT_ENTRY_TEMPLATES
    else:
        # For other markets, still prefer light templates but allow
        # occasional heavy ones.
        long_pool = long_light * 3 + long_heavy
        short_pool = short_light * 3 + short_heavy

    long_tpl = random.choice(long_pool)
    short_tpl = random.choice(short_pool)
    exit_tpl = random.choice(EXIT_TEMPLATES)

    params = {
        "trend_min": round(random.uniform(0.1, 1.0), 2),
        "rsi_exit": random.randint(40, 60),
        "trend_exit": round(random.uniform(-0.1, 0.1), 2),
    }

    long_entry_rule = long_tpl.format(**params)
    short_entry_rule = short_tpl.format(**params)
    exit_rule = exit_tpl.format(**params)

    stop_loss_pips = random.choice([50, 75, 100, 150])
    take_profit_pips = random.choice([50, 100, 150, 200])

    long_family, long_regime = _classify_template(long_tpl)
    short_family, short_regime = _classify_template(short_tpl)

    # Basic metadata for later phases
    params["long_family"] = long_family
    params["short_family"] = short_family
    params["regime_type_long"] = long_regime
    params["regime_type_short"] = short_regime

    name_prefix = "core15" if is_core_15m else "ichifib"
    name = f"{name_prefix}_{symbol}_{timeframe}_{random.randint(1000, 9999)}"

    strat = StrategyDefinition(
        name=name,
        symbol=symbol,
        timeframe=timeframe,
        long_entry_rule=long_entry_rule,
        short_entry_rule=short_entry_rule,
        exit_rule=exit_rule,
        stop_loss_pips=stop_loss_pips,
        take_profit_pips=take_profit_pips,
        params=params,
    )
    logger.info("Generated strategy %s", strat.to_dict())
    return strat


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
    strategies = []
    for _ in range(n):
        strategies.append(random_strategy(symbol, timeframe))
    return strategies


def generate_and_save_batch(symbol: str, timeframe: str, n: int) -> List[Path]:
    paths: List[Path] = []
    for strat in generate_batch(symbol, timeframe, n):
        paths.append(save_strategy(strat))
    return paths
