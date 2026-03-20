from __future__ import annotations

"""data/news_collector.py

Fetches economic calendar data from Forex Factory's public JSON feed and
saves it as news_events.parquet for consumption by research/features.py.

Source: https://nfs.faireconomy.media/ff_calendar_thisweek.json
        https://nfs.faireconomy.media/ff_calendar_nextweek.json

These are the same JSON endpoints used by MT4/MT5 FF calendar indicators —
stable, no authentication required, updated in real-time.

Run via scheduler: job_update_news() once daily at 06:00 UTC.
"""

import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional
import json
import re

import requests
import pandas as pd

from ..logging_utils import get_logger

logger = get_logger(__name__)

BASE_DIR = Path(__file__).resolve().parents[1]
RAW_DIR = BASE_DIR / "data" / "raw"
NEWS_PATH = RAW_DIR / "news_events.parquet"

# Forex Factory JSON CDN endpoints
_FF_BASE = "https://nfs.faireconomy.media"
_ENDPOINTS = {
    "this_week": f"{_FF_BASE}/ff_calendar_thisweek.json",
    "next_week": f"{_FF_BASE}/ff_calendar_nextweek.json",
}

# Currencies that directly affect gold (XAUUSDm)
_RELEVANT_CURRENCIES = {"USD", "EUR", "GBP", "JPY", "CNY", "XAU"}

# Gold-specific high-impact events — always flag these regardless of FF impact level
_GOLD_KEYWORDS = {
    "non-farm", "nfp", "fomc", "federal reserve", "fed rate", "powell",
    "cpi", "inflation", "ppi", "gdp", "retail sales", "jobless",
    "unemployment", "interest rate", "monetary policy",
    "gold", "treasury", "bond", "yield",
}

_IMPACT_MAP = {
    "High":   3,
    "Medium": 2,
    "Low":    1,
    "Holiday": 0,
}

_REQUEST_TIMEOUT = 15  # seconds
_RETRY_ATTEMPTS = 3
_RETRY_DELAY = 5  # seconds


def _parse_ff_datetime(date_str: str, time_str: str) -> Optional[datetime]:
    """Parse Forex Factory date + time strings to UTC datetime.

    FF format examples:
        date: "Jan 10, 2025"
        time: "1:30pm" | "All Day" | "Tentative" | ""
    """
    try:
        dt = datetime.strptime(date_str.strip(), "%b %d, %Y")
    except ValueError:
        try:
            dt = datetime.strptime(date_str.strip(), "%B %d, %Y")
        except ValueError:
            logger.debug("Could not parse FF date: %s", date_str)
            return None

    # Parse time — default to 00:00 for all-day / tentative events
    time_str = (time_str or "").strip().lower()
    if not time_str or time_str in {"all day", "tentative", ""}:
        return dt.replace(tzinfo=timezone.utc)

    try:
        # Handle "1:30pm", "10:00am" etc.
        t = datetime.strptime(time_str, "%I:%M%p")
        dt = dt.replace(hour=t.hour, minute=t.minute, tzinfo=timezone.utc)
        # FF times are US Eastern — convert to UTC (+5h EST, +4h EDT)
        # Simple heuristic: EDT (Mar-Nov), EST (Nov-Mar)
        month = dt.month
        utc_offset = 4 if 3 <= month <= 11 else 5
        dt = dt + timedelta(hours=utc_offset)
        return dt
    except ValueError:
        # Time unparseable — return date at midnight UTC
        return dt.replace(tzinfo=timezone.utc)


def _is_gold_relevant(event: dict) -> bool:
    """Return True if event is likely to impact gold price."""
    currency = (event.get("country") or "").upper()
    if currency not in _RELEVANT_CURRENCIES:
        return False
    title = (event.get("title") or "").lower()
    if any(kw in title for kw in _GOLD_KEYWORDS):
        return True
    # Include all High-impact USD events
    impact = (event.get("impact") or "").strip()
    if currency == "USD" and impact == "High":
        return True
    return False


def _fetch_with_retry(url: str) -> Optional[list]:
    """Fetch JSON from URL with retry logic."""
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json",
    }
    for attempt in range(1, _RETRY_ATTEMPTS + 1):
        try:
            resp = requests.get(url, headers=headers, timeout=_REQUEST_TIMEOUT)
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.HTTPError as e:
            logger.warning("HTTP error fetching %s (attempt %d/%d): %s", url, attempt, _RETRY_ATTEMPTS, e)
        except requests.exceptions.RequestException as e:
            logger.warning("Request error fetching %s (attempt %d/%d): %s", url, attempt, _RETRY_ATTEMPTS, e)
        except json.JSONDecodeError as e:
            logger.warning("JSON decode error from %s: %s", url, e)
            return None
        if attempt < _RETRY_ATTEMPTS:
            time.sleep(_RETRY_DELAY)
    return None


def fetch_ff_calendar(weeks: int = 2) -> pd.DataFrame:
    """Fetch Forex Factory calendar for this week and next week.

    Returns a DataFrame with columns:
        datetime_utc  : pd.Timestamp (UTC-aware)
        currency      : str
        impact        : int (0-3)
        event_name    : str
        forecast      : str
        previous      : str
        is_gold_relevant : bool
    """
    all_events: list[dict] = []

    keys = ["this_week", "next_week"] if weeks >= 2 else ["this_week"]
    for key in keys:
        url = _ENDPOINTS[key]
        logger.info("Fetching FF calendar: %s", url)
        data = _fetch_with_retry(url)
        if data:
            all_events.extend(data)
            logger.info("Fetched %d events from %s", len(data), key)
        else:
            logger.warning("Failed to fetch FF calendar: %s", key)

    if not all_events:
        logger.error("No events fetched from Forex Factory")
        return pd.DataFrame()

    rows = []
    for ev in all_events:
        dt = _parse_ff_datetime(
            ev.get("date", ""),
            ev.get("time", ""),
        )
        if dt is None:
            continue

        impact_str = (ev.get("impact") or "").strip()
        impact_int = _IMPACT_MAP.get(impact_str, 0)
        currency = (ev.get("country") or "").upper()
        title = (ev.get("title") or "").strip()

        rows.append({
            "datetime_utc": pd.Timestamp(dt),
            "currency": currency,
            "impact": impact_int,
            "event_name": title,
            "forecast": str(ev.get("forecast") or ""),
            "previous": str(ev.get("previous") or ""),
            "is_gold_relevant": _is_gold_relevant(ev),
        })

    df = pd.DataFrame(rows)
    if df.empty:
        return df

    df = df.sort_values("datetime_utc").reset_index(drop=True)
    logger.info(
        "FF calendar: %d total events, %d gold-relevant, %d high-impact",
        len(df),
        int(df["is_gold_relevant"].sum()),
        int((df["impact"] == 3).sum()),
    )
    return df


def load_news_events() -> pd.DataFrame:
    """Load existing news events from parquet."""
    if not NEWS_PATH.exists():
        return pd.DataFrame()
    try:
        df = pd.read_parquet(NEWS_PATH)
        df["datetime_utc"] = pd.to_datetime(df["datetime_utc"], utc=True)
        return df
    except Exception:
        logger.exception("Failed to load news_events.parquet")
        return pd.DataFrame()


def save_news_events(df: pd.DataFrame) -> None:
    """Save news events to parquet."""
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    df.to_parquet(NEWS_PATH, index=False)
    logger.info("Saved %d news events to %s", len(df), NEWS_PATH)


def update_news_events() -> pd.DataFrame:
    """Fetch latest FF calendar and merge with existing data.

    Deduplicates by (datetime_utc, event_name) so re-runs are idempotent.
    Returns the merged DataFrame.
    """
    logger.info("Updating news events from Forex Factory...")

    new_df = fetch_ff_calendar(weeks=2)
    if new_df.empty:
        logger.warning("No new events fetched — keeping existing data")
        return load_news_events()

    existing = load_news_events()

    if existing.empty:
        combined = new_df
    else:
        # Drop old events that are being refreshed (same datetime+name)
        cutoff = new_df["datetime_utc"].min()
        old_events = existing[existing["datetime_utc"] < cutoff]
        combined = pd.concat([old_events, new_df], ignore_index=True)
        combined = combined.drop_duplicates(
            subset=["datetime_utc", "event_name"], keep="last"
        ).sort_values("datetime_utc").reset_index(drop=True)

    save_news_events(combined)

    # Log upcoming high-impact events (next 48h)
    now = pd.Timestamp.now(tz="UTC")
    upcoming = combined[
        (combined["datetime_utc"] >= now) &
        (combined["datetime_utc"] <= now + pd.Timedelta(hours=48)) &
        (combined["impact"] >= 2) &
        (combined["is_gold_relevant"])
    ].sort_values("datetime_utc")

    if not upcoming.empty:
        logger.info("Upcoming gold-relevant events (next 48h):")
        for _, row in upcoming.iterrows():
            logger.info(
                "  [impact=%d] %s | %s | forecast=%s prev=%s",
                row["impact"],
                row["datetime_utc"].strftime("%Y-%m-%d %H:%M UTC"),
                row["event_name"],
                row["forecast"],
                row["previous"],
            )

    return combined


def get_upcoming_high_impact(
    hours_ahead: float = 4.0,
    min_impact: int = 3,
    gold_relevant_only: bool = True,
) -> pd.DataFrame:
    """Return upcoming high-impact events within the next N hours.

    Used by scheduler to trigger WhatsApp alerts and pre-event lockouts.
    """
    df = load_news_events()
    if df.empty:
        return pd.DataFrame()

    now = pd.Timestamp.now(tz="UTC")
    mask = (
        (df["datetime_utc"] >= now) &
        (df["datetime_utc"] <= now + pd.Timedelta(hours=hours_ahead)) &
        (df["impact"] >= min_impact)
    )
    if gold_relevant_only:
        mask &= df["is_gold_relevant"]

    return df[mask].sort_values("datetime_utc").reset_index(drop=True)