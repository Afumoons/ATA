from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from ..logging_utils import get_logger
from ..strategies.base import StrategyDefinition
from .engine import run_backtest, BacktestResult, _get_periods_per_year

logger = get_logger(__name__)


@dataclass
class WalkForwardConfig:
    n_splits: int = 6        # Tier 2: was 4 — more splits = more robust OOS estimate
    min_test_bars: int = 100 # Tier 2: was 50 — at least ~1 day of M15 bars per window


def _split_walkforward_indices(
    n: int,
    n_splits: int,
    min_test_bars: int = 100,
) -> List[Tuple[int, int, int]]:
    """Return (train_start, train_end, test_end) triples for expanding-window WF.

    Each split uses all data up to fold boundary i as training, and the
    subsequent fold_size bars as out-of-sample test. This ensures each test
    window is genuinely out-of-sample from all prior training.

    With 1950 bars and n_splits=6, fold_size ≈ 279 bars (~2.4 days M15).
    Each test window gets ~279 bars — materially larger than the earlier 4-split setup.
    """
    if n_splits < 1:
        raise ValueError("n_splits must be >= 1")

    splits: List[Tuple[int, int, int]] = []
    fold_size = n // (n_splits + 1)

    for i in range(1, n_splits + 1):
        test_end = min(n, (i + 1) * fold_size)
        test_start = i * fold_size
        test_len = test_end - test_start

        if test_len < min_test_bars:
            continue

        train_start = 0
        train_end = test_start

        if train_end - train_start < min_test_bars:
            continue

        splits.append((train_start, train_end, test_end))

    return splits


def walk_forward_test(
    df: pd.DataFrame,
    strategy: StrategyDefinition,
    cfg: Optional[WalkForwardConfig] = None,
    regime_column: str = "regime",
    **backtest_kwargs,
) -> Dict:
    """Perform walk-forward validation on out-of-sample windows.

    Tier 2 changes vs previous version:
    - n_splits default 4 → 6: more windows = more statistically robust OOS estimate
    - min_test_bars default 50 → 100: avoids near-empty windows on short datasets

    These changes together mean WF Sharpe is computed on materially more OOS data,
    making the threshold gate in scheduler/main.py more meaningful.

    Still uses chained equity curve (no boundary artifacts) and per-symbol
    periods_per_year for correct annualisation.
    """
    if cfg is None:
        cfg = WalkForwardConfig()

    df = df.sort_values("time").reset_index(drop=True)
    n = len(df)

    splits = _split_walkforward_indices(
        n, cfg.n_splits, cfg.min_test_bars
    )

    if not splits:
        logger.warning(
            "No valid walk-forward splits for %s (n=%d n_splits=%d)",
            strategy.name, n, cfg.n_splits,
        )
        return {"windows": [], "aggregate": {}}

    windows: List[Dict] = []

    initial_equity = float(backtest_kwargs.get("initial_equity", 10_000.0))
    chained_equity: List[float] = [initial_equity]
    chained_times: List[pd.Timestamp] = []

    for idx, (train_start, train_end, test_end) in enumerate(splits):
        test_df = df.iloc[train_end:test_end].copy()

        if len(test_df) < cfg.min_test_bars:
            continue

        logger.info(
            "WF window %d/%d: train [%d:%d] test [%d:%d] (%d bars)",
            idx + 1, len(splits),
            train_start, train_end,
            train_end, test_end,
            len(test_df),
        )

        result: BacktestResult = run_backtest(
            test_df,
            strategy,
            regime_column=regime_column,
            **backtest_kwargs,
        )

        windows.append({
            "index": idx,
            "train_range": (int(train_start), int(train_end)),
            "test_range": (int(train_end), int(test_end)),
            "stats": result.stats,
        })

        wf_eq = result.equity_curve
        if len(wf_eq) < 2:
            continue

        wf_start = float(wf_eq.iloc[0])
        if wf_start <= 0:
            continue

        scale = chained_equity[-1] / wf_start
        for ts, ev in zip(wf_eq.index[1:], wf_eq.values[1:]):
            chained_equity.append(float(ev) * scale)
            chained_times.append(ts)

    if not windows:
        logger.warning("Walk-forward produced no valid test windows for %s", strategy.name)
        return {"windows": [], "aggregate": {}}

    if len(chained_equity) < 2 or not chained_times:
        aggregate = {
            "overall_sharpe": 0.0,
            "overall_max_drawdown_pct": 0.0,
            "num_windows": len(windows),
        }
    else:
        eq_series = pd.Series(
            chained_equity[1:],
            index=pd.DatetimeIndex(chained_times),
        )
        returns = eq_series.pct_change().dropna()

        ppy = _get_periods_per_year(strategy.symbol, strategy.timeframe)
        sharpe = (
            float(np.sqrt(ppy) * returns.mean() / (returns.std() + 1e-9))
            if not returns.empty
            else 0.0
        )

        running_max = eq_series.cummax()
        max_dd_pct = float(abs((eq_series / running_max - 1.0).min()) * 100.0)

        aggregate = {
            "overall_sharpe": sharpe,
            "overall_max_drawdown_pct": max_dd_pct,
            "num_windows": len(windows),
        }

    logger.info(
        "Walk-forward complete for %s: windows=%d sharpe=%.3f max_dd=%.2f%%",
        strategy.name,
        aggregate.get("num_windows", 0),
        aggregate.get("overall_sharpe", 0.0),
        aggregate.get("overall_max_drawdown_pct", 0.0),
    )

    return {"windows": windows, "aggregate": aggregate}