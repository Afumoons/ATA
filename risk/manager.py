from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple

from ..logging_utils import get_logger
from ..config import risk_config

logger = get_logger(__name__)


@dataclass
class AccountState:
    equity: float
    balance: float
    open_positions: int


@dataclass
class TradeRequest:
    strategy_name: str
    symbol: str
    direction: str  # "long" or "short"
    volume: float  # lots or equivalent
    risk_perc: float  # requested risk % of equity


@dataclass
class RiskDecision:
    allowed: bool
    reason: str


def check_max_risk_per_trade(account: AccountState, req: TradeRequest) -> RiskDecision:
    if req.risk_perc > risk_config.max_risk_per_trade_pct:
        return RiskDecision(
            allowed=False,
            reason=f"risk_perc {req.risk_perc:.2f}% > max {risk_config.max_risk_per_trade_pct:.2f}%",
        )
    return RiskDecision(allowed=True, reason="ok")


def check_max_open_positions(account: AccountState) -> RiskDecision:
    if account.open_positions >= risk_config.max_open_positions:
        return RiskDecision(
            allowed=False,
            reason=(
                f"open_positions {account.open_positions} >= max "
                f"{risk_config.max_open_positions}"
            ),
        )
    return RiskDecision(allowed=True, reason="ok")


def check_drawdown(equity_peak: float, account: AccountState) -> RiskDecision:
    if equity_peak <= 0:
        return RiskDecision(allowed=True, reason="no_peak")
    dd_pct = (equity_peak - account.equity) / equity_peak * 100.0
    if dd_pct > risk_config.max_portfolio_drawdown_pct:
        return RiskDecision(
            allowed=False,
            reason=(
                f"drawdown {dd_pct:.2f}% > max "
                f"{risk_config.max_portfolio_drawdown_pct:.2f}%"
            ),
        )
    return RiskDecision(allowed=True, reason="ok")


def validate_trade(
    account: AccountState,
    req: TradeRequest,
    equity_peak: float,
) -> RiskDecision:
    """Validate a proposed trade against risk rules.

    This does NOT compute exact pip/SL sizing; that is handled in backtest/execution.
    """
    checks = [
        check_max_risk_per_trade(account, req),
        check_max_open_positions(account),
        check_drawdown(equity_peak, account),
    ]

    for c in checks:
        if not c.allowed:
            logger.warning(
                "Risk reject: strategy=%s symbol=%s dir=%s reason=%s",
                req.strategy_name,
                req.symbol,
                req.direction,
                c.reason,
            )
            return c

    logger.info(
        "Risk accept: strategy=%s symbol=%s dir=%s vol=%.2f risk=%.2f%%",
        req.strategy_name,
        req.symbol,
        req.direction,
        req.volume,
        req.risk_perc,
    )
    return RiskDecision(allowed=True, reason="ok")
