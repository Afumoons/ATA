from __future__ import annotations

"""Parse and plan externally-sourced trade signals.

This module is intentionally side-effect free: it does not read Telegram and it
never sends broker orders.  It converts noisy mentor/channel messages into a
small auditable trade plan that a separate runner can execute in shadow,
semi-auto, or live mode.
"""

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import hashlib
import json
import re
from pathlib import Path
from typing import Any, Literal, Optional

from ..config import execution_config

Direction = Literal["long", "short"]
ExitMode = Literal["tp1_full_close", "trailing_stop"]
Decision = Literal["planned", "ignored", "rejected"]


@dataclass(frozen=True)
class ExternalSignalConfig:
    """Deployment defaults for Telegram mentor signals.

    Afu's current rules:
    - trade XAUUSD only and let ATA resolve broker suffixes (XAUUSDm, etc.)
    - risk 1% per signal
    - if SL is missing, use a 500 pip default invalidation distance
    - if TP is missing, use a trailing stop with the same 500 pip distance
    - if TP exists, full-close at TP1
    - do not skip on parser confidence, max exposure, or spread/slippage here
    """

    canonical_symbol: str = "XAUUSD"
    risk_perc: float = 1.0
    pip_size: float = 0.01
    default_sl_pips: float = 500.0
    default_trailing_pips: float = 500.0
    source: str = "telegram:japsku"


@dataclass(frozen=True)
class ParsedExternalSignal:
    source: str
    message_id: str
    received_at: str
    raw_message: str
    direction: Optional[Direction]
    symbol: str
    entry: Optional[float]
    sl: Optional[float]
    tp: list[float] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ExternalTradePlan:
    decision: Decision
    reason: str
    signal_id: str
    source: str
    message_id: str
    raw_message: str
    symbol: str
    direction: Optional[Direction]
    risk_perc: float
    entry_reference: Optional[float]
    stop_loss_price: Optional[float]
    stop_loss_mode: str
    take_profit_price: Optional[float]
    exit_mode: Optional[ExitMode]
    trailing_stop_pips: Optional[float]
    pip_size: float
    stop_loss_pips_for_sizing: Optional[float]
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


_NUMBER_RE = re.compile(r"(?<!\d)(\d{3,5}(?:\.\d+)?)(?!\d)")
_DIRECTION_RE = re.compile(r"\b(bu+y+|long|se+l+|short)\b", re.IGNORECASE)
_SL_RE = re.compile(
    r"(?:\bsl\b|stop\s*loss|stoploss|stop\s*lose|stoplose|invalid(?:ation)?|cut\s*loss|cl)\D{0,24}"
    r"(\d{3,5}(?:\.\d+)?)",
    re.IGNORECASE,
)
_TP_RE = re.compile(
    r"(?:\btp\s*\d*\b|take\s*profit|takeprofit|take\s*prof|takeprof|target)\D{0,24}(\d{3,5}(?:\.\d+)?)",
    re.IGNORECASE,
)
_ENTRY_RE = re.compile(
    r"(?:entry|open|price|area|zone|now|@)\D{0,24}(\d{3,5}(?:\.\d+)?)",
    re.IGNORECASE,
)
_SYMBOL_RE = re.compile(r"\b(xauusd[a-z]*|xau|gold)\b", re.IGNORECASE)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _signal_id(source: str, message_id: str, raw_message: str) -> str:
    base = f"{source}|{message_id}|{raw_message.strip()}".encode("utf-8", errors="ignore")
    return hashlib.sha256(base).hexdigest()[:16]


def _first_float(match: Optional[re.Match[str]]) -> Optional[float]:
    if match is None:
        return None
    try:
        return float(match.group(1))
    except (TypeError, ValueError):
        return None


def _numbers(raw_message: str) -> list[float]:
    out: list[float] = []
    for item in _NUMBER_RE.findall(raw_message):
        try:
            out.append(float(item))
        except ValueError:
            continue
    return out


def parse_external_signal(
    raw_message: str,
    *,
    message_id: str,
    received_at: Optional[str] = None,
    config: ExternalSignalConfig | None = None,
) -> ParsedExternalSignal:
    """Best-effort parser for changing XAUUSD signal text formats.

    The parser deliberately extracts a plan candidate even when TP/SL are
    missing, because defaults are applied by :func:`build_trade_plan`.
    """

    cfg = config or ExternalSignalConfig()
    text = raw_message.strip()
    notes: list[str] = []

    direction_match = _DIRECTION_RE.search(text)
    direction: Optional[Direction] = None
    if direction_match:
        word = direction_match.group(1).lower()
        direction = "long" if word.startswith("b") or word == "long" else "short"
    else:
        notes.append("no_direction_detected")

    if not _SYMBOL_RE.search(text):
        notes.append("symbol_not_explicit_using_config_canonical_xauusd")

    entry = _first_float(_ENTRY_RE.search(text))
    sl = _first_float(_SL_RE.search(text))
    tp = [float(x) for x in _TP_RE.findall(text)]

    if entry is None and direction_match:
        # Common format: "BUY XAUUSD 4500" / "Sell gold 4498-4500".
        tail = text[direction_match.end() :]
        vals = _numbers(tail)
        if vals:
            entry = vals[0]

    return ParsedExternalSignal(
        source=cfg.source,
        message_id=str(message_id),
        received_at=received_at or _utc_now(),
        raw_message=text,
        direction=direction,
        symbol=cfg.canonical_symbol,
        entry=entry,
        sl=sl,
        tp=tp,
        notes=notes,
    )


def build_trade_plan(
    parsed: ParsedExternalSignal,
    *,
    config: ExternalSignalConfig | None = None,
) -> ExternalTradePlan:
    cfg = config or ExternalSignalConfig()
    signal_id = _signal_id(parsed.source, parsed.message_id, parsed.raw_message)
    notes = list(parsed.notes)

    if parsed.direction is None:
        return ExternalTradePlan(
            decision="ignored",
            reason="no buy/sell direction detected",
            signal_id=signal_id,
            source=parsed.source,
            message_id=parsed.message_id,
            raw_message=parsed.raw_message,
            symbol=cfg.canonical_symbol,
            direction=None,
            risk_perc=cfg.risk_perc,
            entry_reference=parsed.entry,
            stop_loss_price=None,
            stop_loss_mode="none",
            take_profit_price=None,
            exit_mode=None,
            trailing_stop_pips=None,
            pip_size=cfg.pip_size,
            stop_loss_pips_for_sizing=None,
            notes=notes,
        )

    sl = parsed.sl
    sl_mode = "explicit"
    if sl is None:
        sl_mode = "default_from_entry" if parsed.entry is not None else "default_from_fill"
        if parsed.entry is not None:
            distance = cfg.default_sl_pips * cfg.pip_size
            sl = parsed.entry - distance if parsed.direction == "long" else parsed.entry + distance
        notes.append("sl_missing_default_500_pips")

    tp1 = parsed.tp[0] if parsed.tp else None
    exit_mode: ExitMode = "tp1_full_close" if tp1 is not None else "trailing_stop"
    trailing = None if tp1 is not None else cfg.default_trailing_pips
    if tp1 is None:
        notes.append("tp_missing_use_default_500_pip_trailing_stop")

    stop_pips = None
    if parsed.entry is not None and sl is not None:
        stop_pips = abs(parsed.entry - sl) / cfg.pip_size
    elif sl_mode == "default_from_fill":
        stop_pips = cfg.default_sl_pips

    if sl is not None and parsed.entry is not None:
        invalid = parsed.direction == "long" and sl >= parsed.entry
        invalid = invalid or (parsed.direction == "short" and sl <= parsed.entry)
        if invalid:
            return ExternalTradePlan(
                decision="rejected",
                reason="stop loss is on the wrong side of entry reference",
                signal_id=signal_id,
                source=parsed.source,
                message_id=parsed.message_id,
                raw_message=parsed.raw_message,
                symbol=cfg.canonical_symbol,
                direction=parsed.direction,
                risk_perc=cfg.risk_perc,
                entry_reference=parsed.entry,
                stop_loss_price=sl,
                stop_loss_mode=sl_mode,
                take_profit_price=tp1,
                exit_mode=exit_mode,
                trailing_stop_pips=trailing,
                pip_size=cfg.pip_size,
                stop_loss_pips_for_sizing=stop_pips,
                notes=notes,
            )

    return ExternalTradePlan(
        decision="planned",
        reason="ok",
        signal_id=signal_id,
        source=parsed.source,
        message_id=parsed.message_id,
        raw_message=parsed.raw_message,
        symbol=cfg.canonical_symbol,
        direction=parsed.direction,
        risk_perc=cfg.risk_perc,
        entry_reference=parsed.entry,
        stop_loss_price=sl,
        stop_loss_mode=sl_mode,
        take_profit_price=tp1,
        exit_mode=exit_mode,
        trailing_stop_pips=trailing,
        pip_size=cfg.pip_size,
        stop_loss_pips_for_sizing=stop_pips,
        notes=notes,
    )


def append_trade_plan_audit(plan: ExternalTradePlan, path: Path | None = None) -> None:
    """Append one JSONL audit row for parser/execution review."""

    audit_path = path or (Path(__file__).resolve().parent / "external_signal_audit.jsonl")
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    with audit_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(plan.to_dict(), ensure_ascii=False, sort_keys=True) + "\n")


def pips_between(a: float, b: float, *, pip_size: float = 0.01) -> float:
    return abs(a - b) / pip_size


def resolve_default_pip_value(symbol: str) -> float:
    if symbol in execution_config.default_pip_value_per_lot:
        return execution_config.default_pip_value_per_lot[symbol]
    for prefix in execution_config.metals_prefixes:
        if symbol.startswith(prefix):
            return 1.0
    return 10.0
