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
    - risk 0.5% per signal
    - if SL is missing, use a 1000 pip default invalidation distance
    - if TP is missing, use a trailing stop with the same 1000 pip distance
    - if TP exists, full-close at TP1
    - do not skip on parser confidence, max exposure, or spread/slippage here

     ATR-based dynamic SL:
    - if sl_atr_mult is set, SL will be calculated as atr_mult * ATR instead of fixed pips
    - ATR is fetched from recent market data at execution time
    - fallback to default_sl_pips if ATR is unavailable
    """

    canonical_symbol: str = "XAUUSD"
    risk_perc: float = 0.5
    pip_size: float = 0.01
    default_sl_pips: float = 1000.0
    default_trailing_pips: float = 1000.0
    source: str = "telegram:japsku"
    # ATR multiplier for dynamic SL (e.g., 2.0 = 2x ATR)
    # If None, uses fixed default_sl_pips
    sl_atr_mult: Optional[float] = 2
    # ATR period for calculation (default 14 bars)
    atr_period: int = 14
    # Timeframe for ATR calculation (e.g., "M15", "H1", "D1")
    atr_timeframe: str = "M5"


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
    sl_pips: Optional[float]
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
_SL_PIPS_RE = re.compile(
    r"(?:\bsl\b|stop\s*loss|stoploss|stop\s*lose|stoplose|invalid(?:ation)?|cut\s*loss|cl)\D{0,24}"
    r"(\d{1,3}(?:\.\d+)?)\s*(?:pip|pips)\b",
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


def _display_xau_pips_to_internal_pips(display_pips: float, cfg: ExternalSignalConfig) -> float:
    """Convert mentor/channel XAU pip wording to internal pip-size units.

    The source channel labels a 6.00 XAUUSD move as "60.0 Pips" while the
    execution config uses a 0.01 pip size. Therefore a displayed 60-pip stop is
    600 internal sizing pips, matching explicit STOPLOSE/TAKEPROF examples.
    """

    return (display_pips * 0.1) / cfg.pip_size


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
    sl_pips = _first_float(_SL_PIPS_RE.search(text)) if sl is None else None
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
        sl_pips=sl_pips,
        tp=tp,
        notes=notes,
    )


def build_trade_plan(
    parsed: ParsedExternalSignal,
    *,
    config: ExternalSignalConfig | None = None,
    atr_value: Optional[float] = None,
) -> ExternalTradePlan:
    """Build trade plan from parsed signal.

    Args:
        parsed: Parsed external signal
        config: Signal configuration
        atr_value: Pre-fetched ATR value for dynamic SL calculation.
                   If None and sl_atr_mult is configured, will attempt to fetch.

    Returns:
        ExternalTradePlan with calculated SL/TP levels
    """
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

    # Check if using ATR-based SL
    use_atr = cfg.sl_atr_mult is not None and cfg.sl_atr_mult > 0

    if sl is None:
        explicit_sl_pips = None
        # First check for explicit pips from message
        if parsed.sl_pips is not None:
            explicit_sl_pips = _display_xau_pips_to_internal_pips(parsed.sl_pips, cfg)
            sl_mode = "explicit_pips_from_entry" if parsed.entry is not None else "explicit_pips_from_fill"
        # Then check for ATR-based SL
        elif use_atr:
            # Use provided ATR value or try to fetch
            current_atr = atr_value
            if current_atr is None:
                current_atr = fetch_atr_for_symbol(
                    cfg.canonical_symbol,
                    timeframe=cfg.atr_timeframe,
                    period=cfg.atr_period,
                )

            if current_atr is not None:
                # Convert ATR (in price units) to pips
                atr_pips = current_atr / cfg.pip_size
                explicit_sl_pips = cfg.sl_atr_mult * atr_pips
                sl_mode = "atr_based"
                notes.append(f"atr_sl_mult={cfg.sl_atr_mult} atr={current_atr:.4f}")
            else:
                # Fallback to default if ATR unavailable
                sl_mode = "default_from_entry" if parsed.entry is not None else "default_from_fill"
                notes.append("atr_unavailable_fallback_to_default")
        else:
            # Use fixed default
            sl_mode = "default_from_entry" if parsed.entry is not None else "default_from_fill"

        if parsed.entry is not None:
            sizing_pips = explicit_sl_pips if explicit_sl_pips is not None else cfg.default_sl_pips
            distance = sizing_pips * cfg.pip_size
            sl = parsed.entry - distance if parsed.direction == "long" else parsed.entry + distance
        if explicit_sl_pips is None and sl_mode != "atr_based":
            notes.append("sl_missing_default_500_pips")

    tp1 = parsed.tp[0] if parsed.tp else None
    exit_mode: ExitMode = "tp1_full_close" if tp1 is not None else "trailing_stop"
    trailing = None if tp1 is not None else cfg.default_trailing_pips
    if tp1 is None:
        notes.append("tp_missing_use_default_500_pip_trailing_stop")

    stop_pips = None
    if parsed.entry is not None and sl is not None:
        stop_pips = abs(parsed.entry - sl) / cfg.pip_size
    elif parsed.sl_pips is not None:
        stop_pips = _display_xau_pips_to_internal_pips(parsed.sl_pips, cfg)
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

def fetch_atr_for_symbol(
    symbol: str,
    timeframe: str = "H1",
    period: int = 14,
) -> Optional[float]:
    """Fetch current ATR value for a symbol using MT5.

    Args:
        symbol: Canonical symbol name (e.g., "XAUUSD")
        timeframe: Timeframe for ATR calculation (e.g., "M15", "H1", "D1")
        period: ATR period (default 14)

    Returns:
        Current ATR value in price units, or None if unavailable

    Note:
        This function requires MT5 to be initialized and connected.
        Falls back to None if MT5 is unavailable or data cannot be fetched.
    """
    try:
        import MetaTrader5 as mt5
    except ImportError:
        return None

    # Resolve broker-specific symbol
    from ..config import execution_variants_for
    variants = execution_variants_for(symbol) or [symbol]
    resolved_symbol = None
    for variant in variants:
        info = mt5.symbol_info(variant)
        if info is not None and bool(getattr(info, "visible", False)):
            resolved_symbol = variant
            break

    if resolved_symbol is None:
        # Try to select symbol
        for variant in variants:
            try:
                mt5.symbol_select(variant, True)
                info = mt5.symbol_info(variant)
                if info is not None:
                    resolved_symbol = variant
                    break
            except Exception:
                continue

    if resolved_symbol is None:
        return None

    # Map timeframe string to MT5 constant
    TIMEFRAME_MAP = {
        "M1": mt5.TIMEFRAME_M1,
        "M5": mt5.TIMEFRAME_M5,
        "M15": mt5.TIMEFRAME_M15,
        "M30": mt5.TIMEFRAME_M30,
        "H1": mt5.TIMEFRAME_H1,
        "H4": mt5.TIMEFRAME_H4,
        "D1": mt5.TIMEFRAME_D1,
    }

    mt5_tf = TIMEFRAME_MAP.get(timeframe.upper(), mt5.TIMEFRAME_H1)

    # Fetch recent bars for ATR calculation
    rates = mt5.copy_rates_from_pos(resolved_symbol, mt5_tf, 0, period + 10)
    if rates is None or len(rates) < period + 1:
        return None

    import pandas as pd
    df = pd.DataFrame(rates)

    # Calculate True Range
    high = df["high"]
    low = df["low"]
    close = df["close"]
    prev_close = close.shift(1)

    tr = pd.concat(
        [high - low, (high - prev_close).abs(), (low - prev_close).abs()],
        axis=1,
    ).max(axis=1)

    # Calculate ATR using Wilder's smoothing (EMA with alpha = 1/period)
    atr = tr.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()

    # Return the latest ATR value
    if len(atr) > 0 and not pd.isna(atr.iloc[-1]):
        return float(atr.iloc[-1])

    return None
