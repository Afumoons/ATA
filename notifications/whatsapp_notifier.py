from __future__ import annotations

"""notifications/whatsapp_notifier.py

Sends WhatsApp alerts via OpenClaw's outbound text skill.

OpenClaw exposes a webhook endpoint that accepts a POST request with a
message payload. Configure OPENCLAW_WEBHOOK_URL in environment variables
or directly in NotifierConfig below.

Usage:
    from notifications.whatsapp_notifier import send_whatsapp_alert
    send_whatsapp_alert("🚨 NFP in 30 minutes — trading locked")
"""

import os
import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional, List

import requests

from ..logging_utils import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

@dataclass
class NotifierConfig:
    # OpenClaw outbound WhatsApp webhook URL
    # Set via environment variable OPENCLAW_WHATSAPP_WEBHOOK or hardcode here
    webhook_url: str = field(
        default_factory=lambda: os.environ.get("OPENCLAW_WHATSAPP_WEBHOOK", "")
    )

    # Optional shared-secret token for the webhook, passed as ?token=...
    # This is kept in a separate env var so the raw URL can be reused safely.
    webhook_token: str = field(
        default_factory=lambda: os.environ.get("WEBHOOK_TOKEN", "clio-autotrading-hooks")
    )

    # WhatsApp recipient number (international format, no +)
    # Default: Afu's number for this deployment (Indonesia, 62...)
    recipient: str = field(
        default_factory=lambda: os.environ.get("OPENCLAW_WHATSAPP_RECIPIENT", "628170090022")
    )

    # Minimum impact level to send alert (2=medium, 3=high only)
    min_impact_for_alert: int = 3

    # Cooldown — don't re-alert same event within N minutes
    alert_cooldown_minutes: int = 60

    # Alert N minutes before the event
    alert_before_minutes: int = 30

    request_timeout: int = 10
    retry_attempts: int = 2


DEFAULT_CONFIG = NotifierConfig()

# In-memory cooldown tracker: event_key → last_alert_time (UTC ISO)
_alerted_events: dict[str, str] = {}


def _event_key(event_name: str, event_time: str) -> str:
    return f"{event_name}::{event_time}"


def _format_impact_emoji(impact: int) -> str:
    return {3: "🔴", 2: "🟡", 1: "🟢", 0: "⚪"}.get(impact, "⚪")


def _build_message(events: list[dict], account_info: Optional[dict] = None) -> str:
    """Build WhatsApp message text for upcoming high-impact events."""
    lines = ["📊 *Autonomous Trading AI — News Alert*", ""]

    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines.append(f"🕐 {now_str}")
    lines.append("")
    lines.append("⚠️ *Upcoming High-Impact Events (Gold-Relevant):*")
    lines.append("")

    for ev in events:
        impact = int(ev.get("impact", 0))
        emoji = _format_impact_emoji(impact)
        dt_str = ev.get("datetime_utc", "")
        if hasattr(dt_str, "strftime"):
            dt_str = dt_str.strftime("%H:%M UTC")
        else:
            dt_str = str(dt_str)

        lines.append(
            f"{emoji} *{ev.get('event_name', 'Unknown')}*"
            f"\n   🕐 {dt_str}"
            f"\n   💱 {ev.get('currency', '')}"
            f"\n   📈 Forecast: {ev.get('forecast', 'N/A')} | Prev: {ev.get('previous', 'N/A')}"
        )
        lines.append("")

    lines.append("🔒 *Trading will be paused 30 min before / 15 min after each event.*")

    if account_info:
        equity = account_info.get("equity", 0)
        peak = account_info.get("peak", 0)
        dd = (peak - equity) / peak * 100 if peak > 0 else 0
        lines.append("")
        lines.append(f"💰 Account: ${equity:,.2f} | DD from peak: {dd:.1f}%")

    return "\n".join(lines)


def _build_webhook_url(cfg: NotifierConfig) -> str:
    """Append ?token=... to webhook URL if configured and not already present."""
    base = (cfg.webhook_url or "").strip()
    if not base:
        return ""

    token = (cfg.webhook_token or "").strip()
    if not token:
        return base

    # If token already present in URL, don't duplicate
    if "token=" in base:
        return base

    separator = "&" if "?" in base else "?"
    return f"{base}{separator}token={token}"


def _send_openclaw_webhook(
    message: str,
    cfg: NotifierConfig = DEFAULT_CONFIG,
) -> bool:
    """POST message to OpenClaw WhatsApp outbound webhook.

    OpenClaw outbound text payload format (adjust if your OpenClaw
    skill uses a different schema — check your skill's input spec):
    {
        "to": "<recipient_number>",
        "message": "<text>"
    }
    """
    webhook_url = _build_webhook_url(cfg)

    if not webhook_url:
        logger.warning(
            "WhatsApp notifier: OPENCLAW_WHATSAPP_WEBHOOK not set — skipping alert"
        )
        return False

    if not cfg.recipient:
        logger.warning(
            "WhatsApp notifier: OPENCLAW_WHATSAPP_RECIPIENT not set — skipping alert"
        )
        return False

    payload = {
        "to": cfg.recipient,
        "message": message,
    }

    headers = {
        "Content-Type": "application/json",
        "User-Agent": "autonomous-trading-ai/1.0",
    }

    for attempt in range(1, cfg.retry_attempts + 1):
        try:
            resp = requests.post(
                webhook_url,
                headers=headers,
                data=json.dumps(payload),
                timeout=cfg.request_timeout,
            )
            resp.raise_for_status()
            logger.info(
                "WhatsApp alert sent successfully (attempt %d): status=%d",
                attempt,
                resp.status_code,
            )
            return True
        except requests.exceptions.HTTPError as e:
            logger.warning(
                "WhatsApp alert HTTP error (attempt %d/%d): %s",
                attempt, cfg.retry_attempts, e,
            )
        except requests.exceptions.RequestException as e:
            logger.warning(
                "WhatsApp alert request error (attempt %d/%d): %s",
                attempt, cfg.retry_attempts, e,
            )
        if attempt < cfg.retry_attempts:
            time.sleep(2)

    logger.error("WhatsApp alert failed after %d attempts", cfg.retry_attempts)
    return False


def send_whatsapp_alert(
    message: str,
    cfg: NotifierConfig = DEFAULT_CONFIG,
) -> bool:
    """Send a raw text message via OpenClaw WhatsApp."""
    return _send_openclaw_webhook(message, cfg)


def send_news_alert(
    upcoming_events: "pd.DataFrame",
    account_info: Optional[dict] = None,
    cfg: NotifierConfig = DEFAULT_CONFIG,
) -> bool:
    """Send WhatsApp alert for upcoming high-impact events.

    Respects per-event cooldown to avoid duplicate alerts.

    Parameters
    ----------
    upcoming_events : pd.DataFrame
        Output from news_collector.get_upcoming_high_impact()
    account_info : dict, optional
        {"equity": float, "peak": float} for context in alert message
    """
    import pandas as pd

    if upcoming_events is None or (hasattr(upcoming_events, "empty") and upcoming_events.empty):
        return False

    now_utc = datetime.now(timezone.utc)

    # Filter by impact threshold and cooldown
    events_to_alert = []
    for _, row in upcoming_events.iterrows():
        impact = int(row.get("impact", 0))
        if impact < cfg.min_impact_for_alert:
            continue

        dt_utc = row["datetime_utc"]
        if hasattr(dt_utc, "to_pydatetime"):
            dt_utc = dt_utc.to_pydatetime()

        # Only alert if event is within alert_before_minutes window
        minutes_to_event = (dt_utc - now_utc).total_seconds() / 60
        if minutes_to_event > cfg.alert_before_minutes:
            continue

        # Cooldown check
        key = _event_key(str(row.get("event_name", "")), str(dt_utc))
        last_alert = _alerted_events.get(key)
        if last_alert:
            last_dt = datetime.fromisoformat(last_alert)
            if (now_utc - last_dt).total_seconds() / 60 < cfg.alert_cooldown_minutes:
                logger.debug(
                    "WhatsApp alert cooldown active for event: %s", row.get("event_name")
                )
                continue

        events_to_alert.append(row.to_dict())

    if not events_to_alert:
        return False

    message = _build_message(events_to_alert, account_info=account_info)
    success = _send_openclaw_webhook(message, cfg)

    if success:
        # Mark all alerted events in cooldown tracker
        for ev in events_to_alert:
            key = _event_key(str(ev.get("event_name", "")), str(ev.get("datetime_utc", "")))
            _alerted_events[key] = now_utc.isoformat()

    return success


def send_circuit_breaker_alert(
    dd_pct: float,
    equity: float,
    peak: float,
    disabled_strategies: List[str],
    cfg: NotifierConfig = DEFAULT_CONFIG,
) -> bool:
    """Alert when portfolio circuit breaker triggers."""
    message = (
        f"🚨 *CIRCUIT BREAKER TRIGGERED*\n\n"
        f"Portfolio drawdown: {dd_pct:.1f}%\n"
        f"Equity: ${equity:,.2f} (peak: ${peak:,.2f})\n\n"
        f"Disabled {len(disabled_strategies)} active strategies:\n"
        + "\n".join(f"  • {s}" for s in disabled_strategies[:10])
        + ("\n  ..." if len(disabled_strategies) > 10 else "")
        + "\n\n⚠️ Manual review required before re-enabling."
    )
    return _send_openclaw_webhook(message, cfg)


def send_strategy_degradation_alert(
    strategy_name: str,
    recent_avg_pnl: float,
    total_pnl: float,
    new_status: str,
    cfg: NotifierConfig = DEFAULT_CONFIG,
) -> bool:
    """Alert when a strategy is demoted due to live performance degradation."""
    emoji = "⬇️" if new_status == "candidate" else "🚫"
    message = (
        f"{emoji} *Strategy Degraded: {strategy_name}*\n\n"
        f"New status: {new_status}\n"
        f"Recent avg PnL: ${recent_avg_pnl:.2f}\n"
        f"Total live PnL: ${total_pnl:.2f}\n\n"
        f"Strategy has been demoted from active pool."
    )
    return _send_openclaw_webhook(message, cfg)
