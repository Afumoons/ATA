# News Events Data Schema

This file documents the expected schema for macro news events used by
`autonomous_trading_ai`.

News events should be stored under:

- `data/raw/news_events.parquet` (per-symbol filtering happens in code)

## Columns

- `time` (datetime, UTC)
  - Timestamp of the news release.
- `currency` (string)
  - Affected currency, e.g. "USD", "EUR", "XAU".
- `impact` (string)
  - Categorical impact level: "low", "medium", "high".
- `event_name` (string)
  - Short name of the macro event, e.g. "FOMC", "CPI", "NFP".
- `actual` (float | null)
  - Actual released value (if available).
- `forecast` (float | null)
  - Market consensus forecast (if available).
- `previous` (float | null)
  - Previous value (if available).
- `surprise` (float | null)
  - Optional precomputed surprise = actual - forecast (or normalized).

## Derived feature columns

When computing features, the following columns may be added to the
per-symbol feature DataFrame:

- `has_news_window` (bool)
  - True if there is a news event within a configurable time window
    around the bar time (e.g. +/- 30 minutes).
- `news_impact_level` (int)
  - Encoded impact: 0 = none, 1 = low, 2 = medium, 3 = high.
- `news_time_delta_min` (float)
  - Minutes to the nearest news event (negative = before, positive = after).
- `news_surprise` (float | null)
  - Surprise value of the nearest event, if available.
- `in_news_lockout` (bool)
  - True if trading should be avoided for this bar due to a high-impact
    event proximity (policy-dependent).

This schema is intentionally simple and broker/venue agnostic. A separate
collector script is expected to fetch macro events from an external
calendar API and store them into `data/raw/news_events.parquet` using
this layout.
