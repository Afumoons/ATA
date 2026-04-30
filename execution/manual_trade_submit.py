from __future__ import annotations

from typing import Any, Dict, Mapping

import MetaTrader5 as mt5

from ..config import execution_config
from .manual_trade_broker_validation import build_manual_trade_mt5_request, classify_manual_trade_mt5_failure

_SUCCESS_RETCODES = {
    0,
    int(getattr(mt5, "TRADE_RETCODE_DONE", 10009)),
    int(getattr(mt5, "TRADE_RETCODE_PLACED", 10008)),
}


def _raw_result_to_dict(result: Any) -> Dict[str, Any]:
    if result is None:
        return {}
    raw_result = result._asdict() if hasattr(result, "_asdict") else dict(result)
    request = raw_result.get("request")
    if hasattr(request, "_asdict"):
        raw_result["request"] = request._asdict()
    return raw_result


def _pick_retry_modes(initial_filling: int | None) -> list[int]:
    mode_map = {
        "IOC": int(getattr(mt5, "ORDER_FILLING_IOC", 1)),
        "FOK": int(getattr(mt5, "ORDER_FILLING_FOK", 0)),
        "RETURN": int(getattr(mt5, "ORDER_FILLING_RETURN", 2)),
    }
    retry_modes = [mode_map[name] for name in getattr(execution_config, "filling_retry_order", []) if name in mode_map]
    if initial_filling is not None and initial_filling not in retry_modes:
        retry_modes = [initial_filling, *retry_modes]
    elif initial_filling is not None:
        retry_modes = [initial_filling, *[mode for mode in retry_modes if mode != initial_filling]]
    return retry_modes or [mode_map["IOC"]]


def _refresh_market_price(request: Dict[str, Any], preview_payload: Mapping[str, Any] | None) -> None:
    payload = dict(preview_payload or {})
    if str(payload.get("order_type") or "market").strip().lower() != "market":
        return
    symbol = str(request.get("symbol") or payload.get("execution_symbol") or payload.get("symbol") or "")
    tick = mt5.symbol_info_tick(symbol)
    if tick is None:
        return
    side = str(payload.get("side") or "buy").strip().lower()
    request["price"] = float(tick.ask if side == "buy" else tick.bid)


def submit_manual_trade(preview_payload: Mapping[str, Any] | None) -> Dict[str, Any]:
    base_request = build_manual_trade_mt5_request(preview_payload)
    _refresh_market_price(base_request, preview_payload)
    retry_modes = _pick_retry_modes(base_request.get("type_filling"))

    result = None
    used_filling = base_request.get("type_filling")
    for filling_mode in retry_modes:
        request = {**base_request, "type_filling": filling_mode}
        result = mt5.order_send(request)
        if result is not None:
            used_filling = filling_mode
            base_request = request
            break

    if result is None:
        last_error = mt5.last_error()
        failure = classify_manual_trade_mt5_failure(str(base_request.get("symbol") or ""), last_error=last_error)
        return {
            "ok": False,
            "submit_status": "transport_error",
            "retcode": None,
            "message": f"mt5.order_send() returned None (last_error={last_error})",
            "last_error": last_error,
            "request": base_request,
            "used_filling": used_filling,
            "raw_result": {},
            **failure,
        }

    raw_result = _raw_result_to_dict(result)
    retcode = int(raw_result.get("retcode") or 0)
    message = str(raw_result.get("comment") or "Broker submit finished.")
    order_ticket = raw_result.get("order")
    deal_ticket = raw_result.get("deal")
    position_id = raw_result.get("position") or raw_result.get("position_id") or order_ticket
    ok = retcode in _SUCCESS_RETCODES
    return {
        "ok": ok,
        "submit_status": "submitted" if ok else "broker_rejected",
        "retcode": retcode,
        "message": message,
        "request": base_request,
        "used_filling": used_filling,
        "raw_result": raw_result,
        "order_ticket": int(order_ticket) if order_ticket else None,
        "deal_ticket": int(deal_ticket) if deal_ticket else None,
        "position_id": int(position_id) if position_id else None,
    }
