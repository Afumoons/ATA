from __future__ import annotations

"""Background service wrapper for the Telegram signal listener.

Used by scheduler.main so Telegram signal monitoring can start together with the
main ATA runtime without blocking APScheduler startup.
"""

from dataclasses import dataclass
import asyncio
import os
from pathlib import Path
import threading
from types import SimpleNamespace
from typing import Optional

from dotenv import load_dotenv

from ..logging_utils import get_logger

logger = get_logger(__name__)
BASE_DIR = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class TelegramSignalServiceHandle:
    thread: threading.Thread
    channel: str
    mode: str


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        return int(raw)
    except ValueError:
        logger.warning("Invalid %s=%r; using default %s", name, raw, default)
        return default


def telegram_signal_service_configured() -> bool:
    """Return True when enough config exists to start the listener.

    A `.env` file is loaded here because scheduler.main may be launched from a
    shell that has not exported the Telegram credentials.
    """

    load_dotenv(BASE_DIR / ".env", override=False)
    if not _env_bool("ATA_TELEGRAM_SIGNAL_AUTOSTART", True):
        logger.info("Telegram signal autostart disabled via ATA_TELEGRAM_SIGNAL_AUTOSTART")
        return False
    missing = [name for name in ("TELEGRAM_API_ID", "TELEGRAM_API_HASH") if not os.getenv(name)]
    if missing:
        logger.info("Telegram signal listener not started; missing env keys: %s", ", ".join(missing))
        return False
    return True


def start_telegram_signal_service() -> Optional[TelegramSignalServiceHandle]:
    """Start Telegram signal listener in a daemon thread when configured.

    Env knobs:
    - ATA_TELEGRAM_SIGNAL_AUTOSTART: default true; set false to disable
    - ATA_TELEGRAM_SIGNAL_CHANNEL: default japsku
    - ATA_TELEGRAM_SIGNAL_MODE: shadow|auto_live, default shadow
    - ATA_TELEGRAM_SIGNAL_HISTORY: default 0; parse last N messages on startup
    - ATA_TELEGRAM_SIGNAL_LIVE: must be true for actual auto_live orders
    """

    if not telegram_signal_service_configured():
        return None

    channel = os.getenv("ATA_TELEGRAM_SIGNAL_CHANNEL", "japsku")
    mode = os.getenv("ATA_TELEGRAM_SIGNAL_MODE", "shadow").strip().lower()
    if mode not in {"shadow", "auto_live"}:
        logger.warning("Invalid ATA_TELEGRAM_SIGNAL_MODE=%r; falling back to shadow", mode)
        mode = "shadow"
    history = _env_int("ATA_TELEGRAM_SIGNAL_HISTORY", 0)
    audit_path = str(BASE_DIR / "execution" / "external_signal_audit.jsonl")

    def _runner() -> None:
        try:
            from autonomous_trading_ai.scripts.telegram_signal_listener import _main_async

            args = SimpleNamespace(
                channel=channel,
                audit_path=audit_path,
                mode=mode,
                history=history,
                # scheduler.start_scheduler already initializes MT5. Avoid a
                # second initialize/shutdown cycle inside the listener thread.
                mt5_already_initialized=True,
            )
            asyncio.run(_main_async(args))
        except Exception:
            logger.exception("Telegram signal listener thread exited with error")

    thread = threading.Thread(
        target=_runner,
        name="telegram-signal-listener",
        daemon=True,
    )
    thread.start()
    logger.info(
        "Telegram signal listener started in background: channel=%s mode=%s history=%d live_flag=%s",
        channel,
        mode,
        history,
        os.getenv("ATA_TELEGRAM_SIGNAL_LIVE", "<unset>"),
    )
    return TelegramSignalServiceHandle(thread=thread, channel=channel, mode=mode)
