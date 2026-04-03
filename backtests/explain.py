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


def _derive_allowed_blocked_labels(
    perf_map: Dict[str, Dict[str, float]],
    min_allowed_ret: float = 1.5,
    blocked_ret: float = -4.0,
    min_trades: int = 8,
) -> tuple[list[str], list[str]]:
    allowed: list[str] = []
    blocked: list[str] = []
    for label, stats in (perf_map or {}).items():
        try:
            ret = float((stats or {}).get("return_pct", 0.0) or 0.0)
            trades = int((stats or {}).get("num_trades", 0) or 0)
        except Exception:
            continue
        if trades < min_trades:
            continue
        if ret >= min_allowed_ret:
            allowed.append(str(label))
        elif ret <= blocked_ret:
            blocked.append(str(label))
    return sorted(set(allowed)), sorted(set(blocked))


def _derive_routing_confidence(
    best_ret: float,
    worst_ret: float,
    total_trades: int,
    num_allowed: int = 0,
    num_blocked: int = 0,
) -> float:
    trade_score = min(1.0, max(0.0, total_trades / 80.0))
    spread = max(0.0, best_ret - worst_ret)
    separation_score = min(1.0, spread / 25.0)
    specialization_score = min(1.0, (num_allowed + num_blocked) / 4.0)
    leakage_penalty = 0.0
    if worst_ret <= -8.0:
        leakage_penalty += 0.20
    elif worst_ret <= -4.0:
        leakage_penalty += 0.10
    raw = (0.45 * trade_score) + (0.35 * separation_score) + (0.20 * specialization_score)
    return round(max(0.0, min(1.0, raw - leakage_penalty)), 4)


def _nearest_feat_idx(feat_index: pd.DatetimeIndex, t: pd.Timestamp) -> int:
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
    _empty = {
        "regime_pnl": {},
        "regime_class_pnl": {},
        "regime_type_pnl": {},
        "vol_regime_pnl": {},
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

    regimes: List[str] = []
    sessions: List[str] = []
    entry_regime_classes: List[str] = []
    entry_regime_types: List[str] = []
    vol_regimes: List[str] = []
    regime_confidences: List[float] = []
    exit_types: List[str] = []
    rr_values: List[Optional[float]] = []
    news_impacts: List[float] = []
    news_deltas: List[float] = []

    pnl_col = trades["pnl"].values if "pnl" in trades.columns else np.zeros(len(trades))

    for _, row in trades.iterrows():
        et: pd.Timestamp = row["entry_time"]
        feat_pos = _nearest_feat_idx(feat_index, et)
        feat_row = None if feat_pos < 0 else feat.iloc[feat_pos]

        if feat_row is not None and has_regime_col:
            regimes.append(str(feat_row[regime_column]))
        elif "regime" in row.index:
            regimes.append(str(row["regime"]))
        else:
            regimes.append("unknown")

        if feat_row is not None:
            entry_regime_classes.append(str(feat_row.get("regime_class", "unknown")))
            entry_regime_types.append(str(feat_row.get("regime_type", "unknown")))
            vol_regimes.append(str(feat_row.get("vol_regime", "unknown")))
            regime_confidences.append(float(feat_row.get("regime_confidence", 0.0) or 0.0))
        else:
            entry_regime_classes.append("unknown")
            entry_regime_types.append("unknown")
            vol_regimes.append("unknown")
            regime_confidences.append(0.0)

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
    trades["_entry_regime_class"] = entry_regime_classes
    trades["_entry_regime_type"] = entry_regime_types
    trades["_vol_regime"] = vol_regimes
    trades["_regime_confidence"] = regime_confidences
    trades["_exit_type"] = exit_types
    trades["_rr"] = rr_values
    trades["_news_impact"] = news_impacts
    trades["_news_delta"] = news_deltas

    regime_pnl: Dict[str, Dict[str, float]] = {}
    for regime_label, grp in trades.groupby("_regime"):
        pnl_vals = grp["pnl"].values.astype(float) if "pnl" in grp.columns else np.zeros(len(grp))
        pnl_sum = float(pnl_vals.sum())
        num = int(len(grp))
        wins = int((pnl_vals > 0).sum())
        win_rate = wins / num if num > 0 else 0.0
        rr_valid = [rr for rr in grp["_rr"].values if rr is not None]
        avg_rr = float(np.mean(rr_valid)) if rr_valid else 0.0
        regime_pnl[str(regime_label)] = {
            "return_pct": _safe_return_pct(pnl_sum, initial_equity),
            "net_profit": pnl_sum,
            "num_trades": num,
            "avg_rr": avg_rr,
            "win_rate": win_rate,
        }

    regime_class_pnl: Dict[str, Dict[str, float]] = {}
    for label, grp in trades.groupby("_entry_regime_class"):
        pnl_vals = grp["pnl"].values.astype(float) if "pnl" in grp.columns else np.zeros(len(grp))
        regime_class_pnl[str(label)] = {
            "return_pct": _safe_return_pct(float(pnl_vals.sum()), initial_equity),
            "num_trades": int(len(grp)),
        }

    regime_type_pnl: Dict[str, Dict[str, float]] = {}
    for label, grp in trades.groupby("_entry_regime_type"):
        pnl_vals = grp["pnl"].values.astype(float) if "pnl" in grp.columns else np.zeros(len(grp))
        regime_type_pnl[str(label)] = {
            "return_pct": _safe_return_pct(float(pnl_vals.sum()), initial_equity),
            "num_trades": int(len(grp)),
        }

    vol_regime_pnl: Dict[str, Dict[str, float]] = {}
    for label, grp in trades.groupby("_vol_regime"):
        pnl_vals = grp["pnl"].values.astype(float) if "pnl" in grp.columns else np.zeros(len(grp))
        vol_regime_pnl[str(label)] = {
            "return_pct": _safe_return_pct(float(pnl_vals.sum()), initial_equity),
            "num_trades": int(len(grp)),
        }

    session_pnl: Dict[str, Dict[str, float]] = {}
    for sess_label, grp in trades.groupby("_session"):
        pnl_vals = grp["pnl"].values.astype(float) if "pnl" in grp.columns else np.zeros(len(grp))
        session_pnl[str(sess_label)] = {
            "return_pct": _safe_return_pct(float(pnl_vals.sum()), initial_equity),
            "num_trades": int(len(grp)),
        }

    n_trades = len(trades)
    sl_hits = int((trades["_exit_type"] == "SL").sum())
    tp_hits = int((trades["_exit_type"] == "TP").sum())
    rule_exits = int((trades["_exit_type"] == "RULE").sum())
    rr_all = [rr for rr in trades["_rr"].values if rr is not None]

    holding_bars: List[int] = []
    for _, row in trades.iterrows():
        try:
            epos = _nearest_feat_idx(feat_index, row["entry_time"])
            xpos = _nearest_feat_idx(feat_index, row["exit_time"])
        except Exception:
            continue
        if epos >= 0 and xpos >= 0:
            holding_bars.append(max(0, xpos - epos))

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
        "median_holding_bars": float(np.median(holding_bars)) if holding_bars else 0.0,
        "max_holding_bars": int(max(holding_bars)) if holding_bars else 0,
        "max_consecutive_losses": int(max_consec),
    }

    n = len(trades)
    thirds = max(1, n // 3)
    segments = [trades.iloc[0:thirds], trades.iloc[thirds:2 * thirds], trades.iloc[2 * thirds:]]
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

    around_high = trades[(trades["_news_impact"] >= 3) & (np.abs(trades["_news_delta"]) <= 30)]
    high_trades = int(len(around_high))
    high_ret = float(around_high["pnl"].sum()) if high_trades else 0.0

    if has_news_window_col:
        window_rate = float(feat["has_news_window"].astype(bool).mean()) if len(feat) else 0.0
    else:
        window_rate = 0.0
    observed_high_rate = high_trades / max(1, n_trades)

    news_behavior = {
        "trades_around_high_impact": {
            "num_trades": high_trades,
            "return_pct": _safe_return_pct(high_ret, initial_equity),
        },
        "avoidance_rate": float(max(0.0, 1.0 - observed_high_rate / max(window_rate, 1e-6))) if window_rate > 0 else 0.0,
    }

    best_regime = None
    worst_regime = None
    best_regime_ret = 0.0
    worst_regime_ret = 0.0
    if regime_pnl:
        sorted_reg = sorted(regime_pnl.items(), key=lambda kv: kv[1]["return_pct"])
        worst_regime = sorted_reg[0][0]
        best_regime = sorted_reg[-1][0]
        worst_regime_ret = float((sorted_reg[0][1] or {}).get("return_pct", 0.0) or 0.0)
        best_regime_ret = float((sorted_reg[-1][1] or {}).get("return_pct", 0.0) or 0.0)

    best_session = None
    worst_session = None
    best_session_ret = 0.0
    worst_session_ret = 0.0
    if session_pnl:
        sorted_sess = sorted(session_pnl.items(), key=lambda kv: kv[1]["return_pct"])
        worst_session = sorted_sess[0][0]
        best_session = sorted_sess[-1][0]
        worst_session_ret = float((sorted_sess[0][1] or {}).get("return_pct", 0.0) or 0.0)
        best_session_ret = float((sorted_sess[-1][1] or {}).get("return_pct", 0.0) or 0.0)

    trend_ret = (
        (regime_pnl.get("trending_up", {}) or {}).get("return_pct", 0.0)
        + (regime_pnl.get("trending_down", {}) or {}).get("return_pct", 0.0)
    )
    range_ret = float((regime_pnl.get("ranging", {}) or {}).get("return_pct", 0.0))

    avg_regime_confidence = float(np.mean(regime_confidences)) if regime_confidences else 0.0
    allowed_regimes, blocked_regimes = _derive_allowed_blocked_labels(
        regime_pnl, min_allowed_ret=1.5, blocked_ret=-4.0, min_trades=8
    )
    allowed_sessions, blocked_sessions = _derive_allowed_blocked_labels(
        session_pnl, min_allowed_ret=0.75, blocked_ret=-2.0, min_trades=8
    )
    routing_confidence = _derive_routing_confidence(
        best_ret=best_regime_ret,
        worst_ret=worst_regime_ret,
        total_trades=n_trades,
        num_allowed=len(allowed_regimes) + len(allowed_sessions),
        num_blocked=len(blocked_regimes) + len(blocked_sessions),
    )
    specialist_score = round(min(1.0, max(0.0, 0.55 * routing_confidence + 0.45 * avg_regime_confidence)), 4)

    meta = {
        "best_regime": best_regime,
        "worst_regime": worst_regime,
        "best_session": best_session,
        "worst_session": worst_session,
        "best_regime_return_pct": best_regime_ret,
        "worst_regime_return_pct": worst_regime_ret,
        "best_session_return_pct": best_session_ret,
        "worst_session_return_pct": worst_session_ret,
        "allowed_regimes": allowed_regimes,
        "blocked_regimes": blocked_regimes,
        "allowed_sessions": allowed_sessions,
        "blocked_sessions": blocked_sessions,
        "routing_confidence": routing_confidence,
        "avg_regime_confidence": avg_regime_confidence,
        "specialist_score": specialist_score,
        "is_trend_follower": bool(trend_ret > 0),
        "is_range_trader": bool(range_ret > 0),
        "total_pnl": float(pnl_col.sum()),
        "total_return_pct": _safe_return_pct(float(pnl_col.sum()), initial_equity),
    }

    return {
        "regime_pnl": regime_pnl,
        "regime_class_pnl": regime_class_pnl,
        "regime_type_pnl": regime_type_pnl,
        "vol_regime_pnl": vol_regime_pnl,
        "session_pnl": session_pnl,
        "risk_behavior": risk_behavior,
        "stability": stability,
        "news_behavior": news_behavior,
        "meta": meta,
    }
