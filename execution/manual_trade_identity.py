from __future__ import annotations

from typing import Any, Dict

MANUAL_ORDER_ORIGIN = "manual_user"
MANUAL_EXECUTION_ORIGIN = "operator_ui"
MANUAL_COMMENT_TAG = "clio-manual-user"


def manual_trade_marker_payload() -> Dict[str, Any]:
    return {
        "order_origin": MANUAL_ORDER_ORIGIN,
        "execution_origin": MANUAL_EXECUTION_ORIGIN,
        "is_manual": True,
        "exclude_from_strategy_eval": True,
        "comment_tag": MANUAL_COMMENT_TAG,
    }


def is_manual_trade_payload(payload: Dict[str, Any] | None) -> bool:
    if not isinstance(payload, dict):
        return False
    if payload.get("is_manual") is True:
        return True
    if str(payload.get("order_origin") or "") == MANUAL_ORDER_ORIGIN:
        return True
    if str(payload.get("execution_origin") or "") == MANUAL_EXECUTION_ORIGIN:
        return True
    comment = str(payload.get("comment") or payload.get("comment_tag") or payload.get("raw") or "")
    return MANUAL_COMMENT_TAG in comment
