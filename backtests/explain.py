from __future__ import annotations

from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from ..logging_utils import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def _safe_return_pct(pnl: float, initial_equity: float) -> float:
    if initial_equity <= 0:
        return 0.0
    return float(100.0 * pnl / initial_equity)


def _session_from_time(ts: pd.Timestamp) -> str:
    ts_utc = ts.tz_convert("UTC") if ts.tzinfo is not None else ts
    hour = ts_utc.hour
    if 0 <= hour < 7:
        return "asia"
    if 7 <= hour < 13:
        return "london"
    return "new_york"


def _compute_rr(row: pd.Series) -> Optional[float]:
    entry = float(row.get("entry_price", np.nan))
    sl = float(row.get("stop_loss", row.get("sl", np.nan)))
    tp = float(row.get("take_profit", row.get("tp", np.nan)))
    if not (np.isfinite(entry) and np.isfinite(sl) and np.isfinite(tp)):
        return None
    risk = abs(entry - sl)
    reward = abs(tp - entry)
    if risk <= 0:
        return None
    return reward / risk


def _infer_exit_type(row: pd.Series, pip_size: float) -> str:
    exit_price = float(row.get("exit_price", np.nan))
    sl = float(row.get("stop_loss", row.get("sl", np.nan)))
    tp = float(row.get("take_profit", row.get("tp", np.nan)))
    if not np.isfinite(exit_price):
        return "unknown"
    tol = 0.5 * pip_size
    if np.isfinite(sl) and abs(exit_price - sl) <= tol:
        return "SL"
    if np.isfinite(tp) and abs(exit_price - tp) <= tol:
        return "TP"
    return "RULE"


def _compute_sharpe(returns: np.ndarray) -> float:
    if returns.size < 2:
        return 0.0
    mu = returns.mean()
    sigma = returns.std(ddof=1)
    if sigma <= 0:
        return 0.0
    return float(mu / sigma * np.sqrt(returns.size))


def _nearest_feat_idx(feat_index: pd.DatetimeIndex, t: pd.Timestamp) -> int:
    """Return index of the last feature bar at or before time t.

    Replaces feat_index.get_loc(t, method='pad') which was deprecated in
    pandas 1.5 and removed in pandas 2.0. Uses get_indexer which is the
    supported replacement.
    """
    pos = feat_index.get_indexer([t], method="pad")[0]
    return int(pos)


# ---------------------------------------------------------------------------
# Main builder
# ---------------------------------------------------------------------------

def build_strategy_explain(
    trades: pd.DataFrame,
    features: pd.DataFrame,
    regime_column: str = "regime",
    initial_equity: Optional[float] = None,
    symbol: Optional[str] = None,
) -> Dict[str, Any]:
    """Construct structured explanation of a strategy's backtest behavior.

    Expected columns in `trades`:
        entry_time, exit_time          – datetime
        entry_price, exit_price        – float
        stop_loss (or sl), take_profit (or tp) – float
        pnl                            – float
        regime (optional)              – str

    Expected columns in `features`:
        time, regime_column            – required
        news_impact_level, news_time_delta_min, has_news_window – optional
    """
    _empty = {
        "regime_pnl": {},
        "session_pnl": {},
        "risk_behavior": {},
        "stability": {},
        "news_behavior": {},
        "meta": {},
    }
    if trades is None or trades.empty:
        return _empty

    if initial_equity is None or initial_equity <= 0:
        initial_equity = 10_000.0

    pip_size = 0.01 if symbol and ("XAU" in symbol or "XAG" in symbol) else 0.0001

    trades = trades.copy()
    trades["entry_time"] = pd.to_datetime(trades["entry_time"])
    trades["exit_time"] = pd.to_datetime(trades["exit_time"])
    trades = trades.sort_values("entry_time").reset_index(drop=True)

    feat = features.copy()
    feat["time"] = pd.to_datetime(feat["time"])
    feat = feat.sort_values("time").set_index("time")
    feat_index: pd.DatetimeIndex = feat.index

    has_regime_col = regime_column in feat.columns
    has_news_cols = (
        "news_impact_level" in feat.columns
        and "news_time_delta_min" in feat.columns
    )
    has_news_window_col = "has_news_window" in feat.columns

    # ------------------------------------------------------------------ #
    # Single pass: map each trade to its nearest feature row.             #
    # Compute all per-trade derived values in one loop — avoids iterating  #
    # trades multiple times and avoids storing pd.Series objects inside a  #
    # DataFrame column (which can cause subtle dtype/alignment issues).    #
    # ------------------------------------------------------------------ #
    regimes: List[str] = []
    sessions: List[str] = []
    exit_types: List[str] = []
    rr_values: List[Optional[float]] = []

    # News columns (filled only if news data available)
    news_impacts: List[float] = []
    news_deltas: List[float] = []

    pnl_col = trades["pnl"].values if "pnl" in trades.columns else np.zeros(len(trades))

    for i, row in trades.iterrows():
        et: pd.Timestamp = row["entry_time"]

        # Feature row at entry — use get_indexer (pandas 2.0-safe)
        feat_pos = _nearest_feat_idx(feat_index, et)
        if feat_pos < 0:
            feat_row = None
        else:
            feat_row = feat.iloc[feat_pos]

        # Regime
        if feat_row is not None and has_regime_col:
            regimes.append(str(feat_row[regime_column]))
        elif "regime" in row.index:
            regimes.append(str(row["regime"]))
        else:
            regimes.append("unknown")

        sessions.append(_session_from_time(et))
        exit_types.append(_infer_exit_type(row, pip_size))
        rr_values.append(_compute_rr(row))

        if has_news_cols and feat_row is not None:
            news_impacts.append(float(feat_row.get("news_impact_level", 0.0)))
            news_deltas.append(float(feat_row.get("news_time_delta_min", np.inf)))
        else:
            news_impacts.append(0.0)
            news_deltas.append(np.inf)

    trades["_regime"] = regimes
    trades["_session"] = sessions
    trades["_exit_type"] = exit_types
    trades["_rr"] = rr_values
    trades["_news_impact"] = news_impacts
    trades["_news_delta"] = news_deltas

    # ------------------------------------------------------------------ #
    # 1) Regime PnL                                                       #
    # ------------------------------------------------------------------ #
    regime_pnl: Dict[str, Dict[str, float]] = {}
    for regime_label, grp in trades.groupby("_regime"):
        pnl_vals = grp["pnl"].values.astype(float) if "pnl" in grp.columns else np.zeros(len(grp))
        pnl_sum = float(pnl_vals.sum())
        num = int(len(grp))
        wins = int((pnl_vals > 0).sum())
        win_rate = wins / num if num > 0 else 0.0
        # Bug fix: was calling _compute_rr twice per row (once for filter, once for value)
        rr_valid = [rr for rr in grp["_rr"].values if rr is not None]
        avg_rr = float(np.mean(rr_valid)) if rr_valid else 0.0
        regime_pnl[str(regime_label)] = {
            "return_pct": _safe_return_pct(pnl_sum, initial_equity),
            "net_profit": pnl_sum,
            "num_trades": num,
            "avg_rr": avg_rr,
            "win_rate": win_rate,
        }

    # ------------------------------------------------------------------ #
    # 2) Session PnL                                                      #
    # ------------------------------------------------------------------ #
    session_pnl: Dict[str, Dict[str, float]] = {}
    for sess_label, grp in trades.groupby("_session"):
        pnl_vals = grp["pnl"].values.astype(float) if "pnl" in grp.columns else np.zeros(len(grp))
        session_pnl[str(sess_label)] = {
            "return_pct": _safe_return_pct(float(pnl_vals.sum()), initial_equity),
            "num_trades": int(len(grp)),
        }

    # ------------------------------------------------------------------ #
    # 3) Risk behavior                                                    #
    # ------------------------------------------------------------------ #
    n_trades = len(trades)
    sl_hits = int((trades["_exit_type"] == "SL").sum())
    tp_hits = int((trades["_exit_type"] == "TP").sum())
    rule_exits = int((trades["_exit_type"] == "RULE").sum())

    rr_all = [rr for rr in trades["_rr"].values if rr is not None]

    # Holding bars: use searchsorted — O(log N) per trade, not O(N)
    holding_bars: List[int] = []
    feat_index_np = feat_index.view(np.int64)  # nanoseconds for fast comparison
    for _, row in trades.iterrows():
        et_ns = row["entry_time"].value
        xt_ns = row["exit_time"].value
        epos = int(np.searchsorted(feat_index_np, et_ns, side="right")) - 1
        xpos = int(np.searchsorted(feat_index_np, xt_ns, side="right")) - 1
        if epos >= 0 and xpos >= 0:
            holding_bars.append(max(0, xpos - epos))

    # Max consecutive losses
    max_consec = 0
    cur = 0
    pnl_sorted = trades["pnl"].values if "pnl" in trades.columns else np.zeros(n_trades)
    for pv in pnl_sorted:
        if float(pv) <= 0:
            cur += 1
            max_consec = max(max_consec, cur)
        else:
            cur = 0

    risk_behavior = {
        "avg_rr": float(np.mean(rr_all)) if rr_all else 0.0,
        "sl_hit_ratio": float(sl_hits / n_trades) if n_trades else 0.0,
        "tp_hit_ratio": float(tp_hits / n_trades) if n_trades else 0.0,
        "exit_rule_ratio": float(rule_exits / n_trades) if n_trades else 0.0,
        "avg_holding_bars": float(np.mean(holding_bars)) if holding_bars else 0.0,
        "max_consecutive_losses": int(max_consec),
    }

    # ------------------------------------------------------------------ #
    # 4) Stability (subperiod Sharpe)                                     #
    # ------------------------------------------------------------------ #
    n = len(trades)
    thirds = max(1, n // 3)
    segments = [
        trades.iloc[0:thirds],
        trades.iloc[thirds: 2 * thirds],
        trades.iloc[2 * thirds:],
    ]
    sub_sharpes: List[float] = []
    sub_returns: List[float] = []
    for seg in segments:
        if seg.empty or "pnl" not in seg.columns:
            sub_sharpes.append(0.0)
            sub_returns.append(0.0)
            continue
        rets = seg["pnl"].values.astype(float)
        sub_returns.append(_safe_return_pct(float(rets.sum()), initial_equity))
        sub_sharpes.append(_compute_sharpe(rets))

    stability = {
        "subperiod_sharpe": sub_sharpes,
        "subperiod_return_pct": sub_returns,
        "sharpe_std": float(np.std(sub_sharpes)) if len(sub_sharpes) > 1 else 0.0,
    }

    # ------------------------------------------------------------------ #
    # 5) News behavior                                                    #
    # ------------------------------------------------------------------ #
    news_behavior: Dict[str, Any] = {
        "trades_around_high_impact": {"num_trades": 0, "return_pct": 0.0, "avg_rr": 0.0},
        "avoidance_rate": 0.0,
        "pre_news_return_pct": 0.0,
        "post_news_return_pct": 0.0,
    }

    if has_news_cols:
        high_window = 30.0
        impact_arr = trades["_news_impact"].values.astype(float)
        delta_arr = trades["_news_delta"].values.astype(float)
        pnl_arr = trades["pnl"].values.astype(float) if "pnl" in trades.columns else np.zeros(n_trades)

        hi_mask = (impact_arr >= 3) & (np.abs(delta_arr) <= high_window)
        pre_mask = (impact_arr >= 2) & (delta_arr >= -60.0) & (delta_arr < 0.0)
        post_mask = (impact_arr >= 2) & (delta_arr >= 0.0) & (delta_arr <= 60.0)

        hi_pnl = float(pnl_arr[hi_mask].sum())
        hi_rr_vals = [rr for rr, flag in zip(trades["_rr"].values, hi_mask) if flag and rr is not None]

        news_behavior["trades_around_high_impact"] = {
            "num_trades": int(hi_mask.sum()),
            "return_pct": _safe_return_pct(hi_pnl, initial_equity),
            "avg_rr": float(np.mean(hi_rr_vals)) if hi_rr_vals else 0.0,
        }
        news_behavior["pre_news_return_pct"] = _safe_return_pct(
            float(pnl_arr[pre_mask].sum()), initial_equity
        )
        news_behavior["post_news_return_pct"] = _safe_return_pct(
            float(pnl_arr[post_mask].sum()), initial_equity
        )

        # Avoidance rate — vectorized, was O(high_bars * trades)
        # Bug fix: feat.get("col", default) on DataFrame returns Series or
        # scalar default — comparing scalar False with & operator on Series
        # would raise or produce wrong result. Use explicit column check.
        if has_news_window_col:
            high_bar_mask = (feat["news_impact_level"] >= 3) & feat["has_news_window"].astype(bool)
        else:
            high_bar_mask = feat["news_impact_level"] >= 3

        high_bar_times = feat.index[high_bar_mask]
        total_high_bars = len(high_bar_times)

        if total_high_bars > 0:
            trade_times_ns = trades["entry_time"].values.astype(np.int64)
            bar_times_ns = high_bar_times.view(np.int64)
            # One-hour tolerance in nanoseconds
            tol_ns = int(3_600 * 1e9)
            bars_with_trade = int(
                sum(
                    1
                    for bt_ns in bar_times_ns
                    if np.any(np.abs(trade_times_ns - bt_ns) <= tol_ns)
                )
            )
            news_behavior["avoidance_rate"] = float(
                max(0.0, min(1.0, 1.0 - bars_with_trade / total_high_bars))
            )

    # ------------------------------------------------------------------ #
    # 6) Meta summary                                                     #
    # ------------------------------------------------------------------ #
    best_regime = None
    worst_regime = None
    if regime_pnl:
        sorted_reg = sorted(regime_pnl.items(), key=lambda kv: kv[1]["return_pct"])
        worst_regime = sorted_reg[0][0]
        best_regime = sorted_reg[-1][0]

    trend_ret = (
        (regime_pnl.get("trending_up", {}) or {}).get("return_pct", 0.0)
        + (regime_pnl.get("trending_down", {}) or {}).get("return_pct", 0.0)
    )
    range_ret = float((regime_pnl.get("ranging", {}) or {}).get("return_pct", 0.0))

    meta = {
        "best_regime": best_regime,
        "worst_regime": worst_regime,
        "is_trend_follower": bool(trend_ret > 0),
        "is_range_trader": bool(range_ret > 0),
        "total_pnl": float(pnl_col.sum()),
        "total_return_pct": _safe_return_pct(float(pnl_col.sum()), initial_equity),
    }

    return {
        "regime_pnl": regime_pnl,
        "session_pnl": session_pnl,
        "risk_behavior": risk_behavior,
        "stability": stability,
        "news_behavior": news_behavior,
        "meta": meta,
    }