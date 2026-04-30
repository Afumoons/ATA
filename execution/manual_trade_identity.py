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
