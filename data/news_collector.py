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

import json
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

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
_RELEVANT_CURRENCIES = {"USD", "EUR", "GBP", "JPY", "CNY", "CHF", "XAU"}

# Gold-specific keywords — flag events regardless of FF impact label
_GOLD_KEYWORDS = {
    "non-farm", "nfp", "fomc", "federal reserve", "fed rate", "powell",
    "cpi", "inflation", "core cpi", "ppi", "gdp", "retail sales", "jobless",
    "unemployment", "initial claims", "interest rate", "monetary policy",
    "quantitative", "balance sheet", "taper", "gold", "treasury", "bond",
    "yield", "ism", "pmi", "china", "geopolit",
}

_IMPACT_MAP = {
    "High":    3,
    "Medium":  2,
    "Low":     1,
    "Holiday": 0,
}

_REQUEST_TIMEOUT = 15
_RETRY_ATTEMPTS = 3
_RETRY_DELAY = 5


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _normalize_event(ev: dict) -> dict:
    """Lowercase all keys — resilient to FF field name casing changes."""
    return {k.lower(): v for k, v in ev.items()}


def _get_field(ev: dict, *candidates: str, default: str = "") -> str:
    """Return the first non-empty value among candidate field names."""
    for key in candidates:
        val = ev.get(key)
        if val is not None and str(val).strip():
            return str(val).strip()
    return default


def _parse_ff_datetime(date_str: str, time_str: str) -> Optional[datetime]:
    """Parse Forex Factory date/time fields to a UTC-aware datetime.

    Handles two formats that FF has used:

    Format A (legacy — pre-2026):
        date = "Mar 23, 2026"       (human-readable, US Eastern implied)
        time = "10:00am"            (separate field, US Eastern)

    Format B (current — 2026+):
        date = "2026-03-23T10:00:00-04:00"   (ISO 8601 with tz offset)
        time = <field absent or empty>

    Both are handled transparently. If neither parses, returns None and
    the event is silently skipped.
    """
    date_str = (date_str or "").strip()
    if not date_str:
        return None

    # --- Format B: ISO 8601 with timezone offset ---
    # Detected by presence of 'T' + timezone indicator
    if "T" in date_str and (date_str.endswith("Z") or "+" in date_str
                            or (date_str.count("-") >= 3)):
        try:
            dt = datetime.fromisoformat(date_str)
            return dt.astimezone(timezone.utc).replace(tzinfo=timezone.utc)
        except (ValueError, TypeError):
            pass
        # Fallback: strip timezone and treat as UTC
        try:
            clean = date_str[:19]  # "2026-03-23T10:00:00"
            dt = datetime.strptime(clean, "%Y-%m-%dT%H:%M:%S")
            return dt.replace(tzinfo=timezone.utc)
        except ValueError:
            pass

    # --- Format A: "Mon DD, YYYY" + separate time field ---
    for fmt in ("%b %d, %Y", "%B %d, %Y", "%m/%d/%Y"):
        try:
            dt = datetime.strptime(date_str, fmt)
            break
        except ValueError:
            continue
    else:
        logger.debug("Could not parse FF date: %r (time: %r)", date_str, time_str)
        return None

    time_str = (time_str or "").strip().lower()
    if not time_str or time_str in {"all day", "tentative", ""}:
        return dt.replace(hour=0, minute=0, tzinfo=timezone.utc)

    for fmt in ("%I:%M%p", "%I%p", "%H:%M"):
        try:
            t = datetime.strptime(time_str, fmt)
            dt = dt.replace(hour=t.hour, minute=t.minute)
            break
        except ValueError:
            continue

    # US Eastern → UTC: EDT (Mar–Nov) = UTC+4, EST (Nov–Mar) = UTC+5
    utc_offset = 4 if 3 <= dt.month <= 11 else 5
    return dt.replace(tzinfo=timezone.utc) + timedelta(hours=utc_offset)


def _is_gold_relevant(ev: dict) -> bool:
    """Return True if a (normalized, lowercase-key) event impacts gold."""
    currency = _get_field(ev, "country", "currency", "curr").upper()
    if currency not in _RELEVANT_CURRENCIES:
        return False
    title = _get_field(ev, "title", "name", "event").lower()
    # All High-impact USD events
    if currency == "USD" and _get_field(ev, "impact") == "High":
        return True
    return any(kw in title for kw in _GOLD_KEYWORDS)


def _fetch_with_retry(url: str) -> Optional[list]:
    """Fetch JSON from URL with retry + soft 404 handling."""
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/122.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json",
        "Referer": "https://www.forexfactory.com/",
    }
    for attempt in range(1, _RETRY_ATTEMPTS + 1):
        try:
            resp = requests.get(url, headers=headers, timeout=_REQUEST_TIMEOUT)

            # 404 = FF hasn't published this period yet (common on Sundays)
            if resp.status_code == 404:
                logger.warning(
                    "FF calendar endpoint not available yet (404): %s", url
                )
                return None

            resp.raise_for_status()
            return resp.json()

        except requests.exceptions.HTTPError as e:
            logger.warning(
                "HTTP error fetching %s (attempt %d/%d): %s",
                url, attempt, _RETRY_ATTEMPTS, e,
            )
        except requests.exceptions.RequestException as e:
            logger.warning(
                "Request error fetching %s (attempt %d/%d): %s",
                url, attempt, _RETRY_ATTEMPTS, e,
            )
        except json.JSONDecodeError as e:
            logger.warning("JSON decode error from %s: %s", url, e)
            return None

        if attempt < _RETRY_ATTEMPTS:
            time.sleep(_RETRY_DELAY)

    return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def fetch_ff_calendar(weeks: int = 2) -> pd.DataFrame:
    """Fetch Forex Factory calendar for this week (and optionally next week).

    Returns a DataFrame with columns:
        datetime_utc     : pd.Timestamp (UTC-aware)
        currency         : str
        impact           : int (0-3)
        event_name       : str
        forecast         : str
        previous         : str
        is_gold_relevant : bool
    """
    all_events: list[dict] = []

    keys = ["this_week", "next_week"] if weeks >= 2 else ["this_week"]
    for key in keys:
        url = _ENDPOINTS[key]
        logger.info("Fetching FF calendar: %s", url)
        data = _fetch_with_retry(url)
        if data:
            # Normalize field name casing immediately
            normalized = [_normalize_event(ev) for ev in data]
            all_events.extend(normalized)
            logger.info("Fetched %d events from %s", len(data), key)
        else:
            logger.warning("Skipped FF calendar endpoint: %s", key)

    if not all_events:
        logger.error("No events fetched from Forex Factory")
        return pd.DataFrame()

    rows = []
    skipped = 0
    for ev in all_events:
        date_val = _get_field(ev, "date", "dateline", "event_date")
        time_val = _get_field(ev, "time", "event_time")
        dt = _parse_ff_datetime(date_val, time_val)
        if dt is None:
            skipped += 1
            continue

        impact_str = _get_field(ev, "impact", "importance")
        impact_int = _IMPACT_MAP.get(impact_str, 0)
        currency   = _get_field(ev, "country", "currency", "curr").upper()
        title      = _get_field(ev, "title", "name", "event")

        rows.append({
            "datetime_utc":     pd.Timestamp(dt),
            "currency":         currency,
            "impact":           impact_int,
            "event_name":       title,
            "forecast":         _get_field(ev, "forecast", "fore"),
            "previous":         _get_field(ev, "previous", "prev"),
            "is_gold_relevant": _is_gold_relevant(ev),
        })

    if skipped:
        logger.warning(
            "Skipped %d/%d FF events — date parse failed "
            "(FF may have changed format again)",
            skipped, len(all_events),
        )

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

    Deduplicates by (datetime_utc, event_name) — idempotent on re-runs.
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
        cutoff = new_df["datetime_utc"].min()
        old_events = existing[existing["datetime_utc"] < cutoff]
        combined = pd.concat([old_events, new_df], ignore_index=True)
        combined = (
            combined
            .drop_duplicates(subset=["datetime_utc", "event_name"], keep="last")
            .sort_values("datetime_utc")
            .reset_index(drop=True)
        )

    save_news_events(combined)

    # Log upcoming high-impact gold events (next 48h)
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