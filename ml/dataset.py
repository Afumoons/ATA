"""Dataset assembly for Stage 1 adaptive ML shadow models."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import pandas as pd
from pandas.api.types import is_numeric_dtype

from autonomous_trading_ai.config import MLConfig
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
