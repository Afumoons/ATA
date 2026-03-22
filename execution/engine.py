from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import MetaTrader5 as mt5

from ..logging_utils import get_logger
from ..risk.manager import AccountState, TradeRequest, RiskDecision, validate_trade

logger = get_logger(__name__)

TRADES_LOG_PATH = Path(__file__).resolve().parent / "trades.log"

# ---------------------------------------------------------------------------
# Pip value per standard lot, per instrument family.
#
# The original code used: volume = risk_amount / (sl_distance * 100_000)
# which is the forex formula (1 lot = 100k units, pip value ≈ $10/pip/lot).
#
# For gold (XAUUSDm):
#   1 lot = 100 troy oz
#   pip size = 0.01 (1 cent)
#   pip value = 100 oz * $0.01 = $1.00 per pip per lot
#
# Using the forex formula on gold underestimates volume by ~10x, forcing
# every trade to clamp at 0.01 lot regardless of risk settings.
#
# Override pip_value_per_lot in execute_trade() if your broker differs.
# ---------------------------------------------------------------------------

_DEFAULT_PIP_VALUE_PER_LOT: dict[str, float] = {
    # Metals
    "XAUUSDm": 1.0,   # gold: $1/pip/lot
    "XAGUSDm": 0.5,   # silver: ~$0.50/pip/lot
    "XAUUSD":  1.0,
    "XAGUSD":  0.5,
    # Major forex: 1 pip = 0.0001, 1 lot = 100k units → $10/pip/lot (for USD pairs)
    # These are approximate; use broker contract spec for precision.
    "EURUSD": 10.0,
    "GBPUSD": 10.0,
    "USDJPY": 10.0,
    "AUDUSD": 10.0,
    "USDCAD": 10.0,
    "USDCHF": 10.0,
    # Crypto (highly variable — use mt5 symbol_info for real values)
    "BTCUSDm": 0.1,
    "ETHUSDm": 0.1,
}

_METALS = {"XAU", "XAG"}


def _pip_value_for_symbol(symbol: str) -> float:
    """Best-effort pip value per lot lookup. Falls back to $10 (forex default)."""
    if symbol in _DEFAULT_PIP_VALUE_PER_LOT:
        return _DEFAULT_PIP_VALUE_PER_LOT[symbol]
    # Detect metals by prefix
    for prefix in _METALS:
        if symbol.startswith(prefix):
            return 1.0
    return 10.0  # forex default


def _clamp_volume(volume: float, symbol: str) -> float:
    """Clamp volume to broker min/max/step from MT5 symbol info."""
    info = mt5.symbol_info(symbol)
    if info is None:
        return max(volume, 0.01)
    min_lot = float(info.volume_min)
    max_lot = float(info.volume_max)
    step = float(info.volume_step)
    # Round to nearest step
    if step > 0:
        volume = round(round(volume / step) * step, 8)
    return float(max(min_lot, min(max_lot, volume)))


@dataclass
class ExecutionResult:
    success: bool
    reason: str
    ticket: Optional[int] = None
    volume: Optional[float] = None
    price: Optional[float] = None
    raw_result: Optional[dict] = None


def _get_account_state() -> AccountState:
    info = mt5.account_info()
    if info is None:
        raise RuntimeError("MT5 account_info() returned None — not logged in?")

    positions = mt5.positions_get()
    open_positions = len(positions) if positions else 0

    return AccountState(
        equity=float(info.equity),
        balance=float(info.balance),
        open_positions=open_positions,
    )


def _log_trade(
    strategy_name: str,
    symbol: str,
    direction: str,
    volume: float,
    price: float,
    sl: float,
    tp: float,
    ticket: int,
    reason: str,
) -> None:
    line = (
        f"strategy={strategy_name} symbol={symbol} dir={direction} vol={volume:.4f} "
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
    pip_size: float = 0.01,
    pip_value_per_lot: Optional[float] = None,
    equity_peak: Optional[float] = None,
) -> ExecutionResult:
    """Validate and execute a market order via MetaTrader 5.

    Volume sizing formula (fixed from original):
        risk_amount   = equity * (risk_perc / 100)
        volume (lots) = risk_amount / (stop_loss_pips * pip_value_per_lot)

    The original formula used sl_distance * 100_000 which is the forex
    approximation. For gold (pip_value = $1/pip/lot) this underestimated
    volume by ~10x, forcing every trade to the 0.01 minimum lot.

    Parameters
    ----------
    pip_size         : price distance per 1 pip (0.01 for metals, 0.0001 for forex)
    pip_value_per_lot: monetary value of 1 pip movement per standard lot.
                       Defaults to instrument-family lookup. Override if broker differs.
    equity_peak      : historical equity peak for drawdown guard. Should come
                       from live_monitor. Defaults to current equity if None
                       (drawdown guard disabled effectively).
    """
    if direction not in {"long", "short"}:
        return ExecutionResult(success=False, reason=f"invalid direction: {direction}")

    if stop_loss_pips <= 0:
        return ExecutionResult(success=False, reason=f"non-positive stop_loss_pips: {stop_loss_pips}")

    # ------------------------------------------------------------------ #
    # Get live tick                                                        #
    # ------------------------------------------------------------------ #
    tick = mt5.symbol_info_tick(symbol)
    if tick is None:
        return ExecutionResult(success=False, reason=f"no tick data for {symbol}")

    price = float(tick.ask if direction == "long" else tick.bid)

    # ------------------------------------------------------------------ #
    # Account state                                                        #
    # ------------------------------------------------------------------ #
    try:
        account = _get_account_state()
    except RuntimeError as e:
        return ExecutionResult(success=False, reason=str(e))

    if equity_peak is None:
        # No historical peak available — use current equity.
        # This disables the drawdown guard. Prefer passing peak from live_monitor.
        equity_peak = account.equity
        logger.debug(
            "execute_trade: equity_peak not provided for %s — drawdown guard inactive",
            strategy_name,
        )

    # ------------------------------------------------------------------ #
    # Volume sizing                                                        #
    # ------------------------------------------------------------------ #
    pv = pip_value_per_lot if pip_value_per_lot is not None else _pip_value_for_symbol(symbol)
    if pv <= 0:
        return ExecutionResult(success=False, reason=f"invalid pip_value_per_lot: {pv}")

    risk_amount = account.equity * (risk_perc / 100.0)
    raw_volume = risk_amount / (stop_loss_pips * pv)
    volume = _clamp_volume(raw_volume, symbol)

    logger.debug(
        "Sizing: strategy=%s symbol=%s equity=%.2f risk_pct=%.3f "
        "sl_pips=%.1f pip_val=%.4f raw_vol=%.4f clamped_vol=%.4f",
        strategy_name, symbol, account.equity, risk_perc,
        stop_loss_pips, pv, raw_volume, volume,
    )

    # ------------------------------------------------------------------ #
    # Risk validation                                                      #
    # ------------------------------------------------------------------ #
    req = TradeRequest(
        strategy_name=strategy_name,
        symbol=symbol,
        direction=direction,
        volume=volume,
        risk_perc=risk_perc,
    )
    decision: RiskDecision = validate_trade(account, req, equity_peak)
    if not decision.allowed:
        logger.info(
            "Trade rejected by risk manager: strategy=%s reason=%s",
            strategy_name, decision.reason,
        )
        return ExecutionResult(success=False, reason=f"risk_reject: {decision.reason}")

    # ------------------------------------------------------------------ #
    # Build and send order                                                 #
    # ------------------------------------------------------------------ #
    if direction == "long":
        sl_price = price - stop_loss_pips * pip_size
        tp_price = price + take_profit_pips * pip_size
        order_type = mt5.ORDER_TYPE_BUY
    else:
        sl_price = price + stop_loss_pips * pip_size
        tp_price = price - take_profit_pips * pip_size
        order_type = mt5.ORDER_TYPE_SELL

    # Sanity check SL/TP are valid (non-negative price)
    if sl_price <= 0 or tp_price <= 0:
        return ExecutionResult(
            success=False,
            reason=f"computed sl/tp invalid: sl={sl_price:.5f} tp={tp_price:.5f}",
        )

    # ------------------------------------------------------------------ #
    # Detect filling mode supported by this broker/symbol                 #
    #                                                                      #
    # Exness Hedge accounts require an explicit type_filling in the order #
    # request. Without it, order_send() returns None silently — no error  #
    # code, no retcode, just None.                                        #
    #                                                                      #
    # filling_mode bitmask in symbol_info:                                #
    #   1 = ORDER_FILLING_FOK  (Fill or Kill)                            #
    #   2 = ORDER_FILLING_IOC  (Immediate or Cancel)                     #
    # ------------------------------------------------------------------ #
    filling_mode = mt5.ORDER_FILLING_IOC  # safe default for most brokers
    sym_info = mt5.symbol_info(symbol)
    if sym_info is not None:
        fm = int(sym_info.filling_mode)
        if fm & 1:
            filling_mode = mt5.ORDER_FILLING_FOK
        elif fm & 2:
            filling_mode = mt5.ORDER_FILLING_IOC
        else:
            filling_mode = mt5.ORDER_FILLING_RETURN

    request = {
        "action":       mt5.TRADE_ACTION_DEAL,
        "symbol":       symbol,
        "volume":       float(volume),
        "type":         order_type,
        "price":        price,
        "sl":           round(sl_price, 5),
        "tp":           round(tp_price, 5),
        "deviation":    10,
        "magic":        987654,
        "comment":      f"clio-auto-{strategy_name[:20]}",
        "type_filling": filling_mode,
    }

    result = mt5.order_send(request)

    if result is None:
        last_err = mt5.last_error()
        logger.error(
            "order_send() returned None: strategy=%s symbol=%s dir=%s "
            "vol=%.4f price=%.5f filling=%s last_error=%s",
            strategy_name, symbol, direction,
            volume, price, filling_mode, last_err,
        )
        return ExecutionResult(
            success=False,
            reason=f"mt5.order_send() returned None (last_error={last_err})",
        )

    res_dict = result._asdict()

    if result.retcode != mt5.TRADE_RETCODE_DONE:
        logger.warning(
            "Order failed: strategy=%s symbol=%s dir=%s retcode=%s deal=%s",
            strategy_name, symbol, direction, result.retcode, res_dict,
        )
        return ExecutionResult(
            success=False,
            reason=f"order_failed: retcode={result.retcode}",
            raw_result=res_dict,
        )

    ticket = int(result.order)
    _log_trade(strategy_name, symbol, direction, volume, price, sl_price, tp_price, ticket, "executed")

    return ExecutionResult(
        success=True,
        reason="ok",
        ticket=ticket,
        volume=volume,
        price=price,
        raw_result=res_dict,
    )