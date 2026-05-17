import numpy as np
import pandas as pd

from autonomous_trading_ai.research.features import compute_features
from autonomous_trading_ai.strategies.generator import FAMILY_LIBRARY, random_strategy
from autonomous_trading_ai.strategies.pool import strategy_motif


def _sample_ohlcv(rows: int = 260) -> pd.DataFrame:
    idx = pd.date_range("2026-01-01", periods=rows, freq="15min", tz="UTC")
    base = 100.0 + np.sin(np.arange(rows) / 12.0) * 1.5 + np.arange(rows) * 0.03
    close = pd.Series(base)
    open_ = close.shift(1).fillna(close.iloc[0] - 0.1)
    high = pd.concat([open_, close], axis=1).max(axis=1) + 0.25
    low = pd.concat([open_, close], axis=1).min(axis=1) - 0.25
    tick_volume = 100 + (np.arange(rows) % 20) * 5
    return pd.DataFrame(
        {
            "time": idx,
            "open": open_.to_numpy(),
            "high": high.to_numpy(),
            "low": low.to_numpy(),
            "close": close.to_numpy(),
            "tick_volume": tick_volume,
        }
    )


def test_compute_features_adds_vwap_and_volume_profile_context():
    feat = compute_features(_sample_ohlcv(), "BTCUSDm", "M15")
    required = {
        "session_vwap",
        "session_vwap_dist_atr",
        "session_vwap_slope",
        "above_vwap",
        "below_vwap",
        "vwap_reclaim_long",
        "vwap_reclaim_short",
        "vp_poc",
        "vp_vah",
        "vp_val",
        "vp_width_atr",
        "vp_close_pos",
        "in_value_area",
        "near_vp_poc",
        "near_vp_vah",
        "near_vp_val",
        "vp_accept_above",
        "vp_accept_below",
    }
    assert required.issubset(set(feat.columns))
    usable_profile = feat.dropna(subset=["vp_poc", "vp_vah", "vp_val"])
    assert not usable_profile.empty
    assert (usable_profile["vp_vah"] >= usable_profile["vp_val"]).all()


def test_vwap_profile_strategy_family_generates_orderflow_rules():
    strat = random_strategy("BTCUSDm", "M15", family="vwap_profile")
    rule_text = f"{strat.long_entry_rule} || {strat.short_entry_rule} || {strat.exit_rule}"
    assert "session_vwap" in rule_text or "above_vwap" in rule_text or "below_vwap" in rule_text
    assert "vp_" in rule_text or "near_vp" in rule_text
    assert strat.params["family"] == "vwap_profile"
    assert strat.params["playbook_type"] == "vwap_volume_profile"
    assert strategy_motif(strat) == "vwap_volume_profile"
    assert "vwap_profile" in FAMILY_LIBRARY
