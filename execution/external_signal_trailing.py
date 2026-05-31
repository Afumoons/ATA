from __future__ import annotations

"""Runtime trailing-stop maintenance for externally sourced Telegram trades.

The external signal executor can place a no-TP order whose parser plan says
``exit_mode=trailing_stop``.  MT5 does not trail stops server-side from that
metadata, so this module persists per-ticket trailing intent and periodically
moves SL via ``TRADE_ACTION_SLTP`` when price moves favorably.
"""

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Literal, Optional

try:
    import MetaTrader5 as mt5  # type: ignore
except Exception:  # pragma: no cover - optional at import time for tests/non-MT5 hosts
    mt5 = None

from ..logging_utils import get_logger

logger = get_logger(__name__)
BASE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_TRAILING_STATE = BASE_DIR / "execution" / "external_signal_trailing_state.json"
DEFAULT_TRAILING_AUDIT = BASE_DIR / "execution" / "external_signal_trailing_audit.jsonl"
Direction = Literal["long", "short"]


@dataclass(frozen=True)
class ExternalTrailingState:
    ticket: str
    signal_id: str
    source: str
    symbol: str
    direction: Direction
    entry_price: float
    current_sl: float
    trailing_stop_pips: float
    pip_size: float
    highest_price: float
    lowest_price: float
    tp: float = 0.0
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(data, indent=2, ensure_ascii=False, sort_keys=True)
    fd, tmp_path = tempfile.mkstemp(dir=path.parent, prefix=f".{path.stem}_", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(payload)
        os.replace(tmp_path, path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def _load_state(path: Path = DEFAULT_TRAILING_STATE) -> dict[str, Any]:
    if not path.exists():
        return {"positions": {}, "updated_at": None}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        logger.exception("Failed to read external trailing state %s; starting empty", path)
        return {"positions": {}, "updated_at": None}
    if not isinstance(data, dict):
        return {"positions": {}, "updated_at": None}
    positions = data.get("positions")
    if not isinstance(positions, dict):
        data["positions"] = {}
    return data


def _append_audit(row: dict[str, Any], path: Path = DEFAULT_TRAILING_AUDIT) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = dict(row)
    payload.setdefault("ts", _utc_now())
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")


def register_external_trailing_state(
    *,
    ticket: int | str,
    signal_id: str,
    source: str,
    symbol: str,
    direction: Direction,
    entry_price: float,
    initial_sl: float,
    trailing_stop_pips: float,
    pip_size: float,
    tp: float = 0.0,
    path: Path | None = None,
) -> ExternalTrailingState:
    """Persist trailing intent for a newly opened external signal position."""

    state_path = path or DEFAULT_TRAILING_STATE
    now = _utc_now()
    rec = ExternalTrailingState(
        ticket=str(ticket),
        signal_id=str(signal_id),
        source=str(source),
        symbol=str(symbol),
        direction=direction,
        entry_price=float(entry_price),
        current_sl=float(initial_sl),
        trailing_stop_pips=float(trailing_stop_pips),
        pip_size=float(pip_size),
        highest_price=float(entry_price),
        lowest_price=float(entry_price),
        tp=float(tp or 0.0),
        created_at=now,
        updated_at=now,
    )
    data = _load_state(state_path)
    positions = data.setdefault("positions", {})
    positions[str(ticket)] = rec.to_dict()
    data["updated_at"] = now
    _safe_write_json(state_path, data)
    return rec


def _position_map() -> dict[str, Any]:
    if mt5 is None:
        return {}
    positions = mt5.positions_get()
    if not positions:
        return {}
    return {str(getattr(pos, "ticket", "")): pos for pos in positions if getattr(pos, "ticket", None) is not None}


def _trade_constant(name: str) -> Any:
    if mt5 is None:
        raise RuntimeError("MetaTrader5 module is unavailable")
    return getattr(mt5, name)


def _round_price(value: float) -> float:
    return round(float(value), 5)


def _current_position_sl(pos: Any, fallback: float) -> float:
    try:
        value = float(getattr(pos, "sl", 0.0) or 0.0)
    except (TypeError, ValueError):
        value = 0.0
    return value if value > 0 else float(fallback)


def _current_position_tp(pos: Any, fallback: float) -> float:
    try:
        return float(getattr(pos, "tp", 0.0) or 0.0)
    except (TypeError, ValueError):
        return float(fallback or 0.0)


def _valid_price(value: Any) -> Optional[float]:
    try:
        price = float(value)
    except (TypeError, ValueError):
        return None
    return price if price > 0 else None


def _build_trailing_update(rec: dict[str, Any], pos: Any) -> tuple[Optional[dict[str, Any]], dict[str, Any]]:
    ticket = str(rec.get("ticket") or getattr(pos, "ticket", ""))
    symbol = str(getattr(pos, "symbol", None) or rec.get("symbol") or "")
    direction = str(rec.get("direction") or "").lower()
    pip_size = float(rec.get("pip_size") or 0.01)
    trailing_stop_pips = float(rec.get("trailing_stop_pips") or 0.0)
    distance = trailing_stop_pips * pip_size
    if not symbol or direction not in {"long", "short"} or distance <= 0:
        return None, {"reason": "invalid_state", "ticket": ticket, "symbol": symbol, "direction": direction}

    tick = mt5.symbol_info_tick(symbol) if mt5 is not None else None
    if tick is None:
        return None, {"reason": "no_tick", "ticket": ticket, "symbol": symbol}

    old_sl = _current_position_sl(pos, float(rec.get("current_sl") or 0.0))
    tp = _current_position_tp(pos, float(rec.get("tp") or 0.0))
    highest = float(rec.get("highest_price") or rec.get("entry_price") or 0.0)
    lowest = float(rec.get("lowest_price") or rec.get("entry_price") or 0.0)

    if direction == "long":
        favorable = _valid_price(getattr(tick, "bid", None))
        if favorable is None:
            return None, {"reason": "invalid_tick", "ticket": ticket, "symbol": symbol, "side": "bid"}
        highest = max(highest, favorable)
        candidate_sl = _round_price(highest - distance)
        should_update = candidate_sl > old_sl
    else:
        favorable = _valid_price(getattr(tick, "ask", None))
        if favorable is None:
            return None, {"reason": "invalid_tick", "ticket": ticket, "symbol": symbol, "side": "ask"}
        lowest = min(lowest, favorable)
        candidate_sl = _round_price(lowest + distance)
        should_update = old_sl <= 0 or candidate_sl < old_sl

    rec["highest_price"] = highest
    rec["lowest_price"] = lowest
    if not should_update:
        rec["updated_at"] = _utc_now()
        return None, {
            "reason": "no_better_sl",
            "ticket": ticket,
            "symbol": symbol,
            "old_sl": old_sl,
            "candidate_sl": candidate_sl,
            "favorable_price": favorable,
        }

    request = {
        "action": _trade_constant("TRADE_ACTION_SLTP"),
        "position": int(ticket),
        "symbol": symbol,
        "sl": candidate_sl,
        "tp": _round_price(tp) if tp else 0.0,
    }
    return request, {
        "ticket": ticket,
        "symbol": symbol,
        "direction": direction,
        "old_sl": old_sl,
        "new_sl": candidate_sl,
        "favorable_price": favorable,
        "highest_price": highest,
        "lowest_price": lowest,
    }


def update_external_signal_trailing_stops(
    *,
    path: Path | None = None,
    audit_path: Path | None = None,
) -> dict[str, int]:
    """Move SL for active external-signal trailing positions.

    Returns a compact summary with counts.  This function is safe to call from
    the scheduler every live-monitor cycle; it removes state for positions no
    longer open and only sends MT5 modifications that improve the SL.
    """

    state_path = path or DEFAULT_TRAILING_STATE
    trail_audit = audit_path or DEFAULT_TRAILING_AUDIT
    data = _load_state(state_path)
    positions_state: dict[str, dict[str, Any]] = data.setdefault("positions", {})
    summary = {"tracked": len(positions_state), "updated": 0, "skipped": 0, "errors": 0, "removed_closed": 0}
    if mt5 is None:
        if positions_state:
            summary["skipped"] = len(positions_state)
            _append_audit(
                {
                    "event": "external_trailing_skipped",
                    "reason": "mt5_unavailable",
                    "tracked": len(positions_state),
                },
                trail_audit,
            )
        return summary

    open_positions = _position_map()

    changed = False
    for ticket in list(positions_state.keys()):
        rec = positions_state[ticket]
        pos = open_positions.get(str(ticket))
        if pos is None:
            positions_state.pop(ticket, None)
            summary["removed_closed"] += 1
            changed = True
            _append_audit({"event": "external_trailing_state_removed_closed", "ticket": ticket, "signal_id": rec.get("signal_id")}, trail_audit)
            continue

        try:
            request, meta = _build_trailing_update(rec, pos)
            if request is None:
                summary["skipped"] += 1
                changed = True
                _append_audit({"event": "external_trailing_skipped", **meta}, trail_audit)
                continue
            result = mt5.order_send(request)
            if result is None:
                summary["errors"] += 1
                _append_audit({"event": "external_trailing_sl_error", **meta, "request": request, "reason": f"order_send_none:{mt5.last_error()}"}, trail_audit)
                continue
            raw_result = result._asdict() if hasattr(result, "_asdict") else {"retcode": getattr(result, "retcode", None)}
            if getattr(result, "retcode", None) != _trade_constant("TRADE_RETCODE_DONE"):
                summary["errors"] += 1
                _append_audit({"event": "external_trailing_sl_error", **meta, "request": request, "result": raw_result, "reason": f"retcode:{getattr(result, 'retcode', None)}"}, trail_audit)
                continue
            rec["current_sl"] = float(request["sl"])
            rec["tp"] = float(request.get("tp") or 0.0)
            rec["updated_at"] = _utc_now()
            positions_state[ticket] = rec
            summary["updated"] += 1
            changed = True
            _append_audit({"event": "external_trailing_sl_update", **meta, "request": request, "result": raw_result}, trail_audit)
        except Exception as exc:
            summary["errors"] += 1
            logger.exception("External signal trailing update failed for ticket=%s", ticket)
            _append_audit({"event": "external_trailing_sl_error", "ticket": ticket, "reason": str(exc)}, trail_audit)

    if changed:
        data["updated_at"] = _utc_now()
        _safe_write_json(state_path, data)
    return summary
