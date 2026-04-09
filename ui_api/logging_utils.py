from __future__ import annotations

try:
    from ..logging_utils import get_logger
except ImportError:
    from logging_utils import get_logger

ui_logger = get_logger("autonomous_trading_ai.ui_api")
