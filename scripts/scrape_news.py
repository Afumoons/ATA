"""
scrape_news.py — Standalone Forex Factory news scraper
=======================================================
Run directly: python scrape_news.py

Fetches economic calendar from Forex Factory's public JSON CDN
(same source used by MT4/MT5 FF calendar indicators) and saves
to news_events.parquet in the format expected by features.py.

Usage:
    python scrape_news.py                      # fetch this week + next week
    python scrape_news.py --weeks 4            # fetch 4 weeks ahead
    python scrape_news.py --output custom.parquet
    python scrape_news.py --csv                # also export CSV for inspection
    python scrape_news.py --show               # print table to terminal only
    python scrape_news.py --gold-only          # only gold-relevant events
    python scrape_news.py --min-impact 3       # only high-impact events
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Dependency check — give clear error if packages missing
# ---------------------------------------------------------------------------
try:
    import requests
except ImportError:
    print("ERROR: 'requests' not installed. Run: pip install requests")
    sys.exit(1)

try:
    import pandas as pd
except ImportError:
    print("ERROR: 'pandas' not installed. Run: pip install pandas")
    sys.exit(1)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_OUTPUT = Path(__file__).resolve().parent / "news_events.parquet"

FF_ENDPOINTS = {
    "this_week":  "https://nfs.faireconomy.media/ff_calendar_thisweek.json",
    "next_week":  "https://nfs.faireconomy.media/ff_calendar_nextweek.json",
    "last_week":  "https://nfs.faireconomy.media/ff_calendar_lastweek.json",
}

# Currencies with direct gold price impact
GOLD_CURRENCIES = {"USD", "EUR", "GBP", "JPY", "CNY", "CHF", "XAU"}

# Title keywords that flag gold-relevant events regardless of currency
GOLD_KEYWORDS = {
    "non-farm", "nfp", "fomc", "federal reserve", "fed rate", "powell",
    "cpi", "inflation", "core cpi", "ppi", "gdp", "retail sales",
    "jobless", "unemployment", "initial claims", "interest rate",
    "monetary policy", "quantitative", "balance sheet", "taper",
    "gold", "treasury", "bond", "yield", "ism", "pmi",
    "china", "geopolit",
}

IMPACT_MAP = {"High": 3, "Medium": 2, "Low": 1, "Holiday": 0}
IMPACT_LABEL = {3: "HIGH", 2: "MED", 1: "LOW", 0: "HOL"}
IMPACT_COLOR = {3: "\033[91m", 2: "\033[93m", 1: "\033[92m", 0: "\033[90m"}
RESET = "\033[0m"

REQUEST_TIMEOUT = 15
RETRY_ATTEMPTS = 3
RETRY_DELAY = 4


# ---------------------------------------------------------------------------
# Fetch
# ---------------------------------------------------------------------------

def _fetch_json(url: str) -> Optional[list]:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/122.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json, text/plain, */*",
        "Referer": "https://www.forexfactory.com/",
    }
    for attempt in range(1, RETRY_ATTEMPTS + 1):
        try:
            resp = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT)

            # 404 means FF hasn't published this week's calendar yet
            # (common on Sundays before the update). Treat as soft skip.
            if resp.status_code == 404:
                print(f"  Not available yet (404) — FF may not have published this period yet")
                return None

            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.HTTPError as e:
            print(f"  HTTP error (attempt {attempt}/{RETRY_ATTEMPTS}): {e}")
        except requests.exceptions.ConnectionError as e:
            print(f"  Connection error (attempt {attempt}/{RETRY_ATTEMPTS}): {e}")
        except requests.exceptions.Timeout:
            print(f"  Timeout (attempt {attempt}/{RETRY_ATTEMPTS})")
        except json.JSONDecodeError as e:
            print(f"  JSON parse error: {e}")
            return None

        if attempt < RETRY_ATTEMPTS:
            print(f"  Retrying in {RETRY_DELAY}s...")
            time.sleep(RETRY_DELAY)

    print(f"  Failed after {RETRY_ATTEMPTS} attempts: {url}")
    return None


def _parse_ff_datetime(date_str: str, time_str: str) -> Optional[datetime]:
    """Parse Forex Factory date/time fields to UTC datetime.

    FF has used two formats historically:

    Format A (old — pre-2026):
        date = "Mar 23, 2026"
        time = "10:00am"  (US Eastern, separate field)

    Format B (new — 2026+):
        date = "2026-03-23T10:00:00-04:00"  (ISO 8601 with tz offset)
        time = <field absent>

    This function handles both automatically.
    """
    date_str = (date_str or "").strip()

    # --- Format B: ISO 8601 with timezone offset (new FF format) ---
    # Example: "2026-03-23T10:00:00-04:00"
    if "T" in date_str and ("+" in date_str or date_str.count("-") >= 3):
        try:
            # Python 3.7+ fromisoformat handles offset-aware strings
            dt = datetime.fromisoformat(date_str)
            # Convert to UTC
            return dt.astimezone(timezone.utc).replace(tzinfo=timezone.utc)
        except (ValueError, TypeError):
            pass

    # --- Format A: old "Mon DD, YYYY" + separate time field ---
    time_str = (time_str or "").strip().lower()

    for fmt in ("%b %d, %Y", "%B %d, %Y", "%m/%d/%Y"):
        try:
            dt = datetime.strptime(date_str, fmt)
            break
        except ValueError:
            continue
    else:
        return None

    if not time_str or time_str in {"all day", "tentative", ""}:
        return dt.replace(hour=0, minute=0, tzinfo=timezone.utc)

    for fmt in ("%I:%M%p", "%I%p", "%H:%M"):
        try:
            t = datetime.strptime(time_str, fmt)
            dt = dt.replace(hour=t.hour, minute=t.minute)
            break
        except ValueError:
            continue

    # EST vs EDT offset
    utc_offset = 4 if 3 <= dt.month <= 11 else 5
    return (dt.replace(tzinfo=timezone.utc) + timedelta(hours=utc_offset))


def _normalize_event(ev: dict) -> dict:
    """Lowercase all keys so parsing is resilient to FF field name changes."""
    return {k.lower(): v for k, v in ev.items()}


def _get_field(ev: dict, *candidates: str, default: str = "") -> str:
    """Return the first non-empty value among candidate field names."""
    for key in candidates:
        val = ev.get(key)
        if val is not None and str(val).strip():
            return str(val).strip()
    return default


def _is_gold_relevant(ev: dict) -> bool:
    """Check gold relevance on a normalized (lowercase-key) event dict."""
    currency = _get_field(ev, "country", "currency", "curr").upper()
    if currency not in GOLD_CURRENCIES:
        return False
    title = _get_field(ev, "title", "name", "event").lower()
    if currency == "USD" and _get_field(ev, "impact") == "High":
        return True
    return any(kw in title for kw in GOLD_KEYWORDS)


def fetch_calendar(
    weeks: int = 2,
    include_last: bool = False,
    debug: bool = False,
) -> pd.DataFrame:
    """Fetch FF calendar for the specified number of weeks ahead."""
    keys = []
    if include_last:
        keys.append("last_week")
    keys.append("this_week")
    if weeks >= 2:
        keys.append("next_week")

    all_events: list[dict] = []
    for key in keys:
        url = FF_ENDPOINTS[key]
        print(f"Fetching {key}: {url}")
        data = _fetch_json(url)
        if data:
            normalized = [_normalize_event(ev) for ev in data]
            all_events.extend(normalized)
            print(f"  → {len(data)} events")
            if debug and data:
                print(f"  [debug] field names: {list(normalized[0].keys())}")
                print(f"  [debug] first event: {normalized[0]}")
        else:
            print(f"  → skipped")

    if not all_events:
        print("\nNo events fetched. Check your internet connection.")
        return pd.DataFrame()

    rows = []
    skipped = 0
    skipped_sample: Optional[dict] = None

    for ev in all_events:
        date_val = _get_field(ev, "date", "dateline", "event_date", "eventdate")
        time_val = _get_field(ev, "time", "event_time", "eventtime")
        dt = _parse_ff_datetime(date_val, time_val)

        if dt is None:
            skipped += 1
            if skipped_sample is None:
                skipped_sample = ev
            continue

        impact_str = _get_field(ev, "impact", "importance", "impactclass")
        impact_int = IMPACT_MAP.get(impact_str, 0)
        currency   = _get_field(ev, "country", "currency", "curr").upper()
        title      = _get_field(ev, "title", "name", "event")

        rows.append({
            "datetime_utc":     pd.Timestamp(dt),
            "currency":         currency,
            "impact":           impact_int,
            "impact_label":     impact_str,
            "event_name":       title,
            "forecast":         _get_field(ev, "forecast", "fore"),
            "previous":         _get_field(ev, "previous", "prev"),
            "actual":           _get_field(ev, "actual", "act"),
            "is_gold_relevant": _is_gold_relevant(ev),
        })

    if skipped:
        print(f"  (skipped {skipped}/{len(all_events)} events — date parse failed)")

    df = pd.DataFrame(rows)

    if df.empty and all_events:
        first = all_events[0]
        print(f"\n[!] All {len(all_events)} events failed date parsing.")
        print(f"    FF may have changed their JSON structure.")
        first = all_events[0]
        date_v = first.get("date", "<missing>")
        time_v = first.get("time", "<missing>")
        print(f"\n[!] All {len(all_events)} events failed date parsing.")
        print(f"    FF may have changed their JSON structure.")
        print(f"    First event field names : {list(first.keys())}")
        print(f"    date field value        : {date_v!r}")
        print(f"    time field value        : {time_v!r}")
        if skipped_sample:
            print(f"    Full first skipped event: {skipped_sample}")
        print("\n    Run with --debug for full event dump")
        return df

    df = df.sort_values("datetime_utc").reset_index(drop=True)
    return df


# ---------------------------------------------------------------------------
# Display
# ---------------------------------------------------------------------------

def _impact_str(impact: int, color: bool = True) -> str:
    label = IMPACT_LABEL.get(impact, "???")
    if not color:
        return label
    c = IMPACT_COLOR.get(impact, "")
    return f"{c}{label}{RESET}"


def print_table(
    df: pd.DataFrame,
    gold_only: bool = False,
    min_impact: int = 0,
    upcoming_only: bool = False,
    color: bool = True,
) -> None:
    now = pd.Timestamp.now(tz="UTC")

    filtered = df.copy()
    if gold_only:
        filtered = filtered[filtered["is_gold_relevant"] == True]
    if min_impact > 0:
        filtered = filtered[filtered["impact"] >= min_impact]
    if upcoming_only:
        filtered = filtered[filtered["datetime_utc"] >= now]

    if filtered.empty:
        print("No events match the filter criteria.")
        return

    # Header
    print(f"\n{'─'*90}")
    print(f"{'DATE/TIME (UTC)':<22} {'IMP':<5} {'CURR':<5} {'EVENT':<38} {'FORE':<8} {'PREV':<8} GOLD")
    print(f"{'─'*90}")

    for _, row in filtered.iterrows():
        dt = row["datetime_utc"]
        dt_str = dt.strftime("%Y-%m-%d %H:%M") if pd.notna(dt) else "?"

        # Highlight upcoming events
        is_future = dt >= now if pd.notna(dt) else False
        is_soon = is_future and (dt - now).total_seconds() < 3600  # within 1h
        prefix = "\033[1m" if is_soon and color else ""
        suffix = RESET if is_soon and color else ""

        imp = _impact_str(int(row["impact"]), color)
        gold = "★" if row.get("is_gold_relevant") else " "
        event = str(row["event_name"])[:37]
        fore = str(row["forecast"])[:7]
        prev = str(row["previous"])[:7]
        curr = str(row["currency"])[:4]

        print(
            f"{prefix}{dt_str:<22}{suffix} "
            f"{imp:<14} {curr:<5} {event:<38} {fore:<8} {prev:<8} {gold}"
        )

    print(f"{'─'*90}")
    print(
        f"Total: {len(filtered)} events | "
        f"Gold-relevant: {int(filtered['is_gold_relevant'].sum())} | "
        f"High-impact: {int((filtered['impact'] == 3).sum())}"
    )


def print_upcoming_summary(df: pd.DataFrame, hours: float = 24.0) -> None:
    """Print a focused summary of upcoming high-impact events."""
    now = pd.Timestamp.now(tz="UTC")
    cutoff = now + pd.Timedelta(hours=hours)

    upcoming = df[
        (df["datetime_utc"] >= now) &
        (df["datetime_utc"] <= cutoff) &
        (df["impact"] >= 2) &
        (df["is_gold_relevant"] == True)
    ].sort_values("datetime_utc")

    if upcoming.empty:
        print(f"\n✓  No gold-relevant events with impact≥2 in the next {hours:.0f}h")
        return

    print(f"\n⚠  Upcoming gold-relevant events (next {hours:.0f}h):")
    print(f"{'─'*70}")
    for _, row in upcoming.iterrows():
        dt = row["datetime_utc"]
        delta_min = (dt - now).total_seconds() / 60
        delta_str = f"in {delta_min:.0f}m" if delta_min < 60 else f"in {delta_min/60:.1f}h"
        imp = _impact_str(int(row["impact"]), color=True)
        print(
            f"  {imp}  {dt.strftime('%Y-%m-%d %H:%M UTC')} ({delta_str})"
            f"  {row['currency']}  {row['event_name']}"
            f"  | fore={row['forecast'] or '?'} prev={row['previous'] or '?'}"
        )
    print(f"{'─'*70}")


# ---------------------------------------------------------------------------
# Save
# ---------------------------------------------------------------------------

def load_existing(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    try:
        df = pd.read_parquet(path)
        df["datetime_utc"] = pd.to_datetime(df["datetime_utc"], utc=True)
        print(f"Loaded {len(df)} existing events from {path}")
        return df
    except Exception as e:
        print(f"Warning: could not load existing file ({e}) — starting fresh")
        return pd.DataFrame()


def merge_and_save(
    new_df: pd.DataFrame,
    path: Path,
    also_csv: bool = False,
) -> pd.DataFrame:
    existing = load_existing(path)

    if existing.empty:
        combined = new_df
    else:
        # Drop anything newer than our earliest new event (will be refreshed)
        cutoff = new_df["datetime_utc"].min()
        old = existing[existing["datetime_utc"] < cutoff]
        combined = pd.concat([old, new_df], ignore_index=True)
        combined = (
            combined
            .drop_duplicates(subset=["datetime_utc", "event_name"], keep="last")
            .sort_values("datetime_utc")
            .reset_index(drop=True)
        )

    # Ensure output directory exists
    path.parent.mkdir(parents=True, exist_ok=True)
    combined.to_parquet(path, index=False)
    print(f"\nSaved {len(combined)} events → {path}")

    if also_csv:
        csv_path = path.with_suffix(".csv")
        combined.to_csv(csv_path, index=False)
        print(f"Also saved CSV  → {csv_path}")

    return combined


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Forex Factory economic calendar scraper",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument(
        "--weeks", type=int, default=2, metavar="N",
        help="Number of weeks to fetch (1=this week only, 2=+next week). Default: 2",
    )
    p.add_argument(
        "--include-last", action="store_true",
        help="Also fetch last week (useful for backfilling recent events)",
    )
    p.add_argument(
        "--output", type=Path, default=DEFAULT_OUTPUT, metavar="PATH",
        help=f"Output parquet path. Default: {DEFAULT_OUTPUT}",
    )
    p.add_argument(
        "--csv", action="store_true",
        help="Also export a CSV alongside the parquet for easy inspection",
    )
    p.add_argument(
        "--show", action="store_true",
        help="Print table to terminal only — do not save to disk",
    )
    p.add_argument(
        "--gold-only", action="store_true",
        help="Filter output to gold-relevant events only",
    )
    p.add_argument(
        "--min-impact", type=int, default=0, choices=[0, 1, 2, 3], metavar="N",
        help="Minimum impact level to display/save (0=all, 1=low+, 2=med+, 3=high only)",
    )
    p.add_argument(
        "--upcoming", type=float, default=24.0, metavar="HOURS",
        help="Show summary of upcoming events in next N hours. Default: 24",
    )
    p.add_argument(
        "--no-color", action="store_true",
        help="Disable terminal color codes",
    )
    p.add_argument(
        "--debug", action="store_true",
        help="Print raw FF event structure to diagnose format changes",
    )
    return p.parse_args()


def main() -> None:
    args = parse_args()
    color = not args.no_color and sys.stdout.isatty()

    print("=" * 60)
    print(" Forex Factory Calendar Scraper")
    print(f" {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    print("=" * 60)

    # Fetch
    df = fetch_calendar(weeks=args.weeks, include_last=args.include_last, debug=args.debug)

    if df.empty:
        print("\nNo data fetched. Exiting.")
        sys.exit(1)

    print(f"\nFetched {len(df)} total events")
    print(f"  Gold-relevant : {int(df['is_gold_relevant'].sum())}")
    print(f"  High-impact   : {int((df['impact'] == 3).sum())}")
    print(f"  Date range    : {df['datetime_utc'].min().strftime('%Y-%m-%d')} "
          f"→ {df['datetime_utc'].max().strftime('%Y-%m-%d')}")

    # Upcoming summary
    print_upcoming_summary(df, hours=args.upcoming)

    # Full table
    print_table(
        df,
        gold_only=args.gold_only,
        min_impact=args.min_impact,
        color=color,
    )

    # Save unless --show only
    if not args.show:
        merge_and_save(df, path=args.output, also_csv=args.csv)
    else:
        print("\n(--show mode: file not saved)")


if __name__ == "__main__":
    main()