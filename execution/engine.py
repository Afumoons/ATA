from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import MetaTrader5 as mt5

from ..logging_utils import get_logger
from ..risk.manager import AccountState, TradeRequest, RiskDecision, validate_trade

logger = get_logger(__name__)

TRADES_LOG_PATH = Path(__file__).resolve().parent / "trades.log"


@dataclass
class ExecutionResult:
    success: bool
    reason: str
    ticket: Optional[int] = None
    raw_result: Optional[dict] = None


def _get_account_state() -> AccountState:
    info = mt5.account_info()
    if info is None:
        raise RuntimeError("MT5 account_info() returned None (not logged in?)")

    positions = mt5.positions_get()
    open_positions = len(positions) if positions else 0

    return AccountState(
        equity=float(info.equity),
        balance=float(info.balance),
        open_positions=open_positions,
    )


def _log_trade(strategy_name: str, symbol: str, direction: str, volume: float, price: float, sl: float, tp: float, ticket: int, reason: str) -> None:
    line = (
        f"strategy={strategy_name} symbol={symbol} dir={direction} vol={volume:.2f} "
        f"price={price:.5f} sl={sl:.5f} tp={tp:.5f} ticket={ticket} reason={reason}\n"
    )
    with TRADES_LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(line)
    logger.info("Trade executed: %s", line.strip())


def execute_trade(
    strategy_name: str,
    symbol: str,
    direction: str,
    risk_perc: float,
    stop_loss_pips: float,
    take_profit_pips: float,
    pip_size: float = 0.0001,
    equity_peak: Optional[float] = None,
) -> ExecutionResult:
    """Validate and execute a trade via MetaTrader5.

    This is a thin layer over the risk manager + MT5 API. It assumes SL/TP are
    expressed in pips relative to the current price.
    """
    if direction not in {"long", "short"}:
        return ExecutionResult(success=False, reason=f"invalid direction: {direction}")

    tick = mt5.symbol_info_tick(symbol)
    if tick is None:
        return ExecutionResult(success=False, reason=f"no tick data for {symbol}")

    price = float(tick.ask if direction == "long" else tick.bid)

    account = _get_account_state()
    if equity_peak is None:
        equity_peak = account.equity

    # Approximate volume sizing (per-lot risk): risk_perc of equity across SL distance
    sl_distance = stop_loss_pips * pip_size
    if sl_distance <= 0:
        return ExecutionResult(success=False, reason="non-positive stop_loss_pips")

    risk_amount = account.equity * (risk_perc / 100.0)
    volume = risk_amount / (sl_distance * 100_000)  # rough: 1 lot ~ 100k notional
    volume = max(volume, 0.01)  # clamp to minimum lot

    req = TradeRequest(
        strategy_name=strategy_name,
        symbol=symbol,
        direction=direction,
        volume=volume,
        risk_perc=risk_perc,
    )

    decision: RiskDecision = validate_trade(account, req, equity_peak)
    if not decision.allowed:
        return ExecutionResult(success=False, reason=f"risk_reject: {decision.reason}")

    # Build SL/TP prices
    if direction == "long":
        sl_price = price - stop_loss_pips * pip_size
        tp_price = price + take_profit_pips * pip_size
        order_type = mt5.ORDER_TYPE_BUY
    else:
        sl_price = price + stop_loss_pips * pip_size
        tp_price = price - take_profit_pips * pip_size
        order_type = mt5.ORDER_TYPE_SELL

    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": float(volume),
        "type": order_type,
        "price": price,
        "sl": sl_price,
        "tp": tp_price,
        "deviation": 10,
        "magic": 987654,
        "comment": f"clio-auto-{strategy_name}",
    }

    result = mt5.order_send(request)
    if result is None:
        return ExecutionResult(success=False, reason="mt5.order_send() returned None")

    res_dict = result._asdict()
    if result.retcode != mt5.TRADE_RETCODE_DONE:
        logger.warning("Order failed: %s", res_dict)
        return ExecutionResult(success=False, reason=f"order_failed: {result.retcode}", raw_result=res_dict)

    ticket = int(result.order)
    _log_trade(strategy_name, symbol, direction, volume, price, sl_price, tp_price, ticket, "executed")
    return ExecutionResult(success=True, reason="ok", ticket=ticket, raw_result=res_dict)
