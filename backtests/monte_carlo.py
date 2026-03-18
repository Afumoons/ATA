from __future__ import annotations

from typing import Dict, List

import numpy as np

from ..logging_utils import get_logger
from .engine import Trade

logger = get_logger(__name__)


def monte_carlo_pnl(
    trades: List[Trade],
    n_runs: int = 1000,
    slippage_std_pips: float = 0.0,
    pip_size: float = 0.0001,
) -> Dict[str, float]:
    """Monte Carlo stress test on a list of trades.

    - Randomizes trade order per run.
    - Applies random slippage (normal with std in pips) to each trade.
    - Returns distribution stats for final equity and max drawdown.
    """
    if not trades:
        return {}

    base_pnls = np.array([t.pnl for t in trades], dtype=float)
    n_trades = len(trades)

    final_equities = []
    max_drawdowns = []

    for _ in range(n_runs):
        order = np.random.permutation(n_trades)
        pnls = base_pnls[order].copy()

        if slippage_std_pips > 0:
            slippage = np.random.normal(loc=0.0, scale=slippage_std_pips, size=n_trades)
            # For simplicity, treat slippage as a direct PnL adjustment in price*size units
            pnls -= slippage * pip_size

        equity_curve = pnls.cumsum()
        final_equities.append(equity_curve[-1])

        running_max = np.maximum.accumulate(equity_curve)
        dd = equity_curve - running_max
        max_drawdowns.append(dd.min())

    final_equities = np.array(final_equities)
    max_drawdowns = np.array(max_drawdowns)

    stats = {
        "mc_final_equity_mean": float(final_equities.mean()),
        "mc_final_equity_p5": float(np.percentile(final_equities, 5)),
        "mc_final_equity_p95": float(np.percentile(final_equities, 95)),
        "mc_max_dd_mean": float(max_drawdowns.mean()),
        "mc_max_dd_p5": float(np.percentile(max_drawdowns, 5)),
        "mc_max_dd_p95": float(np.percentile(max_drawdowns, 95)),
    }

    logger.info(
        "Monte Carlo: runs=%d, final_eq_mean=%.2f, p5=%.2f, p95=%.2f, max_dd_mean=%.2f",
        n_runs,
        stats["mc_final_equity_mean"],
        stats["mc_final_equity_p5"],
        stats["mc_final_equity_p95"],
        stats["mc_max_dd_mean"],
    )

    return stats
