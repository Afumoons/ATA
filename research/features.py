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


# ---------------------------------------------------------------------------
# News features — backed by data/news_collector.py
# ---------------------------------------------------------------------------

def _load_news_events() -> pd.DataFrame | None:
    """Load gold-relevant news events from news_collector output.

    Primary source: news_collector.load_news_events() which reads
    news_events.parquet with column 'datetime_utc'.

    Falls back to legacy format (column 'time') for backward compatibility.
    Returns None if no data available — caller degrades gracefully.
    """
    try:
        from ..data.news_collector import load_news_events
        news = load_news_events()
        if news is not None and not news.empty:
            # Filter to gold-relevant only
            if "is_gold_relevant" in news.columns:
                news = news[news["is_gold_relevant"] == True].copy()
            if not news.empty:
                return news
    except ImportError:
        pass
    except Exception:
        logger.exception("Failed to load news events via news_collector")

    # Legacy fallback: old format with 'time' column
    news_path = DATA_DIR / "raw" / "news_events.parquet"
    if not news_path.exists():
        logger.info(
            "No news_events.parquet found at %s; skipping news features", news_path
        )
        return None
    try:
        news = pd.read_parquet(news_path)
        if "time" in news.columns:
            news = news.rename(columns={"time": "datetime_utc"})
            news["datetime_utc"] = pd.to_datetime(news["datetime_utc"], utc=True)
            return news
    except Exception:
        logger.exception("Failed to load legacy news events")
    return None


def _add_news_features(
    df: pd.DataFrame,
    news: pd.DataFrame,
    window_min: int = 60,
    lockout_min: int = 15,
) -> pd.DataFrame:
    """Join news calendar data into feature DataFrame.

    Adds columns:
        news_impact_level    : int 0-3
        news_time_delta_min  : float, signed minutes to nearest event
                               (negative = bar is before event)
        has_news_window      : bool, within window_min of any impact>=2 event
        in_news_lockout      : bool, within lockout_min of any impact==3 event

    Uses vectorised numpy — O(n_bars + n_events), not O(n_bars × n_events).
    """
    if news is None or news.empty:
        return df

    df = df.copy()
    df["time"] = pd.to_datetime(df["time"], utc=True)

    # Determine impact column name — news_collector uses 'impact' (int 0-3)
    # legacy format may use 'impact' (str 'High'/'Medium') mapped via impact_level
    if "impact" in news.columns:
        if news["impact"].dtype == object:
            # Legacy string format
            impact_map = {"low": 1, "Low": 1, "medium": 2, "Medium": 2,
                          "high": 3, "High": 3}
            news = news.copy()
            news["_impact_int"] = news["impact"].map(impact_map).fillna(0).astype(int)
            impact_col = "_impact_int"
        else:
            impact_col = "impact"
    elif "impact_level" in news.columns:
        impact_col = "impact_level"
    else:
        logger.warning("News data has no recognizable impact column — skipping")
        return df

    # Ensure datetime_utc is UTC-aware
    news = news.copy()
    news["datetime_utc"] = pd.to_datetime(news["datetime_utc"], utc=True)
    news = news.sort_values("datetime_utc").reset_index(drop=True)

    # Normalize both bar/event times to a common nanosecond scale.
    # Parquet-loaded timezone-aware columns may preserve different underlying
    # units (e.g. `datetime64[ms, UTC]` vs `datetime64[us, UTC]`), which breaks
    # raw subtraction if we do not coerce them to the same resolution first.
    bar_ns = (
        pd.to_datetime(df["time"], utc=True)
        .dt.tz_convert("UTC")
        .dt.tz_localize(None)
        .astype("datetime64[ns]")
        .astype(np.int64)
        .to_numpy()
    )
    event_ns = (
        pd.to_datetime(news["datetime_utc"], utc=True)
        .dt.tz_convert("UTC")
        .dt.tz_localize(None)
        .astype("datetime64[ns]")
        .astype(np.int64)
        .to_numpy()
    )
    impact_vals = news[impact_col].values.astype(int)     # (n_events,)

    # delta_matrix[i, j] = (bar_i_time - event_j_time) in minutes
    # positive = bar is AFTER event, negative = bar is BEFORE event
    delta_matrix = (bar_ns[:, None] - event_ns[None, :]) / 1e9 / 60.0

    abs_delta = np.abs(delta_matrix)
    nearest_idx = abs_delta.argmin(axis=1)
    nearest_delta = delta_matrix[np.arange(len(df)), nearest_idx]
    nearest_impact = impact_vals[nearest_idx]

    df["news_impact_level"] = nearest_impact
    df["news_time_delta_min"] = nearest_delta.astype(float)
    df["has_news_window"] = (
        (nearest_impact >= 2) & (abs_delta[np.arange(len(df)), nearest_idx] <= window_min)
    )
    df["in_news_lockout"] = (
        (nearest_impact == 3) & (abs_delta[np.arange(len(df)), nearest_idx] <= lockout_min)
    )

    n_lockout = int(df["in_news_lockout"].sum())
    n_window = int(df["has_news_window"].sum())
    if n_lockout > 0 or n_window > 0:
        logger.info(
            "News features merged: %d bars in lockout zone, %d bars in news window",
            n_lockout, n_window,
        )

    return df


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

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

    # News features — degrades gracefully if news_events.parquet not available
    news = _load_news_events()
    if news is not None:
        df = _add_news_features(df, news)
    else:
        # Safe defaults so downstream code never KeyErrors on news columns
        df["news_impact_level"] = 0
        df["news_time_delta_min"] = np.inf
        df["has_news_window"] = False
        df["in_news_lockout"] = False

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