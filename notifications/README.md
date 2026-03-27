# notifications/ – Outbound Alerts (Best-Effort)

## Purpose

This module provides **outbound alerting** for the autonomous trading system.

Right now it is focused on **WhatsApp-style alerts via webhook handoff**.
It is intentionally treated as:

- useful
- operationally valuable
- non-critical to trading correctness

Core trading must continue even if notifications fail.

## Current Scope

This module currently covers:

- formatted news alerts for upcoming macro events
- strategy degradation alerts
- manual/raw text alerts
- webhook delivery plumbing for outbound handoff

It does **not** own the final message transport network by itself; instead, it
hands messages off to a webhook receiver / gateway path.

## Key Files

### `whatsapp_notifier.py`

Main notification builder + sender.

Responsibilities:

- build formatted outbound messages
- attach recipient and tokenized webhook target
- POST payloads to the configured outbound webhook
- retry transient failures conservatively
- keep failures isolated from core trading logic

Supported alert patterns include:

- upcoming high-impact macro news
- strategy degradation / demotion events
- circuit-breaker-related alert helpers
- free-text manual alerts

### `webhook_server.py` (project root)

Not inside this folder, but part of the same outbound-alert story.

This FastAPI app exposes:

- `POST /hooks/whatsapp_outbound`

It validates a shared token and currently acts as a lightweight receiver /
placeholder integration point.

## Delivery Model

Current intended path:

1. trading module decides an alert should be sent
2. `notifications.whatsapp_notifier` formats the message
3. notifier POSTs JSON to the configured webhook URL
4. webhook receiver / gateway handles the final handoff to messaging infra

This is why the module should be viewed as **best-effort** rather than a
hard-guaranteed delivery layer.

## Configuration

The notifier is configured via environment variables wrapped by
`NotifierConfig`.

Important inputs include:

- `OPENCLAW_WHATSAPP_WEBHOOK`
- `WEBHOOK_TOKEN`
- `OPENCLAW_WHATSAPP_RECIPIENT`

Typical knobs also include:

- minimum impact for alerts
- cooldown minutes
- lead time before event alerts
- request timeout
- retry count

## Pass 3 Relevance

Pass 3 increases the operational value of alerts because the system now has
more meaningful live-state transitions worth surfacing, especially:

- imminent macro events affecting execution lockout
- live degradation events when an `active` strategy is demoted
- potential circuit-breaker events or related operator-facing warnings

This module is still intentionally separated from core execution so alert
failures do not interfere with safety or order routing.

## How It’s Used

### News flow

- `scheduler.job_update_news()` and `job_news_alert()` may call
  `send_news_alert(...)`
- the notifier filters to relevant/high-impact events and applies cooldowns

### Strategy degradation flow

- scheduler degradation logic calls `send_strategy_degradation_alert(...)`
  when a strategy is explicitly downgraded due to poor live performance

### Manual/raw alerts

- callers can use `send_whatsapp_alert(...)` for generic text alerts

## Gotchas / Notes

- If webhook URL or recipient config is missing, the module should log and no-op
  rather than break trading.
- This module depends on outbound HTTP access and `requests` availability.
- Token handling secures the handoff path, but end-to-end delivery still depends
  on the external receiver/gateway wiring.
- Circuit-breaker alert helpers may exist before every final integration path is
  wired; documentation should reflect actual usage rather than intended usage.

## Changelog (Docs)

- 2026-03-21: Documented webhook-based WhatsApp alerting and clarified the
  experimental status.
- 2026-03-27: Refreshed for pass 3 to frame notifications as best-effort
  operational alerts for macro events, degradation, and live-state transitions.