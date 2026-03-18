from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from ..logging_utils import get_logger

logger = get_logger(__name__)

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
FEATURES_DIR = DATA_DIR / "features"
FEATURES_DIR.mkdir(parents=True, exist_ok=True)

# Core columns that must be non-NaN for a row to be usable in signal generation.
# Rows missing ANY of these are dropped. Ichimoku/Fib/news columns are allowed
# to be NaN at the edges and are excluded from the hard drop.
_CORE_FEATURE_COLS = [
    "rsi",
    "ma_short",
    "ma_long",
    "atr",
    "volatility",
    "trend_strength",
]


def compute_rsi(close: pd.Series, period: int = 14) -> pd.Series:
    """Wilder's RSI using EWM with adjust=False — matches MT5 and TradingView."""
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    # adjust=False is Wilder's smoothing (recursive / RMA).
    # adjust=True (pandas default) uses a different weight scheme and gives
    # different values than what trading platforms display.
    avg_gain = gain.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()
    rs = avg_gain / (avg_loss + 1e-9)
    return 100.0 - (100.0 / (1.0 + rs))


def compute_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Wilder's ATR using EWM with adjust=False — matches MT5."""
    high = df["high"]
    low = df["low"]
    close = df["close"]
    prev_close = close.shift(1)

    tr = pd.concat(
        [high - low, (high - prev_close).abs(), (low - prev_close).abs()],
        axis=1,
    ).max(axis=1)

    return tr.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()


def compute_volatility(close: pd.Series, window: int = 20) -> pd.Series:
    returns = close.pct_change()
    return returns.rolling(window=window, min_periods=window).std()


def compute_trend_strength(
    close: pd.Series,
    atr: pd.Series,
    window: int = 50,
) -> pd.Series:
    """ATR-normalized slope of a rolling mean.

    Normalising by ATR rather than close.std() keeps the values stationary
    across different price levels (critical for instruments like gold at
    ~2900 where close std can be very large and would compress all values
    toward zero).

    Values are typically in the range [-2, 2]:
      > 0  : upward trend
      < 0  : downward trend
      ~0   : flat / ranging
    """
    ma = close.rolling(window=window, min_periods=window).mean()
    slope = ma.diff()
    return slope / (atr + 1e-9)


def compute_ichimoku(df: pd.DataFrame) -> pd.DataFrame:
    """Add Ichimoku Kinko Hyo lines to the DataFrame.

    IMPORTANT — Senkou span shift:
    The traditional Ichimoku chart projects Senkou A/B *forward* by 26 periods
    (shift +26 on a chart). For feature engineering this is misleading: at bar i,
    shift(+26) gives the average of tenkan/kijun from bar i-26, i.e. the cloud
    as it was 26 bars ago — NOT the current live cloud level.

    Instead we store the *unshifted* spans (instantaneous values). This is what
    a live system would actually compare price against when asking "is price above
    the cloud right now?". The first `base_period` rows will still be NaN due to
    the rolling windows, but no rows at the tail end are lost.

    chikou_span is intentionally EXCLUDED: it requires close prices from 26 bars
    in the future (shift(-26)), which is forward-looking and introduces data
    leakage into any backtest or ML model.
    """
    high = df["high"]
    low = df["low"]

    conv_period = 9
    base_period = 26
    span_b_period = 52

    tenkan_sen = (
        high.rolling(conv_period).max() + low.rolling(conv_period).min()
    ) / 2
    kijun_sen = (
        high.rolling(base_period).max() + low.rolling(base_period).min()
    ) / 2

    # Unshifted instantaneous spans — price vs cloud comparison is immediate
    senkou_span_a = (tenkan_sen + kijun_sen) / 2
    senkou_span_b = (
        high.rolling(span_b_period).max() + low.rolling(span_b_period).min()
    ) / 2

    # Derived: is price currently inside / above / below the cloud?
    close = df["close"]
    cloud_top = senkou_span_a.combine(senkou_span_b, max)
    cloud_bot = senkou_span_a.combine(senkou_span_b, min)

    df = df.copy()
    df["tenkan_sen"] = tenkan_sen
    df["kijun_sen"] = kijun_sen
    df["senkou_span_a"] = senkou_span_a
    df["senkou_span_b"] = senkou_span_b
    df["above_cloud"] = (close > cloud_top).astype(int)
    df["below_cloud"] = (close < cloud_bot).astype(int)
    df["in_cloud"] = (~df["above_cloud"].astype(bool) & ~df["below_cloud"].astype(bool)).astype(int)

    # NOTE: chikou_span intentionally not added — it uses future close prices.
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
    """Load macro news events if available."""
    if not NEWS_PATH.exists():
        logger.info(
            "No news_events.parquet found at %s; skipping news features", NEWS_PATH
        )
        return None
    try:
        news = pd.read_parquet(NEWS_PATH)
    except Exception as e:
        logger.exception("Failed to load news events from %s: %s", NEWS_PATH, e)
        return None
    if "time" not in news.columns:
        logger.warning(
            "News events file missing 'time' column; skipping news features"
        )
        return None
    news = news.copy()
    news["time"] = pd.to_datetime(news["time"], utc=True)
    return news


def _add_news_features(
    df: pd.DataFrame, news: pd.DataFrame, window_min: int = 30
) -> pd.DataFrame:
    """Join macro news context into the feature DataFrame.

    For each bar, compute proximity to the nearest news event and derive:
    - has_news_window    : bool, nearest event is within window_min minutes
    - news_impact_level : int 1-3 (low/medium/high)
    - news_time_delta_min: float, signed minutes to nearest event
    - news_surprise     : float, actual - forecast surprise value
    - in_news_lockout   : bool, high-impact event within window
    """
    if news is None or news.empty:
        return df

    df = df.copy()
    # Ensure timezone-aware UTC on both sides to avoid comparison errors
    df["time"] = pd.to_datetime(df["time"], utc=True)

    impact_map = {"low": 1, "medium": 2, "high": 3}
    news = news.copy()
    news["impact_level"] = (
        news["impact"].map(impact_map).fillna(0).astype(int)
    )

    # Rename news time so merge_asof exposes it as a separate column.
    # When both frames share the same key name (on="time"), pandas keeps
    # only the LEFT frame's key in the output — "time_y" never appears.
    # Renaming the right key to "news_time" avoids the KeyError.
    news = news.rename(columns={"time": "news_time"}).sort_values("news_time")
    df = df.sort_values("time").reset_index(drop=True)

    cols_right = ["news_time", "impact_level", "surprise"]

    nearest_fwd = pd.merge_asof(
        df[["time"]],
        news[cols_right],
        left_on="time",
        right_on="news_time",
        direction="forward",
    )
    nearest_bwd = pd.merge_asof(
        df[["time"]],
        news[cols_right],
        left_on="time",
        right_on="news_time",
        direction="backward",
    )

    fwd_delta = (
        (nearest_fwd["news_time"] - df["time"]).dt.total_seconds() / 60.0
    ).fillna(np.inf)
    bwd_delta = (
        (df["time"] - nearest_bwd["news_time"]).dt.total_seconds() / 60.0
    ).fillna(np.inf)

    use_fwd = fwd_delta.abs() <= bwd_delta.abs()

    nearest_impact = np.where(
        use_fwd, nearest_fwd["impact_level"], nearest_bwd["impact_level"]
    )
    nearest_surprise = np.where(
        use_fwd, nearest_fwd["surprise"], nearest_bwd["surprise"]
    )
    nearest_delta = np.where(use_fwd, fwd_delta, -bwd_delta)

    df["news_time_delta_min"] = nearest_delta
    df["news_impact_level"] = (
        pd.Series(nearest_impact, index=df.index).fillna(0).astype(int)
    )
    df["news_surprise"] = pd.Series(nearest_surprise, index=df.index)

    window = float(window_min)
    df["has_news_window"] = df["news_time_delta_min"].abs() <= window
    df["in_news_lockout"] = (
        (df["news_impact_level"] >= 3) & df["has_news_window"]
    )

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

    Expected columns: ["time", "open", "high", "low", "close", "tick_volume"].
    """
    logger.info(
        "Computing features for %s %s (len=%d)", symbol, timeframe, len(df)
    )

    df = df.copy()
    df = df.sort_values("time")
    # Timezone-aware UTC — consistent with news event timestamps
    df["time"] = pd.to_datetime(df["time"], utc=True)

    # Core indicators
    df["rsi"] = compute_rsi(df["close"], period=rsi_period)
    df["ma_short"] = df["close"].rolling(ma_short, min_periods=ma_short).mean()
    df["ma_long"] = df["close"].rolling(ma_long, min_periods=ma_long).mean()
    df["atr"] = compute_atr(df, period=atr_period)
    df["volatility"] = compute_volatility(df["close"], window=vol_window)

    # ATR-normalised trend strength (more stationary than std-normalised)
    df["trend_strength"] = compute_trend_strength(
        df["close"], df["atr"], window=trend_window
    )

    # Ichimoku (chikou excluded — forward-looking; senkou unshifted — instantaneous)
    df = compute_ichimoku(df)

    # Fibonacci zones
    df = compute_fib_zones(df, window=100)

    # Optional: macro news features
    news = _load_news_events()
    if news is not None:
        df = _add_news_features(df, news)

    # Drop only on core signal columns — not on Ichimoku/Fib/news tails.
    # This preserves recent bars that have NaN in derived-only columns.
    before = len(df)
    df.dropna(subset=_CORE_FEATURE_COLS, inplace=True)
    df.reset_index(drop=True, inplace=True)
    dropped = before - len(df)
    if dropped:
        logger.debug(
            "Dropped %d rows with NaN in core feature columns for %s %s",
            dropped,
            symbol,
            timeframe,
        )

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