"""Dataset assembly for Stage 1 adaptive ML shadow models."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd
from pandas.api.types import is_numeric_dtype

from autonomous_trading_ai.config import MLConfig, canonical_symbol
from autonomous_trading_ai.ml.labels import add_direction_label, add_future_return_labels, drop_unlabelable_tail


@dataclass
class MLDataset:
    symbol: str
    timeframe: str
    feature_columns: list[str]
    train: pd.DataFrame
    validation: pd.DataFrame
    test: pd.DataFrame
    label_column: str


_EXCLUDE_SUBSTRINGS = (
    "target",
    "pnl",
    "result",
    "ticket",
    "order",
    "profit",
)


def load_feature_frame(symbol: str, timeframe: str, base_dir: Path | None = None) -> pd.DataFrame:
    root = Path(base_dir) if base_dir is not None else Path(__file__).resolve().parents[1]
    path = root / "data" / "features" / f"{symbol}_{timeframe}_features.parquet"
    if not path.exists():
        raise FileNotFoundError(f"feature parquet not found: {path}")
    df = pd.read_parquet(path)
    if "time" in df.columns:
        df = df.sort_values("time").reset_index(drop=True)
    return df


def _augment_btc_features(df: pd.DataFrame) -> pd.DataFrame:
    """Add BTC-specific momentum and volatility features.

    BTC trades around the clock and tends to benefit from short-horizon price
    action context that is weaker or less useful on metals. These features stay
    leak-free by using only current and past bars.
    """
    out = df.copy()
    close = pd.to_numeric(out["close"], errors="coerce")
    open_ = pd.to_numeric(out["open"], errors="coerce") if "open" in out.columns else close
    high = pd.to_numeric(out["high"], errors="coerce") if "high" in out.columns else close
    low = pd.to_numeric(out["low"], errors="coerce") if "low" in out.columns else close
    atr = pd.to_numeric(out["atr"], errors="coerce") if "atr" in out.columns else pd.Series(pd.NA, index=out.index)
    atr = atr.replace(0, pd.NA)

    for horizon in (1, 2, 4, 8):
        out[f"btc_return_{horizon}"] = (close - close.shift(horizon)) / atr

    out["btc_body_atr"] = (close - open_) / atr
    out["btc_range_atr"] = (high - low) / atr
    out["btc_wick_up_atr"] = (high - pd.concat([open_, close], axis=1).max(axis=1)) / atr
    out["btc_wick_down_atr"] = (pd.concat([open_, close], axis=1).min(axis=1) - low) / atr
    if "trend_strength" in out.columns:
        out["btc_trend_accel"] = pd.to_numeric(out["trend_strength"], errors="coerce").diff()
    if "session_vwap" in out.columns:
        session_vwap = pd.to_numeric(out["session_vwap"], errors="coerce")
        out["btc_vwap_distance_atr"] = (close - session_vwap) / atr
    if "volatility" in out.columns:
        out["btc_volatility_change"] = pd.to_numeric(out["volatility"], errors="coerce").diff()
    return out


def _augment_xau_features(df: pd.DataFrame) -> pd.DataFrame:
    """Add XAU-specific session, news, and regime interaction features.

    XAU has stronger session/news structure than the baseline frame captures,
    so we enrich those contexts without changing label construction.
    """
    out = df.copy()
    time = pd.to_datetime(out["time"], utc=True, errors="coerce")
    hour = time.dt.hour.astype(float) + time.dt.minute.astype(float) / 60.0
    dow = time.dt.dayofweek.astype(float)

    out["xau_hour_sin"] = np.sin(2.0 * np.pi * hour / 24.0)
    out["xau_hour_cos"] = np.cos(2.0 * np.pi * hour / 24.0)
    out["xau_dow_sin"] = np.sin(2.0 * np.pi * dow / 7.0)
    out["xau_dow_cos"] = np.cos(2.0 * np.pi * dow / 7.0)
    out["xau_london_ny_overlap"] = (((time.dt.hour >= 13) & (time.dt.hour < 17)).astype(int))
    out["xau_london_open_window"] = (((time.dt.hour >= 7) & (time.dt.hour < 11)).astype(int))
    out["xau_ny_open_window"] = (((time.dt.hour >= 13) & (time.dt.hour < 17)).astype(int))
    out["xau_asia_london_transition"] = (((time.dt.hour >= 7) & (time.dt.hour < 10)).astype(int))

    if "news_impact_level" in out.columns:
        impact = pd.to_numeric(out["news_impact_level"], errors="coerce").fillna(0)
        out["xau_news_impact_sq"] = impact.pow(2)
        out["xau_news_high_impact"] = (impact >= 3).astype(int)
        out["xau_news_medium_impact"] = (impact >= 2).astype(int)
    if "news_time_delta_min" in out.columns:
        delta = pd.to_numeric(out["news_time_delta_min"], errors="coerce")
        out["xau_news_delta_inv"] = 1.0 / (1.0 + delta.abs())
        out["xau_news_urgent"] = (delta.abs() <= 30.0).astype(int)
        out["xau_news_stale"] = (delta.abs() >= 180.0).astype(int)
    if "has_news_window" in out.columns and "news_impact_level" in out.columns:
        has_news = pd.to_numeric(out["has_news_window"], errors="coerce").fillna(0)
        impact = pd.to_numeric(out["news_impact_level"], errors="coerce").fillna(0)
        out["xau_news_window_x_impact"] = has_news * impact
    if "in_news_lockout" in out.columns and "news_impact_level" in out.columns:
        lockout = pd.to_numeric(out["in_news_lockout"], errors="coerce").fillna(0)
        impact = pd.to_numeric(out["news_impact_level"], errors="coerce").fillna(0)
        out["xau_news_lockout_x_impact"] = lockout * impact
    if "regime_confidence" in out.columns:
        regime_conf = pd.to_numeric(out["regime_confidence"], errors="coerce")
        if "trend_strength" in out.columns:
            trend_strength = pd.to_numeric(out["trend_strength"], errors="coerce")
            out["xau_regime_trend_strength"] = regime_conf * trend_strength
            out["xau_regime_trend_strength_abs"] = regime_conf * trend_strength.abs()
        if "news_impact_level" in out.columns:
            impact = pd.to_numeric(out["news_impact_level"], errors="coerce").fillna(0)
            out["xau_regime_news_pressure"] = regime_conf * impact
    return out


def _is_excluded_column(column: str, label_columns: set[str]) -> bool:
    lower = column.lower()
    if lower == "time" or column in label_columns:
        return True
    if lower.startswith("future_") or lower.endswith("_label"):
        return True
    return any(token in lower for token in _EXCLUDE_SUBSTRINGS)


def infer_feature_columns(df: pd.DataFrame, label_columns: Iterable[str]) -> list[str]:
    label_set = set(label_columns)
    columns: list[str] = []
    for column in df.columns:
        if _is_excluded_column(str(column), label_set):
            continue
        if not is_numeric_dtype(df[column]):
            continue
        columns.append(str(column))
    return columns


def build_ml_dataset(symbol: str, timeframe: str, config: MLConfig, base_dir: Path | None = None) -> MLDataset:
    df = load_feature_frame(symbol, timeframe, base_dir=base_dir)
    if len(df) < config.min_training_rows + config.min_validation_rows + 3:
        raise ValueError(
            f"dataset for {symbol} {timeframe} is too small: {len(df)} rows; "
            f"need at least {config.min_training_rows + config.min_validation_rows + 3}"
        )

    df = add_future_return_labels(df, config.prediction_horizons_bars)
    df = add_direction_label(df, config.primary_horizon_bars, config.neutral_return_threshold_atr)
    df = drop_unlabelable_tail(df, config.max_label_lookahead_bars)
    df = df[df["direction_label"].notna()].copy().reset_index(drop=True)
    symbol_key = canonical_symbol(symbol)
    if symbol_key == "BTCUSDm":
        df = _augment_btc_features(df)
    elif symbol_key == "XAUUSDm":
        df = _augment_xau_features(df)
    if len(df) < config.min_training_rows + config.min_validation_rows + 3:
        raise ValueError(f"labeled dataset for {symbol} {timeframe} is too small: {len(df)} rows")

    label_column = "direction_label"
    feature_columns = infer_feature_columns(df, label_columns=[label_column])
    if not feature_columns:
        raise ValueError(f"no numeric feature columns inferred for {symbol} {timeframe}")

    n = len(df)
    train_end = max(config.min_training_rows, int(n * 0.60))
    validation_end = max(train_end + config.min_validation_rows, int(n * 0.80))
    if validation_end >= n:
        validation_end = n - 1
    if train_end >= validation_end:
        raise ValueError(f"dataset for {symbol} {timeframe} is too small after split constraints")

    return MLDataset(
        symbol=symbol,
        timeframe=timeframe,
        feature_columns=feature_columns,
        train=df.iloc[:train_end].copy().reset_index(drop=True),
        validation=df.iloc[train_end:validation_end].copy().reset_index(drop=True),
        test=df.iloc[validation_end:].copy().reset_index(drop=True),
        label_column=label_column,
    )
