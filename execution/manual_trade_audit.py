from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, Iterable, Mapping

try:
    from ..execution.audit_utils import append_pool_audit
    from ..execution.manual_trade_identity import manual_trade_marker_payload
except ImportError:
    from execution.audit_utils import append_pool_audit
    from execution.manual_trade_identity import manual_trade_marker_payload


_MANUAL_PREVIEW_KEYS = (
    "symbol",
    "symbol_canonical",
    "execution_symbol",
    "instrument_class",
    "side",
    "order_type",
    "entry_price",
    "stop_loss_price",
    "take_profit_price",
    "lot_size",
    "risk_mode",
    "risk_value",
    "risk_amount",
    "stop_loss_mode",
    "stop_loss_input",
    "take_profit_mode",
    "take_profit_input",
)


def _to_dict(value: Mapping[str, Any] | None) -> Dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    return {str(key): item for key, item in value.items()}


def manual_trade_preview_fingerprint(preview_payload: Mapping[str, Any] | None) -> str:
    normalized = {key: _to_dict(preview_payload).get(key) for key in _MANUAL_PREVIEW_KEYS}
    encoded = json.dumps(normalized, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:16]


def build_manual_ticket_preview_audit_event(
    *,
    preview_payload: Mapping[str, Any] | None,
    derived: Mapping[str, Any] | None = None,
    symbol_spec: Mapping[str, Any] | None = None,
    symbol_spec_warnings: Iterable[str] | None = None,
) -> Dict[str, Any]:
    preview = {
        **manual_trade_marker_payload(),
        **_to_dict(preview_payload),
    }
    derived_payload = _to_dict(derived)
    symbol_spec_payload = _to_dict(symbol_spec)
    warnings = [str(item) for item in list(symbol_spec_warnings or []) + list(derived_payload.get("warnings") or []) if str(item).strip()]

    return {
        "event": "manual_ticket_preview_intent",
        "event_category": "manual_trade_ticket",
        "audit_stage": "preview_intent",
        "preview_fingerprint": manual_trade_preview_fingerprint(preview),
        "preview_payload": preview,
        "symbol": preview.get("symbol") or symbol_spec_payload.get("symbol"),
        "execution_symbol": preview.get("execution_symbol") or symbol_spec_payload.get("execution_symbol"),
        "side": preview.get("side"),
        "order_type": preview.get("order_type"),
        "entry_price": preview.get("entry_price"),
        "stop_loss_price": preview.get("stop_loss_price"),
        "take_profit_price": preview.get("take_profit_price"),
        "lot_size": preview.get("lot_size"),
        "risk_mode": preview.get("risk_mode"),
        "risk_value": preview.get("risk_value"),
        "risk_amount": preview.get("risk_amount"),
        "symbol_spec": symbol_spec_payload,
        "warnings": warnings,
        **manual_trade_marker_payload(),
    }


def record_manual_ticket_preview_intent(
    *,
    preview_payload: Mapping[str, Any] | None,
    derived: Mapping[str, Any] | None = None,
    symbol_spec: Mapping[str, Any] | None = None,
    symbol_spec_warnings: Iterable[str] | None = None,
) -> Dict[str, Any]:
    event = build_manual_ticket_preview_audit_event(
        preview_payload=preview_payload,
        derived=derived,
        symbol_spec=symbol_spec,
        symbol_spec_warnings=symbol_spec_warnings,
    )
    append_pool_audit(event)
    return event


def build_manual_ticket_execution_audit_event(
    *,
    preview_payload: Mapping[str, Any] | None,
    submit_status: str,
    broker_response: Mapping[str, Any] | None = None,
    error_message: str | None = None,
) -> Dict[str, Any]:
    preview = {
        **manual_trade_marker_payload(),
        **_to_dict(preview_payload),
    }
    event = {
        "event": "manual_ticket_execution_result",
        "event_category": "manual_trade_ticket",
        "audit_stage": "execution_result",
        "submit_status": str(submit_status or "unknown"),
        "preview_fingerprint": manual_trade_preview_fingerprint(preview),
        "preview_payload": preview,
        "broker_response": _to_dict(broker_response),
        **manual_trade_marker_payload(),
    }
    if error_message:
        event["error_message"] = str(error_message)
    return event


def record_manual_ticket_execution_result(
    *,
    preview_payload: Mapping[str, Any] | None,
    submit_status: str,
    broker_response: Mapping[str, Any] | None = None,
    error_message: str | None = None,
) -> Dict[str, Any]:
    event = build_manual_ticket_execution_audit_event(
        preview_payload=preview_payload,
        submit_status=submit_status,
        broker_response=broker_response,
        error_message=error_message,
    )
    append_pool_audit(event)
    return event
