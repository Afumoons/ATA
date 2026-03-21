from __future__ import annotations

import random
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Any, List, Tuple

from .base import StrategyDefinition
from .generator import (
    random_strategy,
    rebuild_strategy_from_params,
    save_strategy,
    load_strategy,
    _TREND_MIN_LOW,
    _TREND_MIN_HIGH,
    _TREND_EXIT_CLAMP_MIN,
    _TREND_EXIT_CLAMP_MAX,
)
from ..logging_utils import get_logger

logger = get_logger(__name__)

STRATEGY_DIR = Path(__file__).resolve().parent
GENERATED_DIR = STRATEGY_DIR / "generated"


@dataclass
class EvolutionConfig:
    population_size: int = 20
    elite_frac: float = 0.2
    mutation_rate: float = 0.4
    crossover_rate: float = 0.4


DEFAULT_EVOL_CONFIG = EvolutionConfig()


def _mutate_params(params: Dict[str, Any]) -> Dict[str, Any]:
    """Return a mutated copy of a params dict.

    All numeric fields are clamped to safe ranges aligned with the
    ATR-normalised trend_strength scale used in generator.py and regime.py.
    trend_exit is clamped to prevent unbounded drift across mutation cycles.
    """
    p = params.copy()

    if "rsi_low" in p:
        p["rsi_low"] = max(5, min(40, p["rsi_low"] + random.randint(-5, 5)))
    if "rsi_high" in p:
        p["rsi_high"] = max(60, min(95, p["rsi_high"] + random.randint(-5, 5)))
    if "trend_min" in p:
        p["trend_min"] = round(
            max(_TREND_MIN_LOW, min(_TREND_MIN_HIGH,
                float(p["trend_min"]) + random.uniform(-0.05, 0.05))),
            3,
        )
    if "vol_max" in p:
        p["vol_max"] = max(0.001, min(0.1,
            float(p["vol_max"]) + random.uniform(-0.005, 0.005)))
    if "rsi_exit" in p:
        p["rsi_exit"] = max(30, min(70, int(p["rsi_exit"]) + random.randint(-5, 5)))
    if "trend_exit" in p:
        # Clamp to prevent drift — without a bound, repeated mutation pushes
        # trend_exit far outside meaningful range after many cycles.
        p["trend_exit"] = round(
            max(_TREND_EXIT_CLAMP_MIN, min(_TREND_EXIT_CLAMP_MAX,
                float(p["trend_exit"]) + random.uniform(-0.03, 0.03))),
            3,
        )
    if "sl_atr_mult" in p:
        p["sl_atr_mult"] = random.choice([1.5, 2.0, 2.5])
    if "tp_atr_mult" in p:
        p["tp_atr_mult"] = random.choice([2.0, 3.0, 4.0])
    if "stop_loss_pips" in p:
        p["stop_loss_pips"] = random.choice([50, 75, 100, 150])
    if "take_profit_pips" in p:
        p["take_profit_pips"] = random.choice([50, 100, 150, 200])

    return p


def _mutate_strategy(strat: StrategyDefinition) -> StrategyDefinition:
    """Produce a mutated child from a parent strategy.

    Key fix: rules are RE-GENERATED from the mutated params so that the
    rule strings and params dict are always in sync. Previously,
    random_strategy() was called first (baking in random params) and then
    params were overwritten — leaving rules and params disconnected.
    """
    mutated_params = _mutate_params(strat.params)

    return rebuild_strategy_from_params(
        symbol=strat.symbol,
        timeframe=strat.timeframe,
        params=mutated_params,
    )


def _crossover(a: StrategyDefinition, b: StrategyDefinition) -> StrategyDefinition:
    """Produce a child by mixing params from two parent strategies.

    Key fix: after mixing params, rules are RE-GENERATED from the blended
    params so that rule strings and params are always in sync. Previously,
    random_strategy() baked in its own random params and then the parent
    params overwrote the dict — rules never reflected the parents at all.
    """
    all_keys = set(a.params.keys()) | set(b.params.keys())
    child_params: Dict[str, Any] = {}

    for key in all_keys:
        # Skip metadata fields — these will be set fresh by rebuild
        if key in {
            "long_family", "short_family",
            "regime_type_long", "regime_type_short", "regime_type",
        }:
            continue
        a_val = a.params.get(key)
        b_val = b.params.get(key)
        if a_val is None:
            child_params[key] = b_val
        elif b_val is None:
            child_params[key] = a_val
        else:
            child_params[key] = a_val if random.random() < 0.5 else b_val

    return rebuild_strategy_from_params(
        symbol=a.symbol,
        timeframe=a.timeframe,
        params=child_params,
    )


def _strategy_fingerprint(strat: StrategyDefinition) -> str:
    """Canonical fingerprint for deduplication.

    Two strategies are considered duplicates if they share the same
    long_entry_rule + short_entry_rule + exit_rule + sl_atr_mult + tp_atr_mult.
    This catches clones produced when crossover/mutation picks identical
    params from near-identical elite parents.
    """
    return "|".join([
        str(strat.long_entry_rule or ""),
        str(strat.short_entry_rule or ""),
        str(strat.exit_rule or ""),
        str(getattr(strat, "sl_atr_mult", "")),
        str(getattr(strat, "tp_atr_mult", "")),
    ])


def evolve_population(
    symbol: str,
    timeframe: str,
    scored_strategies: List[Tuple[StrategyDefinition, float]],
    cfg: EvolutionConfig = DEFAULT_EVOL_CONFIG,
) -> List[StrategyDefinition]:
    """Given existing strategies with scores, produce a new generation.

    Deduplication fix: tracks rule fingerprints to prevent identical
    strategies from filling the population. Crossover/mutation of similar
    elite parents frequently produces clones — without this guard, up to
    8/20 slots can be wasted on the same strategy evaluated redundantly.

    Falls back to random_strategy() if a unique candidate cannot be
    produced within max_attempts, ensuring the population is always full.
    """
    if not scored_strategies:
        return [random_strategy(symbol, timeframe) for _ in range(cfg.population_size)]

    scored_strategies = sorted(scored_strategies, key=lambda x: x[1], reverse=True)
    elites_count = max(1, int(cfg.elite_frac * cfg.population_size))
    elites = [s for s, _ in scored_strategies[:elites_count]]

    new_pop: List[StrategyDefinition] = []
    seen_fingerprints: set = set()

    # Carry elites forward, deduplicating even among them
    for strat in elites:
        fp = _strategy_fingerprint(strat)
        if fp not in seen_fingerprints:
            new_pop.append(strat)
            seen_fingerprints.add(fp)

    max_attempts_per_slot = 10  # avoid infinite loop if search space is exhausted
    attempts = 0

    while len(new_pop) < cfg.population_size:
        attempts += 1
        r = random.random()

        if r < cfg.mutation_rate:
            parent = random.choice(elites)
            candidate = _mutate_strategy(parent)
        elif r < cfg.mutation_rate + cfg.crossover_rate:
            if len(elites) >= 2:
                p1, p2 = random.sample(elites, 2)
            else:
                p1 = p2 = elites[0]
            candidate = _crossover(p1, p2)
        else:
            candidate = random_strategy(symbol, timeframe)

        fp = _strategy_fingerprint(candidate)
        if fp not in seen_fingerprints:
            new_pop.append(candidate)
            seen_fingerprints.add(fp)
            attempts = 0  # reset attempt counter on success
        elif attempts >= max_attempts_per_slot:
            # Can't find a unique variant — force a random strategy
            candidate = random_strategy(symbol, timeframe)
            fp = _strategy_fingerprint(candidate)
            new_pop.append(candidate)
            seen_fingerprints.add(fp)
            attempts = 0
            logger.debug(
                "Evolution: forced random strategy after %d failed unique attempts",
                max_attempts_per_slot,
            )

    logger.info(
        "Evolution: generated new population of %d unique strategies (elites=%d)",
        len(new_pop),
        len([s for s in new_pop if s in elites]),
    )
    return new_pop


def save_population(strategies: List[StrategyDefinition]) -> List[Path]:
    return [save_strategy(s) for s in strategies]


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