from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd

from ..logging_utils import get_logger
from ..strategies.base import StrategyDefinition
from .engine import run_backtest, BacktestResult

logger = get_logger(__name__)


@dataclass
class WalkForwardConfig:
    n_splits: int = 4
    train_ratio: float = 0.7  # fraction of each split used for train


def _split_walkforward_indices(n: int, n_splits: int, train_ratio: float) -> List[Tuple[int, int, int]]:
    """Return list of (train_start, train_end, test_end) indices for walk-forward.

    Assumes data is already time-ordered [0..n-1].
    """
    if n_splits < 1:
        raise ValueError("n_splits must be >= 1")

    fold_size = n // n_splits
    splits: List[Tuple[int, int, int]] = []

    for i in range(n_splits):
        start = i * fold_size
        end = (i + 1) * fold_size if i < n_splits - 1 else n
        length = end - start
        if length < 10:
            continue
        train_end = start + int(length * train_ratio)
        if train_end >= end:
            continue
        splits.append((start, train_end, end))

    return splits


def walk_forward_test(
    df: pd.DataFrame,
    strategy: StrategyDefinition,
    cfg: WalkForwardConfig | None = None,
    **backtest_kwargs,
) -> Dict:
    """Perform walk-forward validation.

    For now, strategy parameters are not re-optimized per window; this function
    simply runs backtests on each out-of-sample window and aggregates stats.
    """
    if cfg is None:
        cfg = WalkForwardConfig()

    df = df.sort_values("time").reset_index(drop=True)
    n = len(df)
    splits = _split_walkforward_indices(n, cfg.n_splits, cfg.train_ratio)

    if not splits:
        logger.warning("No valid walk-forward splits (n=%d, n_splits=%d)", n, cfg.n_splits)
        return {"windows": [], "aggregate": {}}

    windows: List[Dict] = []
    all_equity = []
    all_times = []

    for idx, (train_start, train_end, test_end) in enumerate(splits):
        train_df = df.iloc[train_start:train_end]
        test_df = df.iloc[train_end:test_end]

        logger.info(
            "Walk-forward window %d: train [%d:%d], test [%d:%d]",
            idx,
            train_start,
            train_end,
            train_end,
            test_end,
        )

        # In future we can tune strategy.params based on train_df.
        # For now we just backtest on test_df with the given strategy.
        if len(test_df) < 10:
            continue

        result: BacktestResult = run_backtest(test_df, strategy, **backtest_kwargs)
        windows.append(
            {
                "index": idx,
                "train_range": (int(train_start), int(train_end)),
                "test_range": (int(train_end), int(test_end)),
                "stats": result.stats,
            }
        )
        all_equity.append(result.equity_curve)
        all_times.append(result.equity_curve.index)

    if not windows:
        logger.warning("Walk-forward produced no test windows")
        return {"windows": [], "aggregate": {}}

    # Aggregate: concatenate equity curves aligned by time
    equity_cat = pd.concat(all_equity).sort_index()
    returns = equity_cat.pct_change().dropna()

    if not returns.empty:
        sharpe = float(np.sqrt(252) * returns.mean() / (returns.std() + 1e-9))
    else:
        sharpe = 0.0

    running_max = equity_cat.cummax()
    drawdowns = equity_cat / running_max - 1.0
    max_dd = float(drawdowns.min()) * 100.0

    aggregate = {
        "overall_sharpe": sharpe,
        "overall_max_drawdown_pct": max_dd,
        "num_windows": len(windows),
    }

    logger.info(
        "Walk-forward aggregate: windows=%d, sharpe=%.3f, max_dd=%.2f%%",
        len(windows),
        sharpe,
        max_dd,
    )

    return {"windows": windows, "aggregate": aggregate}
