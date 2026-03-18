from __future__ import annotations

from dataclasses import dataclass

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
    direction: str   # "long" or "short"
    volume: float    # lots
    risk_perc: float # requested risk % of equity


@dataclass
class RiskDecision:
    allowed: bool
    reason: str


def check_max_risk_per_trade(
    account: AccountState, req: TradeRequest
) -> RiskDecision:
    if req.risk_perc <= 0:
        return RiskDecision(
            allowed=False,
            reason=f"risk_perc must be > 0, got {req.risk_perc}",
        )
    if req.risk_perc > risk_config.max_risk_per_trade_pct:
        return RiskDecision(
            allowed=False,
            reason=(
                f"risk_perc {req.risk_perc:.2f}% > max "
                f"{risk_config.max_risk_per_trade_pct:.2f}%"
            ),
        )
    return RiskDecision(allowed=True, reason="ok")


def check_volume(req: TradeRequest) -> RiskDecision:
    """Guard against zero or negative volume reaching MT5."""
    if req.volume <= 0:
        return RiskDecision(
            allowed=False,
            reason=f"volume must be > 0, got {req.volume:.6f}",
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
    """Block new trades if portfolio drawdown exceeds the configured limit."""
    if equity_peak <= 0:
        return RiskDecision(allowed=True, reason="no_peak")

    dd_pct = (equity_peak - account.equity) / equity_peak * 100.0

    if dd_pct > risk_config.max_portfolio_drawdown_pct:
        return RiskDecision(
            allowed=False,
            reason=(
                f"portfolio_drawdown {dd_pct:.2f}% > max "
                f"{risk_config.max_portfolio_drawdown_pct:.2f}%"
            ),
        )
    return RiskDecision(allowed=True, reason="ok")


def validate_trade(
    account: AccountState,
    req: TradeRequest,
    equity_peak: float,
) -> RiskDecision:
    """Validate a proposed trade against all risk rules.

    Checks run in order of cheapest-to-fail first:
    1. Volume sanity (never send 0-lot order to MT5)
    2. Risk per trade cap
    3. Max concurrent open positions
    4. Portfolio drawdown limit
    """
    checks = [
        check_volume(req),
        check_max_risk_per_trade(account, req),
        check_max_open_positions(account),
        check_drawdown(equity_peak, account),
    ]

    for decision in checks:
        if not decision.allowed:
            logger.warning(
                "Risk reject: strategy=%s symbol=%s dir=%s reason=%s "
                "(equity=%.2f peak=%.2f open_pos=%d)",
                req.strategy_name,
                req.symbol,
                req.direction,
                decision.reason,
                account.equity,
                equity_peak,
                account.open_positions,
            )
            return decision

    logger.info(
        "Risk accept: strategy=%s symbol=%s dir=%s vol=%.4f risk=%.3f%% "
        "open_pos=%d equity=%.2f",
        req.strategy_name,
        req.symbol,
        req.direction,
        req.volume,
        req.risk_perc,
        account.open_positions,
        account.equity,
    )
    return RiskDecision(allowed=True, reason="ok")