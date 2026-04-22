from __future__ import annotations

from ..logging_utils import get_logger

logger = get_logger(__name__)


def dynamic_spread_multiplier(*, news_delta_min: float, news_impact: int, vol_regime: str) -> float:
    """Approximate spread expansion under news proximity and high-vol regimes."""
    multiplier = 1.0
    delta = abs(float(news_delta_min))
    regime = str(vol_regime or "").lower()

    if news_impact >= 3 and delta < 30.0:
        multiplier = max(multiplier, 3.0 + (30.0 - delta) / 10.0)
    elif news_impact >= 2 and delta < 60.0:
        multiplier = max(multiplier, 1.5)

    if regime in {"high", "high_vol", "volatility_spike", "event_driven"}:
        multiplier *= 1.3

    return multiplier


def dynamic_slippage_multiplier(*, news_delta_min: float, news_impact: int, vol_regime: str) -> float:
    """Approximate adverse slippage expansion in stressed conditions."""
    multiplier = 1.0
    delta = abs(float(news_delta_min))
    regime = str(vol_regime or "").lower()

    if news_impact >= 3 and delta < 30.0:
        multiplier = max(multiplier, 2.5 + (30.0 - delta) / 20.0)
    elif news_impact >= 2 and delta < 60.0:
        multiplier = max(multiplier, 1.4)

    if regime in {"high", "high_vol", "volatility_spike", "event_driven"}:
        multiplier *= 1.25

    return multiplier


def apply_costs(
    direction: str,
    entry_price: float,
    exit_price: float,
    size: float,
    spread: float,
    commission_per_lot: float,
    slippage_pips: float,
    pip_size: float,
) -> float:
    """Apply transaction costs and return realized PnL in price * size terms.

    - direction: "long" or "short"
    - spread: price spread (in price units)
    - commission_per_lot: per-lot commission in account currency
    - slippage_pips: additional adverse movement in pips applied at entry & exit
    """
    # Adjust for slippage (adverse)
    slippage = slippage_pips * pip_size
    if direction == "long":
        effective_entry = entry_price + slippage
        effective_exit = exit_price - slippage
    else:
        effective_entry = entry_price - slippage
        effective_exit = exit_price + slippage

    if direction == "long":
        gross_pnl = (effective_exit - effective_entry) * size
    else:
        gross_pnl = (effective_entry - effective_exit) * size

    # Spread cost (once, approximate)
    spread_cost = spread * size

    # Commission cost
    lots = size  # simplification: treat size as lot-equivalent
    commission_cost = commission_per_lot * lots

    pnl_after_costs = gross_pnl - spread_cost - commission_cost
    logger.debug(
        "TX costs direction=%s, entry=%.5f, exit=%.5f, size=%.2f, spread=%.5f, slippage_pips=%.2f -> pnl=%.2f",
        direction,
        entry_price,
        exit_price,
        size,
        spread,
        slippage_pips,
        pnl_after_costs,
    )
    return pnl_after_costs
