from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from ..logging_utils import get_logger

logger = get_logger(__name__)

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
FEATURES_DIR = DATA_DIR / "features"
FEATURES_DIR.mkdir(parents=True, exist_ok=True)


def compute_rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period).mean()
    rs = avg_gain / (avg_loss + 1e-9)
    rsi = 100 - (100 / (1 + rs))
    return rsi


def compute_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high = df["high"]
    low = df["low"]
    close = df["close"]
    prev_close = close.shift(1)

    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1 / period, min_periods=period).mean()
    return atr


def compute_volatility(close: pd.Series, window: int = 20) -> pd.Series:
    returns = close.pct_change()
    return returns.rolling(window=window, min_periods=window).std()


def compute_trend_strength(close: pd.Series, window: int = 50) -> pd.Series:
    """Simple trend strength proxy: normalized slope of a rolling mean."""
    ma = close.rolling(window=window, min_periods=window).mean()
    slope = ma.diff()
    scale = close.rolling(window=window, min_periods=window).std()
    return slope / (scale + 1e-9)


def compute_ichimoku(df: pd.DataFrame) -> pd.DataFrame:
    """Add Ichimoku Kinko Hyo lines to the DataFrame."""
    high = df["high"]
    low = df["low"]

    conv_period = 9
    base_period = 26
    span_b_period = 52

    tenkan_sen = (high.rolling(conv_period).max() + low.rolling(conv_period).min()) / 2
    kijun_sen = (high.rolling(base_period).max() + low.rolling(base_period).min()) / 2

    senkou_span_a = ((tenkan_sen + kijun_sen) / 2).shift(base_period)
    senkou_span_b = (
        (high.rolling(span_b_period).max() + low.rolling(span_b_period).min()) / 2
    ).shift(base_period)

    chikou_span = df["close"].shift(-base_period)

    df = df.copy()
    df["tenkan_sen"] = tenkan_sen
    df["kijun_sen"] = kijun_sen
    df["senkou_span_a"] = senkou_span_a
    df["senkou_span_b"] = senkou_span_b
    df["chikou_span"] = chikou_span
    return df


def compute_fib_zones(df: pd.DataFrame, window: int = 100) -> pd.DataFrame:
    """Add simple Fibonacci zone flags based on rolling high/low.

    fib_zone_382 == 1 when close is near 38.2% retracement
    fib_zone_618 == 1 when close is near 61.8% retracement
    """
    high = df["high"]
    low = df["low"]
    close = df["close"]

    rolling_high = high.rolling(window).max()
    rolling_low = low.rolling(window).min()
    range_ = rolling_high - rolling_low
    position = (close - rolling_low) / (range_ + 1e-9)

    df = df.copy()
    df["fib_zone_382"] = position.between(0.36, 0.40).astype(int)
    df["fib_zone_618"] = position.between(0.60, 0.64).astype(int)
    return df


NEWS_PATH = DATA_DIR / "raw" / "news_events.parquet"


def _load_news_events() -> pd.DataFrame | None:
    """Load macro news events if available.

    This is a lightweight, optional dependency. If the file does not
    exist or fails to load, we simply skip news-based features.
    """
    if not NEWS_PATH.exists():
        logger.info("No news_events.parquet found at %s; skipping news features", NEWS_PATH)
        return None
    try:
        news = pd.read_parquet(NEWS_PATH)
    except Exception as e:
        logger.exception("Failed to load news events from %s: %s", NEWS_PATH, e)
        return None
    if "time" not in news.columns:
        logger.warning("News events file missing 'time' column; skipping news features")
        return None
    news = news.copy()
    news["time"] = pd.to_datetime(news["time"], utc=True)
    return news


def _add_news_features(df: pd.DataFrame, news: pd.DataFrame, window_min: int = 30) -> pd.DataFrame:
    """Join macro news context into the feature DataFrame.

    For each bar time, we compute proximity to the nearest news event
    and derive simple features:

    - has_news_window
    - news_impact_level
    - news_time_delta_min
    - news_surprise
    - in_news_lockout (high-impact within window)
    """
    if news is None or news.empty:
        return df

    df = df.copy()
    df["time"] = pd.to_datetime(df["time"], utc=True)

    # Map impact strings to integer levels
    impact_map = {"low": 1, "medium": 2, "high": 3}
    news = news.copy()
    news["impact_level"] = news["impact"].map(impact_map).fillna(0).astype(int)

    # For simplicity, we treat all events as relevant to XAUUSD for now
    # (USD-centric). Later we can filter by currency if needed.

    # Sort for merge_asof
    news = news.sort_values("time")
    df = df.sort_values("time")

    # Forward and backward nearest events
    nearest_forward = pd.merge_asof(
        df[["time"]], news[["time", "impact_level", "surprise"]],
        on="time", direction="forward")
    nearest_backward = pd.merge_asof(
        df[["time"]], news[["time", "impact_level", "surprise"]],
        on="time", direction="backward")

    # Compute deltas in minutes
    fwd_delta = (nearest_forward["time_y"] - df["time"]).dt.total_seconds() / 60.0
    bwd_delta = (df["time"] - nearest_backward["time_y"]).dt.total_seconds() / 60.0

    # Choose event with smaller absolute delta
    fwd_abs = fwd_delta.abs().fillna(np.inf)
    bwd_abs = bwd_delta.abs().fillna(np.inf)
    use_fwd = fwd_abs <= bwd_abs

    nearest_time = np.where(use_fwd, nearest_forward["time_y"], nearest_backward["time_y"])
    nearest_impact = np.where(use_fwd,
                              nearest_forward["impact_level"],
                              nearest_backward["impact_level"])
    nearest_surprise = np.where(use_fwd,
                                nearest_forward["surprise"],
                                nearest_backward["surprise"])
    nearest_delta = np.where(use_fwd, fwd_delta, -bwd_delta)

    df["news_time_delta_min"] = nearest_delta
    df["news_impact_level"] = pd.Series(nearest_impact, index=df.index).fillna(0).astype(int)
    df["news_surprise"] = pd.Series(nearest_surprise, index=df.index)

    window = float(window_min)
    df["has_news_window"] = df["news_time_delta_min"].abs() <= window
    # Simple lockout: high-impact within window
    df["in_news_lockout"] = (df["news_impact_level"] >= 3) & df["has_news_window"]

    return df


def compute_features(
    df: pd.DataFrame,
    symbol: str,
    timeframe: str,
    rsi_period: int = 14,
    ma_short: int = 20,
    ma_long: int = 50,
    atr_period: int = 14,
    vol_window: int = 20,
    trend_window: int = 50,
) -> pd.DataFrame:
    """Given OHLCV DataFrame, compute technical + macro-context features.

    Expected df columns: ["time", "open", "high", "low", "close", "tick_volume"].
    """
    logger.info(
        "Computing features for %s %s (len=%d)", symbol, timeframe, len(df)
    )

    df = df.copy()
    df = df.sort_values("time")
    df["time"] = pd.to_datetime(df["time"])

    # Core indicators
    df["rsi"] = compute_rsi(df["close"], period=rsi_period)
    df["ma_short"] = df["close"].rolling(ma_short, min_periods=ma_short).mean()
    df["ma_long"] = df["close"].rolling(ma_long, min_periods=ma_long).mean()
    df["atr"] = compute_atr(df, period=atr_period)
    df["volatility"] = compute_volatility(df["close"], window=vol_window)
    df["trend_strength"] = compute_trend_strength(df["close"], window=trend_window)

    # Ichimoku
    df = compute_ichimoku(df)

    # Fibonacci zones
    df = compute_fib_zones(df, window=100)

    # Optional: macro news features
    news = _load_news_events()
    if news is not None:
        df = _add_news_features(df, news)

    df.dropna(inplace=True)
    logger.info(
        "Finished feature computation for %s %s (len=%d)", symbol, timeframe, len(df)
    )
    return df


def save_features(df: pd.DataFrame, symbol: str, timeframe: str) -> Path:
    FEATURES_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"{symbol}_{timeframe}_features.parquet"
    path = FEATURES_DIR / filename
    df.to_parquet(path)
    logger.info("Saved features to %s", path)
    return path


def load_features(symbol: str, timeframe: str) -> pd.DataFrame:
    filename = f"{symbol}_{timeframe}_features.parquet"
    path = FEATURES_DIR / filename
    if not path.exists():
        raise FileNotFoundError(f"No features file at {path}")
    df = pd.read_parquet(path)
    logger.info("Loaded features from %s (len=%d)", path, len(df))
    return df
