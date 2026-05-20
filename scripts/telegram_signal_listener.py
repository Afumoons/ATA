from __future__ import annotations

"""Telegram channel listener for external XAUUSD mentor signals.

Default mode is shadow: parse messages, write audit JSONL, and do not trade.
An auto_live mode exists, but it is guarded by ATA_TELEGRAM_SIGNAL_LIVE=true.

Required env for Telegram user-session mode:
- TELEGRAM_API_ID
- TELEGRAM_API_HASH
- TELEGRAM_SIGNAL_SESSION (optional, default: ata_telegram_signals)
"""

import argparse
import asyncio
import os
from pathlib import Path
from typing import Any

from autonomous_trading_ai.data.collector_mt5 import initialize_mt5, shutdown_mt5
from autonomous_trading_ai.execution.external_signal import (
    ExternalSignalConfig,
    append_trade_plan_audit,
    build_trade_plan,
    parse_external_signal,
)
from autonomous_trading_ai.execution.external_signal_executor import execute_external_trade_plan

DEFAULT_CHANNEL = "japsku"
DEFAULT_AUDIT_PATH = Path(__file__).resolve().parents[1] / "execution" / "external_signal_audit.jsonl"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Listen to Telegram trade signals")
    parser.add_argument("--channel", default=DEFAULT_CHANNEL, help="Telegram public channel username or link")
    parser.add_argument("--audit-path", default=str(DEFAULT_AUDIT_PATH), help="JSONL parser audit output path")
    parser.add_argument("--mode", choices=["shadow", "auto_live"], default="shadow", help="shadow logs only; auto_live also requires ATA_TELEGRAM_SIGNAL_LIVE=true")
    parser.add_argument("--history", type=int, default=0, help="Parse the last N existing messages before realtime listen")
    return parser.parse_args()


def _channel_ref(channel: str) -> str:
    channel = channel.strip()
    if channel.startswith("https://t.me/"):
        return channel.rsplit("/", 1)[-1]
    if channel.startswith("@"):
        return channel[1:]
    return channel


def _plan_from_message(message: Any, cfg: ExternalSignalConfig):
    raw = getattr(message, "raw_text", None) or getattr(message, "message", None) or ""
    msg_id = str(getattr(message, "id", "unknown"))
    date = getattr(message, "date", None)
    received_at = date.isoformat() if date is not None else None
    parsed = parse_external_signal(raw, message_id=msg_id, received_at=received_at, config=cfg)
    return build_trade_plan(parsed, config=cfg)


async def _main_async(args: argparse.Namespace) -> None:
    try:
        from telethon import TelegramClient, events
    except ImportError as exc:  # pragma: no cover - environment-dependent
        raise SystemExit(
            "Telethon is not installed. Install with: python -m pip install telethon"
        ) from exc

    api_id = os.getenv("TELEGRAM_API_ID")
    api_hash = os.getenv("TELEGRAM_API_HASH")
    if not api_id or not api_hash:
        raise SystemExit("Set TELEGRAM_API_ID and TELEGRAM_API_HASH before running this listener")

    session_name = os.getenv("TELEGRAM_SIGNAL_SESSION", "ata_telegram_signals")
    channel = _channel_ref(args.channel)
    audit_path = Path(args.audit_path)
    cfg = ExternalSignalConfig(source=f"telegram:{channel}")

    client = TelegramClient(session_name, int(api_id), api_hash)
    mt5_initialized = False
    if args.mode == "auto_live":
        initialize_mt5()
        mt5_initialized = True

    try:
        await client.start()
        entity = await client.get_entity(channel)

        if args.history > 0:
            async for message in client.iter_messages(entity, limit=args.history):
                plan = _plan_from_message(message, cfg)
                append_trade_plan_audit(plan, audit_path)
                decision = execute_external_trade_plan(plan, mode=args.mode, cfg=cfg)
                print(
                    f"history id={plan.message_id} parse={plan.decision} exec={decision.action} "
                    f"reason={decision.reason}"
                )

        @client.on(events.NewMessage(chats=entity))
        async def _handler(event):  # type: ignore[no-untyped-def]
            plan = _plan_from_message(event.message, cfg)
            append_trade_plan_audit(plan, audit_path)
            decision = execute_external_trade_plan(plan, mode=args.mode, cfg=cfg)
            print(
                "new_signal "
                f"id={plan.message_id} parse={plan.decision} exec={decision.action} "
                f"direction={plan.direction} sl={plan.stop_loss_price} "
                f"tp={plan.take_profit_price} exit={plan.exit_mode} reason={decision.reason}"
            )

        print(f"Listening to Telegram channel @{channel} in {args.mode} mode. Audit: {audit_path}")
        await client.run_until_disconnected()
    finally:
        if mt5_initialized:
            shutdown_mt5()


def main() -> None:
    args = _parse_args()
    asyncio.run(_main_async(args))


if __name__ == "__main__":
    main()
