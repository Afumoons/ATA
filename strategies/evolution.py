from __future__ import annotations

import random
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Any, List, Tuple

from .base import StrategyDefinition
from .generator import (
    random_strategy,
    rebuild_strategy_from_params,
    save_strategy,
    load_strategy,
    CORE_M15_FAMILY_WEIGHTS,
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
    min_family_share: int = 2


DEFAULT_EVOL_CONFIG = EvolutionConfig()


def _mutate_params(params: Dict[str, Any]) -> Dict[str, Any]:
    p = params.copy()

    if "rsi_low" in p:
        p["rsi_low"] = max(5, min(40, p["rsi_low"] + random.randint(-5, 5)))
    if "rsi_high" in p:
        p["rsi_high"] = max(60, min(95, p["rsi_high"] + random.randint(-5, 5)))
    if "trend_min" in p:
        p["trend_min"] = round(
            max(_TREND_MIN_LOW, min(_TREND_MIN_HIGH, float(p["trend_min"]) + random.uniform(-0.05, 0.05))),
            3,
        )
    if "vol_max" in p:
        p["vol_max"] = round(max(0.001, min(2.5, float(p["vol_max"]) + random.uniform(-0.08, 0.08))), 3)
    if "vol_min" in p:
        p["vol_min"] = round(max(0.05, min(3.0, float(p["vol_min"]) + random.uniform(-0.12, 0.12))), 3)
    if "rsi_exit" in p:
        p["rsi_exit"] = max(30, min(70, int(p["rsi_exit"]) + random.randint(-5, 5)))
    if "trend_exit" in p:
        p["trend_exit"] = round(
            max(_TREND_EXIT_CLAMP_MIN, min(_TREND_EXIT_CLAMP_MAX, float(p["trend_exit"]) + random.uniform(-0.03, 0.03))),
            3,
        )
    if "sl_atr_mult" in p:
        p["sl_atr_mult"] = max(1.0, min(3.5, round(float(p["sl_atr_mult"]) + random.choice([-0.5, 0.0, 0.5]), 2)))
    if "tp_atr_mult" in p:
        p["tp_atr_mult"] = max(1.2, min(6.0, round(float(p["tp_atr_mult"]) + random.choice([-1.0, 0.0, 1.0]), 2)))
    if "stop_loss_pips" in p:
        p["stop_loss_pips"] = random.choice([40, 50, 75, 100, 150])
    if "take_profit_pips" in p:
        p["take_profit_pips"] = random.choice([50, 75, 100, 150, 200, 250])
    if "time_stop_bars" in p:
        p["time_stop_bars"] = random.choice([3, 4, 6, 8, 10, 12])
    if random.random() < 0.15:
        p["family"] = random.choice(list(CORE_M15_FAMILY_WEIGHTS.keys()))
        p["playbook_type"] = p["family"]

    return p


def _mutate_strategy(strat: StrategyDefinition) -> StrategyDefinition:
    mutated_params = _mutate_params(strat.params)
    return rebuild_strategy_from_params(
        symbol=strat.symbol,
        timeframe=strat.timeframe,
        params=mutated_params,
    )


def _crossover(a: StrategyDefinition, b: StrategyDefinition) -> StrategyDefinition:
    all_keys = set(a.params.keys()) | set(b.params.keys())
    child_params: Dict[str, Any] = {}

    for key in all_keys:
        if key in {
            "long_family", "short_family", "exit_family",
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

    if random.random() < 0.35:
        child_params["family"] = random.choice([
            str(a.params.get("family") or "ma_trend"),
            str(b.params.get("family") or "ma_trend"),
        ])
        child_params["playbook_type"] = child_params["family"]

    return rebuild_strategy_from_params(
        symbol=a.symbol,
        timeframe=a.timeframe,
        params=child_params,
    )


def _strategy_fingerprint(strat: StrategyDefinition) -> str:
    params = getattr(strat, "params", {}) or {}
    family = str(params.get("family") or params.get("playbook_type") or "unknown")
    return "|".join([
        family,
        str(strat.long_entry_rule or ""),
        str(strat.short_entry_rule or ""),
        str(strat.exit_rule or ""),
        str(getattr(strat, "sl_atr_mult", "")),
        str(getattr(strat, "tp_atr_mult", "")),
    ])


def _family_of(strat: StrategyDefinition) -> str:
    return str((getattr(strat, "params", {}) or {}).get("family") or "unknown")


def evolve_population(
    symbol: str,
    timeframe: str,
    scored_strategies: List[Tuple[StrategyDefinition, float]],
    cfg: EvolutionConfig = DEFAULT_EVOL_CONFIG,
) -> List[StrategyDefinition]:
    if not scored_strategies:
        families = list(CORE_M15_FAMILY_WEIGHTS.keys())
        seeded: List[StrategyDefinition] = []
        for family in families[: min(len(families), cfg.population_size)]:
            seeded.append(random_strategy(symbol, timeframe, family=family))
        while len(seeded) < cfg.population_size:
            seeded.append(random_strategy(symbol, timeframe))
        return seeded

    scored_strategies = sorted(scored_strategies, key=lambda x: x[1], reverse=True)
    elites_count = max(1, int(cfg.elite_frac * cfg.population_size))
    elites = [s for s, _ in scored_strategies[:elites_count]]

    new_pop: List[StrategyDefinition] = []
    seen_fingerprints: set = set()

    for strat in elites:
        fp = _strategy_fingerprint(strat)
        if fp not in seen_fingerprints:
            new_pop.append(strat)
            seen_fingerprints.add(fp)

    family_counts = Counter(_family_of(s) for s in new_pop)
    target_families = list(CORE_M15_FAMILY_WEIGHTS.keys()) if timeframe == "M15" else list(family_counts.keys())

    for family in target_families:
        while family_counts.get(family, 0) < cfg.min_family_share and len(new_pop) < cfg.population_size:
            candidate = random_strategy(symbol, timeframe, family=family)
            fp = _strategy_fingerprint(candidate)
            if fp in seen_fingerprints:
                break
            new_pop.append(candidate)
            seen_fingerprints.add(fp)
            family_counts[family] += 1

    max_attempts_per_slot = 12
    attempts = 0

    while len(new_pop) < cfg.population_size:
        attempts += 1
        underrepresented = [f for f in target_families if family_counts.get(f, 0) < cfg.min_family_share]
        forced_family = random.choice(underrepresented) if underrepresented else None
        r = random.random()

        if forced_family is not None and random.random() < 0.60:
            candidate = random_strategy(symbol, timeframe, family=forced_family)
        elif r < cfg.mutation_rate:
            parent = random.choice(elites)
            candidate = _mutate_strategy(parent)
        elif r < cfg.mutation_rate + cfg.crossover_rate:
            if len(elites) >= 2:
                p1, p2 = random.sample(elites, 2)
            else:
                p1 = p2 = elites[0]
            candidate = _crossover(p1, p2)
        else:
            candidate = random_strategy(symbol, timeframe, family=forced_family)

        fp = _strategy_fingerprint(candidate)
        if fp not in seen_fingerprints:
            new_pop.append(candidate)
            seen_fingerprints.add(fp)
            family_counts[_family_of(candidate)] += 1
            attempts = 0
        elif attempts >= max_attempts_per_slot:
            candidate = random_strategy(symbol, timeframe, family=forced_family)
            fp = _strategy_fingerprint(candidate)
            if fp not in seen_fingerprints:
                new_pop.append(candidate)
                seen_fingerprints.add(fp)
                family_counts[_family_of(candidate)] += 1
            attempts = 0
            logger.debug("Evolution: forced random strategy after %d failed unique attempts", max_attempts_per_slot)

    logger.info(
        "Evolution: generated %d unique strategies | family_mix=%s",
        len(new_pop),
        dict(Counter(_family_of(s) for s in new_pop)),
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
