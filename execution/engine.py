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
    "XAUUSDm": 1.0,
    "XAGUSDm": 0.5,
    "XAUUSD":  1.0,
    "XAGUSD":  0.5,
    "EURUSD": 10.0,
    "GBPUSD": 10.0,
    "USDJPY": 10.0,
    "AUDUSD": 10.0,
    "USDCAD": 10.0,
    "USDCHF": 10.0,
    "BTCUSDm": 0.1,
    "ETHUSDm": 0.1,
}

_METALS = {"XAU", "XAG"}


def _pip_value_for_symbol(symbol: str) -> float:
    if symbol in _DEFAULT_PIP_VALUE_PER_LOT:
        return _DEFAULT_PIP_VALUE_PER_LOT[symbol]
    for prefix in _METALS:
        if symbol.startswith(prefix):
            return 1.0
    return 10.0


def _clamp_volume(volume: float, symbol: str) -> float:
    info = mt5.symbol_info(symbol)
    if info is None:
        return max(volume, 0.01)
    min_lot = float(info.volume_min)
    max_lot = float(info.volume_max)
    step = float(info.volume_step)
    if step > 0:
        volume = round(round(volume / step) * step, 8)
    return float(max(min_lot, min(max_lot, volume)))


def _build_comment(strategy_name: str, symbol: str, timeframe: str) -> str:
    """Build MT5 comment — alphanumeric only (Exness requirement).

    Format: {timeframe}{symbol}{uid4}
    Example: M15, XAUUSDm, core15_XAUUSDm_M15_9fb8 → "M15XAUUSDm9fb8"

    uid4 is the 4-char hex suffix after the last underscore in strategy_name.
    Total kept under 31 chars (MT5 comment field limit).
    """
    uid4 = strategy_name.split("_")[-1][:4] if "_" in strategy_name else strategy_name[-4:]
    tf_clean = "".join(c for c in timeframe if c.isalnum())
    sym_clean = "".join(c for c in symbol if c.isalnum())
    return f"{tf_clean}{sym_clean}{uid4}"[:31]


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
    timeframe: str = "M15",
) -> ExecutionResult:
    """Validate and execute a market order via MetaTrader 5.

    Tier 1 additions vs previous version:
    - _build_comment(): comment now M15XAUUSDm9fb8 format for readability in MT5
    - Filling mode retry: if order_send() returns None, retry with next filling mode
      before giving up. Handles Exness edge cases silently returning None.
    - timeframe param added for comment generation.
    """
    if direction not in {"long", "short"}:
        return ExecutionResult(success=False, reason=f"invalid direction: {direction}")

    if stop_loss_pips <= 0:
        return ExecutionResult(success=False, reason=f"non-positive stop_loss_pips: {stop_loss_pips}")

    try:
        from .live_state_utils import strategy_has_open_position
    except Exception:
        logger.exception("execute_trade: failed to import strategy_has_open_position")
        strategy_has_open_position = None

    if strategy_has_open_position is not None and strategy_has_open_position(
        strategy_name=strategy_name,
        symbol=symbol,
        timeframe=timeframe,
    ):
        return ExecutionResult(
            success=False,
            reason=(
                "existing_open_position: "
                f"strategy={strategy_name} symbol={symbol} timeframe={timeframe}"
            ),
        )

    tick = mt5.symbol_info_tick(symbol)
    if tick is None:
        return ExecutionResult(success=False, reason=f"no tick data for {symbol}")

    price = float(tick.ask if direction == "long" else tick.bid)

    try:
        account = _get_account_state()
    except RuntimeError as e:
        return ExecutionResult(success=False, reason=str(e))

    if equity_peak is None:
        equity_peak = account.equity
        logger.debug(
            "execute_trade: equity_peak not provided for %s — drawdown guard inactive",
            strategy_name,
        )

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

    if direction == "long":
        sl_price = price - stop_loss_pips * pip_size
        tp_price = price + take_profit_pips * pip_size
        order_type = mt5.ORDER_TYPE_BUY
    else:
        sl_price = price + stop_loss_pips * pip_size
        tp_price = price - take_profit_pips * pip_size
        order_type = mt5.ORDER_TYPE_SELL

    if sl_price <= 0 or tp_price <= 0:
        return ExecutionResult(
            success=False,
            reason=f"computed sl/tp invalid: sl={sl_price:.5f} tp={tp_price:.5f}",
        )

    # ------------------------------------------------------------------ #
    # Determine initial filling mode from broker/symbol info              #
    # ------------------------------------------------------------------ #
    # Exness returns filling_mode=0 — use IOC as default for Hedge accounts.
    # If broker exposes the bitmask, prefer FOK → IOC → RETURN.
    sym_info = mt5.symbol_info(symbol)
    if sym_info is not None:
        fm = int(sym_info.filling_mode)
        if fm == 0:
            initial_filling = mt5.ORDER_FILLING_IOC
        elif fm & 1:
            initial_filling = mt5.ORDER_FILLING_FOK
        elif fm & 2:
            initial_filling = mt5.ORDER_FILLING_IOC
        else:
            initial_filling = mt5.ORDER_FILLING_RETURN
    else:
        initial_filling = mt5.ORDER_FILLING_IOC

    # ------------------------------------------------------------------ #
    # Filling mode retry sequence                                         #
    #                                                                      #
    # Some brokers silently return None for certain filling modes even    #
    # when the symbol is tradeable. We try up to 3 modes before giving up.#
    # Order: start with detected mode, then try alternatives.            #
    # ------------------------------------------------------------------ #
    all_modes = [mt5.ORDER_FILLING_IOC, mt5.ORDER_FILLING_FOK, mt5.ORDER_FILLING_RETURN]
    # Put detected mode first, then remaining modes in order
    retry_modes = [initial_filling] + [m for m in all_modes if m != initial_filling]

    comment = _build_comment(strategy_name, symbol, timeframe)

    base_request = {
        "action":    mt5.TRADE_ACTION_DEAL,
        "symbol":    symbol,
        "volume":    float(volume),
        "type":      order_type,
        "price":     price,
        "sl":        round(sl_price, 5),
        "tp":        round(tp_price, 5),
        "deviation": 10,
        "magic":     987654,
        "comment":   comment,
    }

    result = None
    used_filling = initial_filling

    for filling_mode in retry_modes:
        request = {**base_request, "type_filling": filling_mode}
        result = mt5.order_send(request)

        if result is not None:
            used_filling = filling_mode
            break

        last_err = mt5.last_error()
        logger.warning(
            "order_send() returned None with filling=%s for %s %s — "
            "retrying next mode (last_error=%s)",
            filling_mode, strategy_name, symbol, last_err,
        )

    if result is None:
        last_err = mt5.last_error()
        logger.error(
            "order_send() returned None after all filling modes: "
            "strategy=%s symbol=%s dir=%s vol=%.4f last_error=%s",
            strategy_name, symbol, direction, volume, last_err,
        )
        return ExecutionResult(
            success=False,
            reason=f"mt5.order_send() returned None after retries (last_error={last_err})",
        )

    res_dict = result._asdict()

    if result.retcode != mt5.TRADE_RETCODE_DONE:
        logger.warning(
            "Order failed: strategy=%s symbol=%s dir=%s retcode=%s filling=%s deal=%s",
            strategy_name, symbol, direction, result.retcode, used_filling, res_dict,
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