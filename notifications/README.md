# notifications/ – Outbound Alerts (Experimental)

## Purpose

This module is intended for **outbound notifications** from the autonomous trading
system, currently focused on WhatsApp alerts via an OpenClaw-managed webhook.

> Status (2026-03-21):
> - The plumbing from `autonomous_trading_ai` → HTTP webhook is implemented.
> - The webhook receiver (`webhook_server.py`) logs payloads to stdout.
> - The final hop from OpenClaw to WhatsApp via that webhook is **still
>   experimental** and not yet fully wired into the gateway. Treat this as a
>   best-effort alert channel, not guaranteed delivery.

## Current Scope

- `whatsapp_notifier.py`
  - Builds structured WhatsApp messages for:
    - Upcoming high-impact macro news events (gold-relevant by default).
    - Circuit breaker triggers (portfolio DD limit breached).
    - Strategy degradation events (live performance downgrades).
    - Raw manual alerts (free-text messages).
  - Sends messages to an **OpenClaw-managed outbound webhook**, which is
    expected to forward them to WhatsApp.

- `webhook_server.py`
  - A small FastAPI app that exposes `POST /hooks/whatsapp_outbound`.
  - Validates a `?token=` query parameter against the shared `WEBHOOK_TOKEN`.
  - Expects a JSON body of the form `{"to": "628170090022", "message": "..."}`.
  - Currently just prints messages to stdout as a placeholder for the real
    OpenClaw/WhatsApp integration.

## Key File: `whatsapp_notifier.py`

### Config

All configuration is via environment variables, wrapped in `NotifierConfig`:

- `OPENCLAW_WHATSAPP_WEBHOOK`
  - Base URL for the OpenClaw outbound WhatsApp webhook.
  - Example (local FastAPI receiver):
    - `http://localhost:8001/hooks/whatsapp_outbound`

- `WEBHOOK_TOKEN`
  - Shared-secret token used to secure the webhook.
  - Default: `"clio-autotrading-hooks"`.
  - The notifier automatically appends `?token=WEBHOOK_TOKEN` to the webhook
    URL if `token=` is not already present.

- `OPENCLAW_WHATSAPP_RECIPIENT`
  - WhatsApp recipient number in international format, **without** `+`.
  - Default for this deployment: `"628170090022"`.

`NotifierConfig` fields:

```python
@dataclass
class NotifierConfig:
    webhook_url: str  # from OPENCLAW_WHATSAPP_WEBHOOK
    webhook_token: str  # from WEBHOOK_TOKEN, default "clio-autotrading-hooks"
    recipient: str  # from OPENCLAW_WHATSAPP_RECIPIENT
    min_impact_for_alert: int = 3
    alert_cooldown_minutes: int = 60
    alert_before_minutes: int = 30
    request_timeout: int = 10
    retry_attempts: int = 2
```

### Core Helpers

- `_build_webhook_url(cfg)`
  - Returns `cfg.webhook_url` with `?token=...` (or `&token=...`) appended when
    `cfg.webhook_token` is set and not already present in the URL.

- `_send_openclaw_webhook(message, cfg)`
  - POSTs `{"to": cfg.recipient, "message": message}` as JSON to the built
    webhook URL.
  - Retries up to `cfg.retry_attempts` times on network/HTTP errors.

### Public Functions

- `send_whatsapp_alert(message: str, cfg=DEFAULT_CONFIG) -> bool`
  - Sends a raw text message via the configured OpenClaw webhook.

- `send_news_alert(upcoming_events: pd.DataFrame, account_info: Optional[dict], cfg) -> bool`
  - Filters upcoming macro events by `impact >= min_impact_for_alert`.
  - Applies a cooldown per event (`alert_cooldown_minutes`).
  - Only alerts events within `alert_before_minutes` of their start time.
  - Builds a formatted WhatsApp message including:
    - Event name, time, currency, forecast vs previous.
    - Optional account snapshot (`equity`, `peak`, drawdown).
  - Sends the message via `_send_openclaw_webhook`.

- `send_circuit_breaker_alert(dd_pct, equity, peak, disabled_strategies, cfg) -> bool`
  - Intended to alert when a portfolio-level circuit breaker fires.
  - Helper is implemented but **not yet wired** into `live_monitor`; currently
    circuit breaker events only disable strategies in the pool and are logged.

- `send_strategy_degradation_alert(strategy_name, recent_avg_pnl, total_pnl, new_status, cfg) -> bool`
  - Alerts when a strategy is demoted due to poor live performance.
  - Called from `_apply_live_degradation(...)` in `scheduler.main` when an
    `active` strategy is demoted to `candidate`.

## Integration Path (Current)

For this deployment, alerts are designed to flow as:

1. `autonomous_trading_ai` → `notifications.whatsapp_notifier`.
2. `whatsapp_notifier` → HTTP POST to `OPENCLAW_WHATSAPP_WEBHOOK` with `?token=WEBHOOK_TOKEN`.
3. Webhook receiver (`webhook_server.py` in this repo) logs the payload and is
   intended to forward it to OpenClaw/WhatsApp.

> **Important:** As of now, the OpenClaw gateway is **not** yet wired to accept
> this webhook and relay to WhatsApp. The module is functional up to the
> HTTP POST boundary and should be considered **experimental**.

## Gotchas / Notes

- If `OPENCLAW_WHATSAPP_WEBHOOK` or `OPENCLAW_WHATSAPP_RECIPIENT` are missing,
  the notifier logs a warning and no alert is sent.
- `requests` must be installed in the Python environment.
- Token validation is handled by the webhook receiver; this module only appends
  the token to the URL.
- Because this is an **auxiliary** channel, failures here must **never** block
  core trading logic; caller code is written to log exceptions and continue.

## Changelog (Docs)

- 2026-03-21: Updated to document `webhook_server.py`, clarified experimental
  status, and noted that circuit-breaker alerts are implemented as helpers but
  not yet wired into `live_monitor`.
