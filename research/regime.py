from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Literal, TypedDict, Optional

import numpy as np
import pandas as pd

from ..logging_utils import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Regime Enums (aligned with Clio's trading regime spec)
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
    # Trend
    trend_up_thresh: float = 0.02
    trend_down_thresh: float = -0.02

    # Volatility quantiles
    vol_high_quantile: float = 0.7
    vol_low_quantile: float = 0.3

    # Strength buckets
    strong_trend_thresh: float = 0.04


DEFAULT_REGIME_CONFIG = RegimeConfig()


# ---------------------------------------------------------------------------
# Core detection – returns structured regime snapshot
# ---------------------------------------------------------------------------

@dataclass
class RegimeSnapshot:
    regime_version: str
    regime_class: RegimeClass
    regime_type: RegimeType
    regime_confidence: float
    regime_timeframe: str

    # Market context (minimal set; caller can join with other cols)
    vol_regime: Literal["low", "normal", "high"]
    trend_strength: float
    volatility: float

    # Hints + explain (optional)
    regime_hints: RegimeHints
    regime_explain: RegimeExplain


def _bucket_volatility(v: float, lo: float, hi: float) -> Literal["low", "normal", "high"]:
    if v >= hi:
        return "high"
    if v <= lo:
        return "low"
    return "normal"


def _classify_trend_type(trend: float, cfg: RegimeConfig) -> RegimeType:
    if trend >= cfg.strong_trend_thresh:
        return "uptrend_strong"
    if trend >= cfg.trend_up_thresh:
        return "uptrend_weak"
    if trend <= -cfg.strong_trend_thresh:
        return "downtrend_strong"
    if trend <= cfg.trend_down_thresh:
        return "downtrend_weak"
    return "unknown"


def detect_regime_structured(
    df: pd.DataFrame,
    timeframe: str,
    cfg: RegimeConfig = DEFAULT_REGIME_CONFIG,
    version: str = "v1",
) -> pd.DataFrame:
    """Return a DataFrame of structured regime snapshots aligned with `df.index`.

    Required columns in df: ``trend_strength`` and ``volatility``.

    This is the *new* regime interface used by the autonomous_trading_ai project.
    It is backward compatible with the older `detect_regime` helper which
    returned a simple label series.
    """

    if "trend_strength" not in df.columns or "volatility" not in df.columns:
        raise ValueError("DataFrame must contain 'trend_strength' and 'volatility' columns")

    trend = df["trend_strength"].astype(float)
    vol = df["volatility"].astype(float)

    # Compute volatility thresholds from sample
    vol_hi = vol.quantile(cfg.vol_high_quantile)
    vol_lo = vol.quantile(cfg.vol_low_quantile)

    snapshots: list[dict] = []

    for t, v in zip(trend, vol):
        vol_bucket = _bucket_volatility(v, vol_lo, vol_hi)

        # Default classification: trend / range / volatility_spike
        if vol_bucket == "high" and abs(t) < cfg.trend_up_thresh:
            regime_class: RegimeClass = "volatility_spike"
            regime_type: RegimeType = "vol_spike_up" if t >= 0 else "vol_spike_down"
        elif t >= cfg.trend_up_thresh or t <= cfg.trend_down_thresh:
            regime_class = "trend"
            regime_type = _classify_trend_type(t, cfg)
        else:
            regime_class = "range"
            regime_type = "range_tight" if vol_bucket == "low" else "range_wide"

        # Confidence: simple heuristic using |trend| and vol bucket
        base_conf = float(min(1.0, max(0.0, abs(t) / max(cfg.strong_trend_thresh, 1e-6))))
        if vol_bucket == "high":
            base_conf *= 0.9
        elif vol_bucket == "low":
            base_conf *= 1.05

        hints: RegimeHints = {}
        if regime_class == "trend":
            hints.update(
                {
                    "risk_mode": "aggressive" if base_conf > 0.7 else "normal",
                    "position_sizing_factor": 1.3 if base_conf > 0.7 else 1.0,
                    "allowed_playbooks": ["trend_follow_scalp", "breakout_continuation"],
                    "disabled_playbooks": ["range_fade", "mean_reversion_intraday"],
                }
            )
        elif regime_class == "range":
            hints.update(
                {
                    "risk_mode": "normal",
                    "position_sizing_factor": 1.0,
                    "allowed_playbooks": ["range_fade", "mean_reversion_intraday"],
                    "disabled_playbooks": ["trend_follow_scalp"],
                }
            )
        elif regime_class == "volatility_spike":
            hints.update(
                {
                    "risk_mode": "conservative",
                    "position_sizing_factor": 0.7,
                    "allowed_playbooks": ["news_spike_scalp"],
                    "disabled_playbooks": ["swing_trend_follow"],
                }
            )

        explain: RegimeExplain = {
            "rules_triggered": [],
            "key_features": {
                "trend_strength": float(t),
                "volatility": float(v),
                "vol_bucket_high": vol_bucket == "high",
                "vol_bucket_low": vol_bucket == "low",
            },
            "raw_model_output": {},
        }

        if regime_class == "trend":
            explain["rules_triggered"].append("trend_threshold_crossed")
        if vol_bucket == "high":
            explain["rules_triggered"].append("vol_high_quantile_crossed")
        if vol_bucket == "low":
            explain["rules_triggered"].append("vol_low_quantile_crossed")

        snapshot = RegimeSnapshot(
            regime_version=version,
            regime_class=regime_class,
            regime_type=regime_type,
            regime_confidence=float(max(0.0, min(1.0, base_conf))),
            regime_timeframe=timeframe,
            vol_regime=vol_bucket,
            trend_strength=float(t),
            volatility=float(v),
            regime_hints=hints,
            regime_explain=explain,
        )
        snapshots.append(asdict(snapshot))

    regime_df = pd.DataFrame(snapshots, index=df.index)
    logger.info("Detected structured regimes: class_counts=%s", regime_df["regime_class"].value_counts().to_dict())
    return regime_df


# ---------------------------------------------------------------------------
# Backward-compatible helper – simple label series
# ---------------------------------------------------------------------------

RegimeLabel = Literal[
    "trending_up",
    "trending_down",
    "ranging",
    "high_vol",
    "low_vol",
]


def detect_regime(df: pd.DataFrame, cfg: RegimeConfig = DEFAULT_REGIME_CONFIG) -> pd.Series:
    """Legacy helper returning simple string labels.

    Prefer ``detect_regime_structured`` for new code.
    """
    structured = detect_regime_structured(df, timeframe="UNKNOWN", cfg=cfg)

    labels: list[str] = []
    for cls, t, vol_regime in zip(
        structured["regime_class"].values,
        structured["trend_strength"].values,
        structured["vol_regime"].values,
    ):
        if cls == "trend":
            labels.append("trending_up" if t >= 0 else "trending_down")
        elif vol_regime == "high":
            labels.append("high_vol")
        elif vol_regime == "low":
            labels.append("low_vol")
        else:
            labels.append("ranging")

    series = pd.Series(labels, index=df.index, name="regime")
    logger.info("Detected legacy regimes: counts=%s", series.value_counts().to_dict())
    return series


def add_regime_column(df: pd.DataFrame, cfg: RegimeConfig = DEFAULT_REGIME_CONFIG) -> pd.DataFrame:
    """Legacy helper that adds a simple ``regime`` label column.

    Newer code should instead join the DataFrame returned by
    :func:`detect_regime_structured`.
    """
    df = df.copy()
    df["regime"] = detect_regime(df, cfg)
    return df
