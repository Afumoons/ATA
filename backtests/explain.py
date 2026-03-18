from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Any

import numpy as np
import pandas as pd

from ..logging_utils import get_logger

logger = get_logger(__name__)


def _safe_return_pct(pnl: float, initial_equity: float) -> float:
    if initial_equity <= 0:
        return 0.0
    return float(100.0 * pnl / initial_equity)


def _session_from_time(ts: pd.Timestamp) -> str:
    ts = ts.tz_convert("UTC") if ts.tzinfo is not None else ts
    hour = ts.hour
    if 0 <= hour < 7:
        return "asia"
    if 7 <= hour < 13:
        return "london"
    return "new_york"


def _compute_rr(row: pd.Series) -> float | None:
    entry = float(row.get("entry_price", np.nan))
    sl = float(row.get("sl", np.nan))
    tp = float(row.get("tp", np.nan))
    if not np.isfinite(entry) or not np.isfinite(sl) or not np.isfinite(tp):
        return None
    risk = abs(entry - sl)
    reward = abs(tp - entry)
    if risk <= 0:
        return None
    return reward / risk


def _infer_exit_type(row: pd.Series, pip_size: float) -> str:
    exit_price = float(row.get("exit_price", np.nan))
    sl = float(row.get("sl", np.nan))
    tp = float(row.get("tp", np.nan))
    if not np.isfinite(exit_price):
        return "unknown"
    tol = 0.5 * pip_size
    if np.isfinite(sl) and abs(exit_price - sl) <= tol:
        return "SL"
    if np.isfinite(tp) and abs(exit_price - tp) <= tol:
        return "TP"
    return "RULE"


def _compute_sharpe(returns: np.ndarray) -> float:
    if returns.size == 0:
        return 0.0
    mu = returns.mean()
    sigma = returns.std(ddof=1)
    if sigma <= 0:
        return 0.0
    # scale by sqrt(n) to approximate period Sharpe
    return float(mu / sigma * np.sqrt(returns.size))


def build_strategy_explain(
    trades: pd.DataFrame,
    features: pd.DataFrame,
    regime_column: str = "regime",
    initial_equity: float | None = None,
    symbol: str | None = None,
) -> Dict[str, Any]:
    """Construct structured explanation of a strategy's behavior.

    This expects `trades` to contain at least:
    - entry_time, exit_time (datetime64[ns])
    - entry_price, exit_price, sl, tp (floats)
    - pnl (float)

    And `features` to contain:
    - time (datetime64[ns])
    - regime_column
    - optional news_* columns.
    """
    if trades is None or trades.empty:
        return {
            "regime_pnl": {},
            "session_pnl": {},
            "risk_behavior": {},
            "stability": {},
            "news_behavior": {},
            "meta": {},
        }

    trades = trades.copy()
    trades["entry_time"] = pd.to_datetime(trades["entry_time"])
    trades["exit_time"] = pd.to_datetime(trades["exit_time"])

    feat = features.copy()
    feat["time"] = pd.to_datetime(feat["time"])
    feat = feat.sort_values("time").set_index("time")

    # Infer pip size heuristically (XAU vs FX); can be improved later.
    if symbol and ("XAU" in symbol or "XAG" in symbol):
        pip_size = 0.01
    else:
        pip_size = 0.0001

    # Map each trade to nearest feature row at entry
    entry_rows = []
    for t in trades["entry_time"]:
        try:
            row = feat.loc[:t].iloc[-1]
        except Exception:
            entry_rows.append(None)
        else:
            entry_rows.append(row)

    trades["_entry_row"] = entry_rows

    # Precompute RR, exit type, session
    rr_list: list[float] = []
    exit_types: list[str] = []
    sessions: list[str] = []
    regimes: list[str] = []

    for i, row in trades.iterrows():
        rr = _compute_rr(row)
        if rr is not None:
            rr_list.append(rr)
        exit_types.append(_infer_exit_type(row, pip_size))
        sessions.append(_session_from_time(row["entry_time"]))

        er = row["_entry_row"]
        if er is None or regime_column not in er.index:
            regimes.append("unknown")
        else:
            regimes.append(str(er[regime_column]))

    trades["_session"] = sessions
    trades["_regime"] = regimes
    trades["_exit_type"] = exit_types

    total_pnl = float(trades["pnl"].sum()) if "pnl" in trades.columns else 0.0
    if initial_equity is None:
        initial_equity = 10000.0

    # 1) Regime PnL
    regime_pnl: Dict[str, Dict[str, float]] = {}
    for regime, grp in trades.groupby("_regime"):
        pnl_sum = float(grp["pnl"].sum()) if "pnl" in grp.columns else 0.0
        num = int(len(grp))
        wins = int((grp["pnl"] > 0).sum()) if "pnl" in grp.columns else 0
        win_rate = float(wins / num) if num > 0 else 0.0
        rr_vals = [
            _compute_rr(r) for _, r in grp.iterrows()
            if _compute_rr(r) is not None
        ]
        avg_rr = float(np.mean(rr_vals)) if rr_vals else 0.0
        regime_pnl[str(regime)] = {
            "return_pct": _safe_return_pct(pnl_sum, initial_equity),
            "net_profit": pnl_sum,
            "num_trades": num,
            "avg_rr": avg_rr,
            "win_rate": win_rate,
        }

    # 2) Session PnL
    session_pnl: Dict[str, Dict[str, float]] = {}
    for sess, grp in trades.groupby("_session"):
        pnl_sum = float(grp["pnl"].sum()) if "pnl" in grp.columns else 0.0
        num = int(len(grp))
        session_pnl[str(sess)] = {
            "return_pct": _safe_return_pct(pnl_sum, initial_equity),
            "num_trades": num,
        }

    # 3) Risk behavior
    n_trades = len(trades)
    sl_hits = sum(1 for t in exit_types if t == "SL")
    tp_hits = sum(1 for t in exit_types if t == "TP")
    rule_exits = sum(1 for t in exit_types if t == "RULE")

    sl_hit_ratio = sl_hits / n_trades if n_trades > 0 else 0.0
    tp_hit_ratio = tp_hits / n_trades if n_trades > 0 else 0.0
    exit_rule_ratio = rule_exits / n_trades if n_trades > 0 else 0.0

    # Holding bars: approximate by index distance
    holding_bars: list[int] = []
    feat_index = feat.index
    for _, row in trades.iterrows():
        et = row["entry_time"]
        xt = row["exit_time"]
        try:
            epos = feat_index.get_loc(max(feat_index[0], min(et, feat_index[-1])), method="pad")
            xpos = feat_index.get_loc(max(feat_index[0], min(xt, feat_index[-1])), method="pad")
            holding_bars.append(int(xpos) - int(epos))
        except Exception:
            continue

    avg_holding_bars = float(np.mean(holding_bars)) if holding_bars else 0.0

    # Max consecutive losses
    max_consec = 0
    cur = 0
    for pnl in trades.sort_values("entry_time")["pnl" if "pnl" in trades.columns else []]:
        if pnl <= 0:
            cur += 1
            max_consec = max(max_consec, cur)
        else:
            cur = 0

    risk_behavior = {
        "avg_rr": float(np.mean(rr_list)) if rr_list else 0.0,
        "sl_hit_ratio": float(sl_hit_ratio),
        "tp_hit_ratio": float(tp_hit_ratio),
        "exit_rule_ratio": float(exit_rule_ratio),
        "avg_holding_bars": avg_holding_bars,
        "max_consecutive_losses": int(max_consec),
    }

    # 4) Stability
    trades_sorted = trades.sort_values("entry_time")
    n = len(trades_sorted)
    thirds = max(1, n // 3)
    segments = [
        trades_sorted.iloc[0:thirds],
        trades_sorted.iloc[thirds:2 * thirds],
        trades_sorted.iloc[2 * thirds :],
    ]
    sub_sharpes: list[float] = []
    sub_returns: list[float] = []
    for seg in segments:
        if seg.empty or "pnl" not in seg.columns:
            sub_sharpes.append(0.0)
            sub_returns.append(0.0)
            continue
        rets = seg["pnl"].values
        sub_returns.append(_safe_return_pct(float(rets.sum()), initial_equity))
        sub_sharpes.append(_compute_sharpe(rets.astype(float)))

    sharpe_std = float(np.std(sub_sharpes)) if sub_sharpes else 0.0
    stability = {
        "subperiod_sharpe": sub_sharpes,
        "subperiod_return_pct": sub_returns,
        "sharpe_std": sharpe_std,
    }

    # 5) News behavior (optional)
    news_behavior: Dict[str, Any] = {
        "trades_around_high_impact": {
            "num_trades": 0,
            "return_pct": 0.0,
            "avg_rr": 0.0,
        },
        "avoidance_rate": 0.0,
        "pre_news_return_pct": 0.0,
        "post_news_return_pct": 0.0,
    }

    if "news_impact_level" in feat.columns and "news_time_delta_min" in feat.columns:
        high_window = 30.0

        # Map entry rows again with news columns
        news_rows = []
        for t in trades["entry_time"]:
            try:
                row = feat.loc[:t].iloc[-1]
            except Exception:
                news_rows.append(None)
            else:
                news_rows.append(row)

        trades["_news_row"] = news_rows

        hi_mask = []
        pre_mask = []
        post_mask = []
        hi_rr: list[float] = []
        hi_pnls: list[float] = []
        pre_pnls: list[float] = []
        post_pnls: list[float] = []

        for _, row in trades.iterrows():
            nr = row["_news_row"]
            if nr is None:
                hi_mask.append(False)
                pre_mask.append(False)
                post_mask.append(False)
                continue
            impact = float(nr.get("news_impact_level", 0.0))
            delta = float(nr.get("news_time_delta_min", np.inf))
            pnl = float(row.get("pnl", 0.0))
            rr = _compute_rr(row)

            is_hi = impact >= 3 and abs(delta) <= high_window
            is_pre = impact >= 2 and (-60.0 <= delta < 0.0)
            is_post = impact >= 2 and (0.0 <= delta <= 60.0)

            hi_mask.append(is_hi)
            pre_mask.append(is_pre)
            post_mask.append(is_post)

            if is_hi:
                hi_pnls.append(pnl)
                if rr is not None:
                    hi_rr.append(rr)
            if is_pre:
                pre_pnls.append(pnl)
            if is_post:
                post_pnls.append(pnl)

        hi_count = sum(hi_mask)
        news_behavior["trades_around_high_impact"] = {
            "num_trades": int(hi_count),
            "return_pct": _safe_return_pct(float(sum(hi_pnls)), initial_equity),
            "avg_rr": float(np.mean(hi_rr)) if hi_rr else 0.0,
        }

        news_behavior["pre_news_return_pct"] = _safe_return_pct(float(sum(pre_pnls)), initial_equity)
        news_behavior["post_news_return_pct"] = _safe_return_pct(float(sum(post_pnls)), initial_equity)

        # Avoidance rate: fraction of high-impact bars where no trade was opened
        high_bars = feat[(feat.get("news_impact_level", 0) >= 3) & (feat.get("has_news_window", False))]
        total_high_bars = len(high_bars)
        if total_high_bars > 0:
            # Rough approximation: a bar has trade if any entry_time falls within that bar's [time, next_time)
            bar_times = high_bars.index
            trade_times = trades["entry_time"].values
            bars_with_trade = 0
            for bt in bar_times:
                # assume timeframe regular; we just check exact time match / nearest <= window
                has_trade = any(abs((tt - bt).item() / 1e9) <= 60 * 60 for tt in trade_times)  # within 1h
                if has_trade:
                    bars_with_trade += 1
            news_behavior["avoidance_rate"] = float(
                max(0.0, min(1.0, 1.0 - bars_with_trade / total_high_bars))
            )

    # 6) Meta
    best_regime = None
    worst_regime = None
    if regime_pnl:
        sorted_reg = sorted(regime_pnl.items(), key=lambda kv: kv[1]["return_pct"])
        worst_regime = sorted_reg[0][0]
        best_regime = sorted_reg[-1][0]

    trend_ret = 0.0
    range_ret = 0.0
    if "trending_up" in regime_pnl:
        trend_ret += regime_pnl["trending_up"]["return_pct"]
    if "trending_down" in regime_pnl:
        trend_ret += regime_pnl["trending_down"]["return_pct"]
    if "ranging" in regime_pnl:
        range_ret = regime_pnl["ranging"]["return_pct"]

    meta = {
        "best_regime": best_regime,
        "worst_regime": worst_regime,
        "is_trend_follower": trend_ret > 0,
        "is_range_trader": range_ret > 0,
    }

    return {
        "regime_pnl": regime_pnl,
        "session_pnl": session_pnl,
        "risk_behavior": risk_behavior,
        "stability": stability,
        "news_behavior": news_behavior,
        "meta": meta,
    }
