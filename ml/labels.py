"""Leakage-safe label builders for adaptive ML research.

These helpers may inspect future OHLC values only to create target labels. The
feature-selection layer is responsible for excluding every generated label from
training inputs.
"""

from __future__ import annotations

import math
from typing import Iterable

import pandas as pd


def _atr_series(df: pd.DataFrame) -> pd.Series:
    if "atr" not in df.columns:
        raise ValueError("ATR column 'atr' is required for ATR-normalized ML labels")
    atr = pd.to_numeric(df["atr"], errors="coerce")
    return atr.replace(0, pd.NA)


def add_future_return_labels(df: pd.DataFrame, horizons: Iterable[int]) -> pd.DataFrame:
    """Add future close-to-close returns normalized by current-row ATR."""
    out = df.copy()
    close = pd.to_numeric(out["close"], errors="coerce")
    atr = _atr_series(out)
    for horizon in horizons:
        if horizon <= 0:
            raise ValueError(f"horizon must be positive, got {horizon}")
        out[f"future_return_{horizon}"] = (close.shift(-horizon) - close) / atr
    return out


def add_direction_label(df: pd.DataFrame, horizon: int, neutral_threshold_atr: float) -> pd.DataFrame:
    """Classify future return as buy/sell/hold using an ATR threshold."""
    out = df.copy()
    column = f"future_return_{horizon}"
    if column not in out.columns:
        out = add_future_return_labels(out, (horizon,))

    def classify(value: float) -> str | float:
        if pd.isna(value):
            return pd.NA
        if value > neutral_threshold_atr:
            return "buy"
        if value < -neutral_threshold_atr:
            return "sell"
        return "hold"

    out["direction_label"] = out[column].map(classify)
    return out


def add_tp_sl_first_touch_labels(
    df: pd.DataFrame,
    tp_atr_mult: float,
    sl_atr_mult: float,
    max_lookahead_bars: int,
) -> pd.DataFrame:
    """Label which side first touches a symmetric long/short TP/SL envelope.

    The label is direction-neutral for candidate entries at the current close:
    ``buy_tp`` means upside TP was touched before downside SL, ``sell_tp`` means
    downside TP was touched before upside SL, ``ambiguous`` means both sides hit
    in the same future bar, and ``none`` means neither side hit within lookahead.
    """
    if max_lookahead_bars <= 0:
        raise ValueError("max_lookahead_bars must be positive")
    out = df.copy()
    high = pd.to_numeric(out["high"], errors="coerce")
    low = pd.to_numeric(out["low"], errors="coerce")
    close = pd.to_numeric(out["close"], errors="coerce")
    atr = _atr_series(out)

    labels: list[str | pd._libs.missing.NAType] = []
    ambiguous_flags: list[bool | pd._libs.missing.NAType] = []
    for idx in range(len(out)):
        if idx + max_lookahead_bars >= len(out) or pd.isna(atr.iloc[idx]):
            labels.append(pd.NA)
            ambiguous_flags.append(pd.NA)
            continue
        entry = close.iloc[idx]
        buy_tp = entry + tp_atr_mult * atr.iloc[idx]
        buy_sl = entry - sl_atr_mult * atr.iloc[idx]
        label = "none"
        ambiguous = False
        for future_idx in range(idx + 1, idx + max_lookahead_bars + 1):
            hit_up = high.iloc[future_idx] >= buy_tp
            hit_down = low.iloc[future_idx] <= buy_sl
            if hit_up and hit_down:
                label = "ambiguous"
                ambiguous = True
                break
            if hit_up:
                label = "buy_tp"
                break
            if hit_down:
                label = "sell_tp"
                break
        labels.append(label)
        ambiguous_flags.append(ambiguous)

    out["tp_sl_label"] = labels
    out["ambiguous_same_bar"] = ambiguous_flags
    return out


def drop_unlabelable_tail(df: pd.DataFrame, max_lookahead_bars: int) -> pd.DataFrame:
    """Drop final rows that cannot have complete future labels."""
    if max_lookahead_bars <= 0:
        return df.copy()
    if len(df) <= max_lookahead_bars:
        return df.iloc[0:0].copy()
    return df.iloc[:-max_lookahead_bars].copy().reset_index(drop=True)
