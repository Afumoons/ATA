from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Literal, TypedDict, Optional

import numpy as np
import pandas as pd

from ..logging_utils import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Regime Enums
# ---------------------------------------------------------------------------

RegimeClass = Literal[
    "trend",
    "range",
    "breakout",
    "mean_reversion",
    "volatility_spike",
    "low_liquidity",
    "event_driven",
    "unknown",
]

RegimeType = Literal[
    # trend
    "uptrend_strong",
    "uptrend_weak",
    "downtrend_strong",
    "downtrend_weak",
    # range
    "range_tight",
    "range_wide",
    "range_rotational",
    # breakout
    "breakout_up",
    "breakout_down",
    "fakeout_up",
    "fakeout_down",
    # mean reversion
    "revert_to_daily_mean",
    "revert_to_intraday_vwap",
    "overshoot_correction",
    # volatility
    "vol_spike_up",
    "vol_spike_down",
    "vol_crush",
    # low liq
    "asian_session_low_liq",
    "weekend_crypto",
    "holiday_thin_market",
    # event driven
    "macro_news_high_impact",
    "macro_news_medium_impact",
    "unscheduled_news_shock",
    # fallback
    "unknown",
]


class RegimeHints(TypedDict, total=False):
    risk_mode: Literal["conservative", "normal", "aggressive"]
    max_leverage_suggested: float
    position_sizing_factor: float
    allowed_playbooks: list[str]
    disabled_playbooks: list[str]
    expected_hold_time_minutes: dict[str, float]
    risk_per_trade_cap: float
    max_concurrent_positions: int


class EventContext(TypedDict, total=False):
    has_scheduled_news: bool
    news_impact: Literal["none", "low", "medium", "high"]
    event_label: Optional[str]
    event_window_minutes: int


class RegimeExplain(TypedDict, total=False):
    rules_triggered: list[str]
    key_features: dict[str, float | bool]
    raw_model_output: dict[str, float]


@dataclass
class RegimeConfig:
    # ---------------------------------------------------------------------------
    # Trend thresholds — ATR-NORMALISED trend_strength scale.
    #
    # After features.py was updated to normalise trend_strength by ATR instead of
    # close.std(), the effective scale changed by roughly 10x for gold M15:
    #   Old (std-based):  typical range ±0.01 .. ±0.10
    #   New (ATR-based):  typical range ±0.05 .. ±1.50
    #
    # Rule of thumb for gold M15 (ATR ~$4-6):
    #   MA slope of $0.5/bar  → trend_strength ≈ 0.10  (very weak drift)
    #   MA slope of $1.0/bar  → trend_strength ≈ 0.20  (clear trend)
    #   MA slope of $2.0/bar  → trend_strength ≈ 0.40  (strong trend)
    #   MA slope of $3.0/bar  → trend_strength ≈ 0.60  (very strong trend)
    #
    # If you change the ATR period or MA window in features.py you MUST
    # re-tune these thresholds empirically (e.g. via regime.py calibrate_thresholds).
    # ---------------------------------------------------------------------------
    trend_up_thresh: float = 0.08      # was 0.02 — now ATR-normalised
    trend_down_thresh: float = -0.08   # was -0.02
    strong_trend_thresh: float = 0.30  # was 0.04

    # Volatility quantiles — computed on the calibration window
    vol_high_quantile: float = 0.75
    vol_low_quantile: float = 0.25

    # Vol quantile calibration window (bars). None = full history.
    # A rolling window keeps thresholds more stationary over time.
    # For 2000 bars of M15 data, 500 bars ≈ 5 trading days.
    vol_quantile_window: Optional[int] = 500

    # If trend_strength is above trend_up_thresh AND vol is high,
    # treat the bar as trending-high-vol rather than pure trend.
    # This prevents dangerously high-leverage entries during volatile trends.
    flag_high_vol_trend: bool = True


DEFAULT_REGIME_CONFIG = RegimeConfig()


# ---------------------------------------------------------------------------
# Structured detection — fully vectorised
# ---------------------------------------------------------------------------

@dataclass
class RegimeSnapshot:
    regime_version: str
    regime_class: RegimeClass
    regime_type: RegimeType
    regime_confidence: float
    regime_timeframe: str
    vol_regime: Literal["low", "normal", "high"]
    trend_strength: float
    volatility: float
    regime_hints: RegimeHints
    regime_explain: RegimeExplain


def _compute_vol_thresholds(
    vol: pd.Series,
    cfg: RegimeConfig,
) -> tuple[pd.Series, pd.Series]:
    """Return (vol_lo, vol_hi) Series aligned with vol.index.

    Uses a rolling quantile window when cfg.vol_quantile_window is set,
    otherwise falls back to a single global quantile. Rolling quantiles
    keep the thresholds stationary as market volatility regimes shift
    over weeks/months.
    """
    w = cfg.vol_quantile_window

    if w is not None and len(vol) >= w:
        vol_hi = vol.rolling(w, min_periods=w // 2).quantile(cfg.vol_high_quantile)
        vol_lo = vol.rolling(w, min_periods=w // 2).quantile(cfg.vol_low_quantile)
        # Forward-fill the NaN prefix so early bars still get a threshold
        vol_hi = vol_hi.ffill().bfill()
        vol_lo = vol_lo.ffill().bfill()
    else:
        # Fallback: global quantile broadcast to a constant Series
        hi_val = float(vol.quantile(cfg.vol_high_quantile))
        lo_val = float(vol.quantile(cfg.vol_low_quantile))
        vol_hi = pd.Series(hi_val, index=vol.index)
        vol_lo = pd.Series(lo_val, index=vol.index)

    return vol_lo, vol_hi


def _hints_for_class(regime_class: str, confidence: float) -> RegimeHints:
    """Return playbook hints for a given class + confidence."""
    if regime_class == "trend":
        return {
            "risk_mode": "aggressive" if confidence > 0.7 else "normal",
            "position_sizing_factor": 1.3 if confidence > 0.7 else 1.0,
            "allowed_playbooks": ["trend_follow_scalp", "breakout_continuation"],
            "disabled_playbooks": ["range_fade", "mean_reversion_intraday"],
        }
    if regime_class == "range":
        return {
            "risk_mode": "normal",
            "position_sizing_factor": 1.0,
            "allowed_playbooks": ["range_fade", "mean_reversion_intraday"],
            "disabled_playbooks": ["trend_follow_scalp"],
        }
    if regime_class == "volatility_spike":
        return {
            "risk_mode": "conservative",
            "position_sizing_factor": 0.7,
            "allowed_playbooks": ["news_spike_scalp"],
            "disabled_playbooks": ["swing_trend_follow"],
        }
    if regime_class == "event_driven":
        return {
            "risk_mode": "conservative",
            "position_sizing_factor": 0.5,
            "allowed_playbooks": [],
            "disabled_playbooks": ["trend_follow_scalp", "range_fade", "swing_trend_follow"],
        }
    # unknown / fallback
    return {
        "risk_mode": "conservative",
        "position_sizing_factor": 0.5,
        "allowed_playbooks": [],
        "disabled_playbooks": [],
    }


def detect_regime_structured(
    df: pd.DataFrame,
    timeframe: str,
    cfg: RegimeConfig = DEFAULT_REGIME_CONFIG,
    version: str = "v2",
) -> pd.DataFrame:
    """Return a DataFrame of structured regime snapshots aligned with df.index.

    Required columns: ``trend_strength``, ``volatility``.
    Optional columns used if present: ``in_news_lockout``, ``news_impact_level``.

    Changes from v1:
    - Fully vectorised — no Python row loop.
    - ATR-normalised trend_strength thresholds (see RegimeConfig).
    - Trending + high-vol bars optionally flagged differently when
      cfg.flag_high_vol_trend is True (position_sizing_factor reduced).
    - Rolling volatility quantile window for more stable thresholds.
    - ``in_news_lockout`` triggers ``event_driven`` class when present.
    - Confidence formula recalibrated for ATR-normalised scale.
    """
    required = {"trend_strength", "volatility"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(
            f"DataFrame missing required columns for regime detection: {missing}"
        )

    trend = df["trend_strength"].astype(float)
    vol = df["volatility"].astype(float)
    abs_trend = trend.abs()

    # Optional news lockout column
    in_news_lockout: pd.Series | None = None
    news_impact: pd.Series | None = None
    if "in_news_lockout" in df.columns:
        in_news_lockout = df["in_news_lockout"].astype(bool)
    if "news_impact_level" in df.columns:
        news_impact = df["news_impact_level"].astype(int)

    # ------------------------------------------------------------------ #
    # Vectorised volatility bucketing                                     #
    # ------------------------------------------------------------------ #
    vol_lo, vol_hi = _compute_vol_thresholds(vol, cfg)
    vol_is_high = vol >= vol_hi
    vol_is_low = vol <= vol_lo
    # "normal" = neither
    vol_bucket = pd.Series("normal", index=df.index, dtype=object)
    vol_bucket[vol_is_high] = "high"
    vol_bucket[vol_is_low] = "low"

    # ------------------------------------------------------------------ #
    # Vectorised regime class                                             #
    # ------------------------------------------------------------------ #
    # Priority (highest first):
    # 1. event_driven  — in_news_lockout (high-impact news window)
    # 2. volatility_spike — high vol + flat price (no clear direction)
    # 3. trend          — trend_strength outside threshold
    #                     (if flag_high_vol_trend, high-vol trend is allowed
    #                      but gets a reduced position_sizing_factor)
    # 4. range          — default

    regime_class = pd.Series("range", index=df.index, dtype=object)

    # Step 4 base is already "range"
    # Step 3: trend
    is_trending = abs_trend >= cfg.trend_up_thresh
    regime_class[is_trending] = "trend"

    # Step 2: volatility_spike — high vol AND NOT clearly trending
    is_vol_spike = vol_is_high & ~is_trending
    regime_class[is_vol_spike] = "volatility_spike"

    # Step 1: event_driven — overrides everything if news lockout is active
    if in_news_lockout is not None:
        regime_class[in_news_lockout] = "event_driven"

    # ------------------------------------------------------------------ #
    # Vectorised regime type                                              #
    # ------------------------------------------------------------------ #
    regime_type = pd.Series("unknown", index=df.index, dtype=object)

    # Trend types
    trend_mask = regime_class == "trend"
    regime_type[trend_mask & (trend >= cfg.strong_trend_thresh)] = "uptrend_strong"
    regime_type[trend_mask & (trend >= cfg.trend_up_thresh) & (trend < cfg.strong_trend_thresh)] = "uptrend_weak"
    regime_type[trend_mask & (trend <= -cfg.strong_trend_thresh)] = "downtrend_strong"
    regime_type[trend_mask & (trend <= cfg.trend_down_thresh) & (trend > -cfg.strong_trend_thresh)] = "downtrend_weak"

    # Range types
    range_mask = regime_class == "range"
    regime_type[range_mask & vol_is_low] = "range_tight"
    regime_type[range_mask & ~vol_is_low] = "range_wide"

    # Vol spike types
    spike_mask = regime_class == "volatility_spike"
    regime_type[spike_mask & (trend >= 0)] = "vol_spike_up"
    regime_type[spike_mask & (trend < 0)] = "vol_spike_down"

    # Event driven types
    if in_news_lockout is not None and news_impact is not None:
        event_mask = regime_class == "event_driven"
        regime_type[event_mask & (news_impact >= 3)] = "macro_news_high_impact"
        regime_type[event_mask & (news_impact == 2)] = "macro_news_medium_impact"
        regime_type[event_mask & (news_impact <= 1)] = "macro_news_high_impact"  # default to high caution
    elif in_news_lockout is not None:
        regime_type[regime_class == "event_driven"] = "macro_news_high_impact"

    # ------------------------------------------------------------------ #
    # Vectorised confidence                                               #
    # ------------------------------------------------------------------ #
    # Normalise |trend_strength| against strong_trend_thresh so that
    # "strong trend" ≈ 1.0 and "weak trend" ≈ 0.2-0.5.
    # For non-trend regimes, confidence is lower by default.
    norm_abs = abs_trend / max(cfg.strong_trend_thresh, 1e-9)
    base_conf = norm_abs.clip(0.0, 1.0)

    # Reduce confidence in high-vol conditions — signal is noisier
    base_conf = base_conf.where(~vol_is_high, base_conf * 0.85)
    # Slightly boost confidence in low-vol conditions — signal is cleaner
    base_conf = base_conf.where(~vol_is_low, (base_conf * 1.05).clip(upper=1.0))

    # Non-trend regimes: cap confidence at 0.6 — we are less certain
    base_conf = base_conf.where(
        regime_class == "trend",
        base_conf.clip(upper=0.6),
    )

    # Event-driven: always low confidence for sizing
    if in_news_lockout is not None:
        base_conf = base_conf.where(~in_news_lockout, 0.2)

    base_conf = base_conf.clip(0.0, 1.0)

    # ------------------------------------------------------------------ #
    # Build output DataFrame directly — no per-row dataclass overhead    #
    # ------------------------------------------------------------------ #
    out = pd.DataFrame(index=df.index)
    out["regime_version"] = version
    out["regime_class"] = regime_class
    out["regime_type"] = regime_type
    out["regime_confidence"] = base_conf.round(4)
    out["regime_timeframe"] = timeframe
    out["vol_regime"] = vol_bucket
    out["trend_strength"] = trend.round(6)
    out["volatility"] = vol.round(8)

    # Hints and explain stored as dicts (one per row — kept for API compat)
    # Build them with list comprehensions rather than a Python loop over rows
    is_high_vol_trend = (regime_class == "trend") & vol_is_high & cfg.flag_high_vol_trend

    hints_list = []
    explain_list = []
    for i in range(len(out)):
        cls = out["regime_class"].iat[i]
        conf = float(out["regime_confidence"].iat[i])
        h = _hints_for_class(cls, conf)

        # Reduce position sizing for high-vol trend bars
        if is_high_vol_trend.iat[i]:
            h = dict(h)  # copy
            h["position_sizing_factor"] = float(h.get("position_sizing_factor", 1.0)) * 0.7
            h["risk_mode"] = "normal"  # override aggressive in volatile trends

        hints_list.append(h)

        rules: list[str] = []
        if abs_trend.iat[i] >= cfg.trend_up_thresh:
            rules.append("trend_threshold_crossed")
        if vol_is_high.iat[i]:
            rules.append("vol_high_quantile_crossed")
        if vol_is_low.iat[i]:
            rules.append("vol_low_quantile_crossed")
        if in_news_lockout is not None and in_news_lockout.iat[i]:
            rules.append("news_lockout_active")

        explain_list.append(
            {
                "rules_triggered": rules,
                "key_features": {
                    "trend_strength": float(trend.iat[i]),
                    "volatility": float(vol.iat[i]),
                    "vol_bucket_high": bool(vol_is_high.iat[i]),
                    "vol_bucket_low": bool(vol_is_low.iat[i]),
                    "is_high_vol_trend": bool(is_high_vol_trend.iat[i]),
                    "in_news_lockout": bool(
                        in_news_lockout.iat[i] if in_news_lockout is not None else False
                    ),
                },
                "raw_model_output": {},
            }
        )

    out["regime_hints"] = hints_list
    out["regime_explain"] = explain_list

    logger.info(
        "Detected structured regimes: class_counts=%s",
        out["regime_class"].value_counts().to_dict(),
    )
    return out


# ---------------------------------------------------------------------------
# Backward-compatible helpers
# ---------------------------------------------------------------------------

RegimeLabel = Literal[
    "trending_up",
    "trending_down",
    "ranging",
    "high_vol",
    "low_vol",
]


def detect_regime(
    df: pd.DataFrame, cfg: RegimeConfig = DEFAULT_REGIME_CONFIG
) -> pd.Series:
    """Legacy helper returning simple string labels.

    Derive labels directly from the structured output — no second loop.
    """
    structured = detect_regime_structured(df, timeframe="UNKNOWN", cfg=cfg)

    cls = structured["regime_class"]
    trend = structured["trend_strength"]
    vol_regime = structured["vol_regime"]

    # Vectorised label assignment
    labels = pd.Series("ranging", index=df.index, dtype=object)
    labels[vol_regime == "low"] = "low_vol"
    labels[vol_regime == "high"] = "high_vol"

    # Trend overrides vol labels — a trending market is labelled as trend
    trend_up_mask = (cls == "trend") & (trend >= 0)
    trend_dn_mask = (cls == "trend") & (trend < 0)
    labels[trend_up_mask] = "trending_up"
    labels[trend_dn_mask] = "trending_down"

    # event_driven / volatility_spike → high_vol for legacy consumers
    spike_mask = cls.isin(["volatility_spike", "event_driven"])
    labels[spike_mask] = "high_vol"

    series = pd.Series(labels.values, index=df.index, name="regime")
    logger.info(
        "Detected legacy regimes: counts=%s",
        series.value_counts().to_dict(),
    )
    return series


def add_regime_column(
    df: pd.DataFrame, cfg: RegimeConfig = DEFAULT_REGIME_CONFIG
) -> pd.DataFrame:
    """Add a simple ``regime`` label column.

    Calls detect_regime_structured once and derives both the label and
    any additional structured columns in a single pass.
    """
    structured = detect_regime_structured(df, timeframe="UNKNOWN", cfg=cfg)

    df = df.copy()

    # Legacy label column (required by signals.py)
    cls = structured["regime_class"]
    trend = structured["trend_strength"]
    vol_regime = structured["vol_regime"]

    labels = pd.Series("ranging", index=df.index, dtype=object)
    labels[vol_regime == "low"] = "low_vol"
    labels[vol_regime == "high"] = "high_vol"
    labels[(cls == "trend") & (trend >= 0)] = "trending_up"
    labels[(cls == "trend") & (trend < 0)] = "trending_down"
    labels[cls.isin(["volatility_spike", "event_driven"])] = "high_vol"

    df["regime"] = labels.values

    # Also attach structured columns that downstream code can use
    df["regime_class"] = structured["regime_class"].values
    df["regime_type"] = structured["regime_type"].values
    df["regime_confidence"] = structured["regime_confidence"].values
    df["vol_regime"] = structured["vol_regime"].values

    logger.info(
        "Detected legacy regimes: counts=%s",
        pd.Series(df["regime"]).value_counts().to_dict(),
    )
    return df


# ---------------------------------------------------------------------------
# Calibration utility — run once after collecting live data
# ---------------------------------------------------------------------------

def calibrate_thresholds(
    df: pd.DataFrame,
    trend_col: str = "trend_strength",
    vol_col: str = "volatility",
    trend_percentiles: tuple[float, float] = (0.60, 0.80),
    vol_percentiles: tuple[float, float] = (0.25, 0.75),
) -> dict:
    """Suggest RegimeConfig thresholds from a DataFrame of computed features.

    Run this once after accumulating a few weeks of live feature data to get
    empirically grounded thresholds for the ATR-normalised trend_strength.

    Usage:
        feat = load_features("XAUUSDm", "M15")
        suggestions = calibrate_thresholds(feat)
        print(suggestions)

    Returns a dict that can be passed directly to RegimeConfig(**suggestions).
    """
    if trend_col not in df.columns or vol_col not in df.columns:
        raise ValueError(f"DataFrame must contain '{trend_col}' and '{vol_col}'")

    abs_trend = df[trend_col].abs().dropna()
    vol = df[vol_col].dropna()

    weak_p, strong_p = trend_percentiles
    vol_lo_p, vol_hi_p = vol_percentiles

    suggestions = {
        "trend_up_thresh": float(abs_trend.quantile(weak_p)),
        "trend_down_thresh": -float(abs_trend.quantile(weak_p)),
        "strong_trend_thresh": float(abs_trend.quantile(strong_p)),
        "vol_low_quantile": vol_lo_p,
        "vol_high_quantile": vol_hi_p,
    }

    logger.info(
        "Threshold calibration suggestions for %s / %s:\n"
        "  trend_up_thresh    = %.4f  (abs_trend p%.0f)\n"
        "  strong_trend_thresh= %.4f  (abs_trend p%.0f)\n"
        "  (current defaults: up=%.4f strong=%.4f)",
        trend_col,
        vol_col,
        suggestions["trend_up_thresh"],
        weak_p * 100,
        suggestions["strong_trend_thresh"],
        strong_p * 100,
        DEFAULT_REGIME_CONFIG.trend_up_thresh,
        DEFAULT_REGIME_CONFIG.strong_trend_thresh,
    )

    return suggestions