from __future__ import annotations

import random
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple

from .base import StrategyDefinition
from .generator import random_strategy, save_strategy, load_strategy
from ..logging_utils import get_logger

logger = get_logger(__name__)

STRATEGY_DIR = Path(__file__).resolve().parent
GENERATED_DIR = STRATEGY_DIR / "generated"


@dataclass
class EvolutionConfig:
    # Slightly larger, more exploratory population for discovery.
    population_size: int = 20
    elite_frac: float = 0.2
    mutation_rate: float = 0.4
    crossover_rate: float = 0.4


DEFAULT_EVOL_CONFIG = EvolutionConfig()


def _mutate_params(params: Dict) -> Dict:
    new_params = params.copy()
    if "rsi_low" in new_params:
        new_params["rsi_low"] = max(5, min(40, new_params["rsi_low"] + random.randint(-5, 5)))
    if "rsi_high" in new_params:
        new_params["rsi_high"] = max(60, min(95, new_params["rsi_high"] + random.randint(-5, 5)))
    if "trend_min" in new_params:
        new_params["trend_min"] = max(0.05, min(1.5, new_params["trend_min"] + random.uniform(-0.1, 0.1)))
    if "vol_max" in new_params:
        new_params["vol_max"] = max(0.001, min(0.1, new_params["vol_max"] + random.uniform(-0.005, 0.005)))
    if "rsi_exit" in new_params:
        new_params["rsi_exit"] = max(30, min(70, new_params["rsi_exit"] + random.randint(-5, 5)))
    if "trend_exit" in new_params:
        new_params["trend_exit"] += random.uniform(-0.05, 0.05)
    return new_params


def _mutate_strategy(strat: StrategyDefinition) -> StrategyDefinition:
    params = _mutate_params(strat.params)

    # Rebuild rules from templates by reusing generator; simpler than string surgery
    mutated = random_strategy(strat.symbol, strat.timeframe)
    mutated.params.update(params)
    return mutated


def _crossover(a: StrategyDefinition, b: StrategyDefinition) -> StrategyDefinition:
    child_params = {}
    for key in set(a.params.keys()) | set(b.params.keys()):
        if random.random() < 0.5:
            child_params[key] = a.params.get(key, b.params.get(key))
        else:
            child_params[key] = b.params.get(key, a.params.get(key))

    child = random_strategy(a.symbol, a.timeframe)
    child.params.update(child_params)
    return child


def evolve_population(
    symbol: str,
    timeframe: str,
    scored_strategies: List[Tuple[StrategyDefinition, float]],
    cfg: EvolutionConfig = DEFAULT_EVOL_CONFIG,
) -> List[StrategyDefinition]:
    """Given existing strategies with scores, produce a new generation.

    - scored_strategies: list of (strategy, score)
    """
    if not scored_strategies:
        # initialize fresh population
        return [random_strategy(symbol, timeframe) for _ in range(cfg.population_size)]

    scored_strategies = sorted(scored_strategies, key=lambda x: x[1], reverse=True)
    elites_count = max(1, int(cfg.elite_frac * cfg.population_size))
    elites = [s for s, _ in scored_strategies[:elites_count]]

    new_pop: List[StrategyDefinition] = []
    new_pop.extend(elites)

    while len(new_pop) < cfg.population_size:
        r = random.random()
        if r < cfg.mutation_rate:
            parent = random.choice(elites)
            new_pop.append(_mutate_strategy(parent))
        elif r < cfg.mutation_rate + cfg.crossover_rate:
            p1, p2 = random.sample(elites, 2) if len(elites) >= 2 else (elites[0], elites[0])
            new_pop.append(_crossover(p1, p2))
        else:
            new_pop.append(random_strategy(symbol, timeframe))

    logger.info(
        "Evolution: generated new population of %d strategies (elites=%d)",
        len(new_pop),
        elites_count,
    )
    return new_pop


def save_population(strategies: List[StrategyDefinition]) -> List[Path]:
    paths: List[Path] = []
    for s in strategies:
        paths.append(save_strategy(s))
    return paths


def load_population() -> List[StrategyDefinition]:
    if not GENERATED_DIR.exists():
        return []
    strategies: List[StrategyDefinition] = []
    for path in GENERATED_DIR.glob("*.json"):
        try:
            strategies.append(load_strategy(path))
        except Exception:
            logger.exception("Failed to load strategy file %s", path)
    return strategies
