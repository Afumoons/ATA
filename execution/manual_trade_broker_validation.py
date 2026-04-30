from __future__ import annotations

from typing import Any, Dict, Mapping

import MetaTrader5 as mt5

from ..config import execution_config
from .manual_trade_identity import MANUAL_COMMENT_TAG, MANUAL_ORDER_MAGIC, manual_trade_marker_payload

_SUCCESS_RETCODES = {
    0,
    int(getattr(mt5, "TRADE_RETCODE_DONE", 10009)),
    int(getattr(mt5, "TRADE_RETCODE_PLACED", 10008)),
}


def _as_dict(value: Any) -> Dict[str, Any]:
    if value is None:
        return {}
    if hasattr(value, "_asdict"):
        return value._asdict()
    if isinstance(value, dict):
        return dict(value)
    return {
        key: getattr(value, key)
        for key in dir(value)
        if not key.startswith("_") and not callable(getattr(value, key))
    }


def inspect_manual_trade_mt5_context(symbol: str) -> Dict[str, Any]:
    terminal_info_fn = getattr(mt5, "terminal_info", None)
    account_info_fn = getattr(mt5, "account_info", None)
    symbol_info_fn = getattr(mt5, "symbol_info", None)

    terminal_info = terminal_info_fn() if callable(terminal_info_fn) else None
    account_info = account_info_fn() if callable(account_info_fn) else None
    symbol_info = symbol_info_fn(symbol) if callable(symbol_info_fn) and symbol else None

    terminal_payload = _as_dict(terminal_info)
    account_payload = _as_dict(account_info)
    symbol_payload = _as_dict(symbol_info)

    return {
        "symbol": symbol,
        "terminal_available": terminal_info is not None,
        "terminal_connected": terminal_payload.get("connected"),
        "terminal_trade_allowed": terminal_payload.get("trade_allowed"),
        "account_available": account_info is not None,
        "account_login": account_payload.get("login"),
        "account_trade_allowed": account_payload.get("trade_allowed"),
        "symbol_available": symbol_info is not None,
        "symbol_visible": symbol_payload.get("visible"),
        "symbol_select": symbol_payload.get("select"),
    }


def classify_manual_trade_mt5_failure(symbol: str, *, last_error: Any = None) -> Dict[str, Any]:
    context = inspect_manual_trade_mt5_context(symbol)
    failure_code = "mt5_transport_error"
    if not context.get("terminal_available") or context.get("terminal_connected") is False:
        failure_code = "mt5_terminal_unavailable"
    elif not context.get("account_available"):
        failure_code = "mt5_account_unavailable"
    elif context.get("account_trade_allowed") is False:
        failure_code = "mt5_account_trading_disabled"
    elif not context.get("symbol_available"):
        failure_code = "mt5_symbol_unavailable"
    elif context.get("symbol_visible") is False and context.get("symbol_select") is False:
        failure_code = "mt5_symbol_not_visible"
    return {
        "failure_code": failure_code,
        "context": {
            **context,
            "last_error": last_error,
        },
    }


def _pick_filling_mode(symbol: str) -> int | None:
    info = mt5.symbol_info(symbol)
    if info is None:
        return None
    filling_mode = int(getattr(info, "filling_mode", 0) or 0)
    if filling_mode == 0:
        return int(getattr(mt5, "ORDER_FILLING_IOC", 1))
    if filling_mode & 1:
        return int(getattr(mt5, "ORDER_FILLING_FOK", 0))
    if filling_mode & 2:
        return int(getattr(mt5, "ORDER_FILLING_IOC", 1))
    return int(getattr(mt5, "ORDER_FILLING_RETURN", 2))


def _resolve_order_type(*, side: str, order_type: str) -> tuple[int, int]:
    normalized_side = str(side or "").strip().lower()
    normalized_type = str(order_type or "market").strip().lower()
    if normalized_type == "market":
        action = int(getattr(mt5, "TRADE_ACTION_DEAL"))
        order = int(getattr(mt5, "ORDER_TYPE_BUY" if normalized_side == "buy" else "ORDER_TYPE_SELL"))
        return action, order
    action = int(getattr(mt5, "TRADE_ACTION_PENDING"))
    order = int(getattr(mt5, "ORDER_TYPE_BUY_LIMIT" if normalized_side == "buy" else "ORDER_TYPE_SELL_LIMIT"))
    return action, order


def build_manual_trade_mt5_request(preview_payload: Mapping[str, Any] | None) -> Dict[str, Any]:
    payload = dict(preview_payload or {})
    symbol = str(payload.get("execution_symbol") or payload.get("symbol") or "")
    side = str(payload.get("side") or "buy")
    order_type = str(payload.get("order_type") or "market")
    action, mt5_order_type = _resolve_order_type(side=side, order_type=order_type)
    request = {
        "action": action,
        "symbol": symbol,
        "volume": float(payload.get("lot_size") or 0.0),
        "type": mt5_order_type,
        "price": float(payload.get("entry_price") or 0.0),
        "sl": float(payload.get("stop_loss_price") or 0.0),
        "tp": float(payload.get("take_profit_price") or 0.0),
        "deviation": int(getattr(execution_config, "order_deviation", 20)),
        "magic": int(payload.get("magic_number") or MANUAL_ORDER_MAGIC),
        "comment": str(payload.get("comment_tag") or MANUAL_COMMENT_TAG),
        "type_time": int(getattr(mt5, "ORDER_TIME_GTC", 0)),
    }
    filling_mode = _pick_filling_mode(symbol)
    if filling_mode is not None:
        request["type_filling"] = filling_mode
    return request


def validate_manual_trade_preview(preview_payload: Mapping[str, Any] | None) -> Dict[str, Any]:
    request = build_manual_trade_mt5_request(preview_payload)
    result = mt5.order_check(request)
    if result is None:
        last_error = mt5.last_error()
        failure = classify_manual_trade_mt5_failure(str(request.get("symbol") or ""), last_error=last_error)
        return {
            "ok": False,
            "stage": "broker_validation",
            "retcode": None,
            "message": f"mt5.order_check() returned None (last_error={last_error})",
            "last_error": last_error,
            "request": {**request, **manual_trade_marker_payload()},
            **failure,
        }

    raw_result = result._asdict()
    retcode = int(raw_result.get("retcode") or 0)
    message = str(raw_result.get("comment") or raw_result.get("request") or "Broker validation finished.")
    return {
        "ok": retcode in _SUCCESS_RETCODES,
        "stage": "broker_validation",
        "retcode": retcode,
        "message": message,
        "request": {**request, **manual_trade_marker_payload()},
        "raw_result": raw_result,
    }
