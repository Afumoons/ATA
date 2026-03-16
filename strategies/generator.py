from __future__ import annotations

import json
import random
from pathlib import Path
from typing import List

from .base import StrategyDefinition
from ..logging_utils import get_logger

logger = get_logger(__name__)

STRATEGY_DIR = Path(__file__).resolve().parent
GENERATED_DIR = STRATEGY_DIR / "generated"
GENERATED_DIR.mkdir(exist_ok=True)


# Bias towards Ichimoku + Fibonacci-style structures
LONG_ENTRY_TEMPLATES = [
    # Ichimoku: bullish alignment above the cloud
    "tenkan_sen > kijun_sen and close > senkou_span_a and close > senkou_span_b",
    # Fib + trend
    "fib_zone_382 == 1 and trend_strength > {trend_min}",
]

SHORT_ENTRY_TEMPLATES = [
    # Ichimoku: bearish alignment below the cloud
    "tenkan_sen < kijun_sen and close < senkou_span_a and close < senkou_span_b",
    # Fib + trend
    "fib_zone_618 == 1 and trend_strength < -{trend_min}",
]

EXIT_TEMPLATES = [
    "rsi > {rsi_exit}",
    "rsi < {rsi_exit}",
    "trend_strength < {trend_exit}",
]


def random_strategy(symbol: str, timeframe: str) -> StrategyDefinition:
    """Generate a strategy config with Ichimoku/Fib-biased rules."""
    long_tpl = random.choice(LONG_ENTRY_TEMPLATES)
    short_tpl = random.choice(SHORT_ENTRY_TEMPLATES)
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

    name = f"ichifib_{symbol}_{timeframe}_{random.randint(1000, 9999)}"

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
