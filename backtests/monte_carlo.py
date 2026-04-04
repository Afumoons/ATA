from __future__ import annotations

from typing import Dict, List

import numpy as np

from ..logging_utils import get_logger
from .engine import Trade

logger = get_logger(__name__)


def _random_permutation_indices(rng: np.random.Generator, n_runs: int, n_trades: int) -> np.ndarray:
    return np.argsort(rng.random((n_runs, n_trades)), axis=1)


def _block_bootstrap_indices(rng: np.random.Generator, n_runs: int, n_trades: int, block_size: int) -> np.ndarray:
    block = max(1, min(int(block_size), n_trades))
    out = np.empty((n_runs, n_trades), dtype=int)
    for run in range(n_runs):
        cursor = 0
        while cursor < n_trades:
            start = int(rng.integers(0, n_trades))
            take = min(block, n_trades - cursor)
            idx = (start + np.arange(take)) % n_trades
            out[run, cursor:cursor + take] = idx
            cursor += take
    return out


def monte_carlo_pnl(
    trades: List[Trade],
    n_runs: int = 1000,
    slippage_std_pips: float = 0.0,
    pip_size: float = 0.01,
    method: str = "shuffle",
    block_size: int = 5,
    seed: int | None = None,
    initial_equity: float = 10_000.0,
) -> Dict[str, float]:
    """Monte Carlo stress test on a list of Trade objects.

    Supported methods:
    - ``shuffle``: fully random trade reordering
    - ``block``: block bootstrap that preserves short local streak structure

    The intent is not to punish bounded specialists for being specialists.
    The goal is to surface sequence fragility more honestly, especially when
    losses cluster in adverse regimes/sessions.

    Returns
    -------
    dict with legacy keys preserved plus richer governance metrics:
        mc_final_pnl_mean / p5 / p95
        mc_max_dd_mean / p5 / p95
        mc_loss_prob
        mc_cvar_p5
        mc_dd_over_10pct_prob / mc_dd_over_20pct_prob
        mc_method / mc_block_size
    """
    if not trades:
        return {}

    rng = np.random.default_rng(seed)
    base_pnls = np.array([t.pnl for t in trades], dtype=float)
    sizes = np.array([float(getattr(t, "size", 1.0)) for t in trades], dtype=float)
    n_trades = len(trades)

    method_norm = str(method or "shuffle").strip().lower()
    if method_norm == "shuffle":
        indices = _random_permutation_indices(rng, n_runs, n_trades)
    elif method_norm in {"block", "block_bootstrap", "bootstrap_block"}:
        indices = _block_bootstrap_indices(rng, n_runs, n_trades, block_size)
        method_norm = "block"
    else:
        raise ValueError(f"Unsupported Monte Carlo method: {method}")

    pnls = base_pnls[indices]
    szs = sizes[indices]

    if slippage_std_pips > 0:
        slip_pips = rng.normal(loc=0.0, scale=slippage_std_pips, size=(n_runs, n_trades))
        pnls = pnls - slip_pips * pip_size * szs

    zeros = np.zeros((n_runs, 1), dtype=float)
    equity = np.concatenate([zeros, np.cumsum(pnls, axis=1)], axis=1)
    final_pnl = equity[:, -1]

    running_max = np.maximum.accumulate(equity, axis=1)
    drawdown = equity - running_max
    max_dd = np.abs(drawdown.min(axis=1))

    denom = max(float(initial_equity), 1.0)
    max_dd_pct = max_dd / denom * 100.0
    loss_prob = float(np.mean(final_pnl < 0.0))
    worst_tail = final_pnl[final_pnl <= np.percentile(final_pnl, 5)]
    cvar_p5 = float(worst_tail.mean()) if len(worst_tail) else float(np.percentile(final_pnl, 5))

    stats = {
        "mc_final_pnl_mean": float(final_pnl.mean()),
        "mc_final_pnl_p5": float(np.percentile(final_pnl, 5)),
        "mc_final_pnl_p95": float(np.percentile(final_pnl, 95)),
        "mc_max_dd_mean": float(max_dd.mean()),
        "mc_max_dd_p5": float(np.percentile(max_dd, 5)),
        "mc_max_dd_p95": float(np.percentile(max_dd, 95)),
        "mc_loss_prob": loss_prob,
        "mc_cvar_p5": cvar_p5,
        "mc_dd_over_10pct_prob": float(np.mean(max_dd_pct >= 10.0)),
        "mc_dd_over_20pct_prob": float(np.mean(max_dd_pct >= 20.0)),
        "mc_method": method_norm,
        "mc_block_size": float(max(1, min(int(block_size), n_trades))),
    }

    logger.info(
        "Monte Carlo (%s, %d runs, %d trades): final_pnl_mean=%.2f [p5=%.2f p95=%.2f] max_dd_mean=%.2f [p5=%.2f p95=%.2f] loss_prob=%.2f cvar_p5=%.2f",
        method_norm,
        n_runs,
        n_trades,
        stats["mc_final_pnl_mean"],
        stats["mc_final_pnl_p5"],
        stats["mc_final_pnl_p95"],
        stats["mc_max_dd_mean"],
        stats["mc_max_dd_p5"],
        stats["mc_max_dd_p95"],
        stats["mc_loss_prob"],
        stats["mc_cvar_p5"],
    )

    return stats
