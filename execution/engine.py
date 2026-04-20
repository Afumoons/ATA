from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import MetaTrader5 as mt5

from ..logging_utils import get_logger
from ..risk.manager import AccountState, TradeRequest, RiskDecision, validate_trade
from ..config import execution_config, execution_variants_for

logger = get_logger(__name__)

# Execution logs remain file-based for easy post-mortem inspection outside MT5.
TRADES_LOG_PATH = Path(__file__).resolve().parent / execution_config.trades_log_filename

# ---------------------------------------------------------------------------
# Pip value per standard lot, per instrument family.
# These are fallback estimates used when broker metadata is incomplete.
# ---------------------------------------------------------------------------


def _pip_value_for_symbol(symbol: str) -> float:
    """Return configured pip value fallback for sizing calculations."""
    if symbol in execution_config.default_pip_value_per_lot:
        return execution_config.default_pip_value_per_lot[symbol]
    for prefix in execution_config.metals_prefixes:
        if symbol.startswith(prefix):
            return 1.0
    return 10.0


def _resolve_execution_symbol(symbol: str) -> str:
    """Resolve canonical symbol to the first execution-ready broker symbol."""
    variants = execution_variants_for(symbol) or [symbol]
    for variant in variants:
        info = mt5.symbol_info(variant)
        if info is None:
            continue
        if not bool(getattr(info, "visible", False)):
            selected = mt5.symbol_select(variant, True)
            logger.info("Execution symbol %s not visible; symbol_select -> %s", variant, selected)
            info = mt5.symbol_info(variant)
        if info is not None:
            if variant != symbol:
                logger.info("Resolved execution symbol %s -> %s", symbol, variant)
            return variant
    return symbol


def _clamp_volume(volume: float, symbol: str) -> float:
    """Clamp requested lot size to the broker's min/max/step constraints."""
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
    return f"{tf_clean}{sym_clean}{uid4}"[:execution_config.order_comment_max_length]


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
    """Validate governance constraints, size risk, then send an MT5 market order.

    Flow summary:
    1. Reject malformed or duplicate-position requests.
    2. Pull live account/tick state from MT5.
    3. Size the position from risk percentage and stop distance.
    4. Run the portfolio risk manager.
    5. Submit the order, retrying filling modes when the broker is picky.

    Notes:
    - The MT5 comment is intentionally compact and alphanumeric for broker
      compatibility.
    - Filling-mode retries exist mainly for brokers such as Exness that can
      return `None` instead of a structured rejection for some modes.
    """
    if direction not in {"long", "short"}:
        return ExecutionResult(success=False, reason=f"invalid direction: {direction}")

    if stop_loss_pips <= 0:
        return ExecutionResult(success=False, reason=f"non-positive stop_loss_pips: {stop_loss_pips}")

    resolved_symbol = _resolve_execution_symbol(symbol)

    try:
        from .live_state_utils import strategy_has_open_position
    except Exception:
        logger.exception("execute_trade: failed to import strategy_has_open_position")
        strategy_has_open_position = None

    if strategy_has_open_position is not None and strategy_has_open_position(
        strategy_name=strategy_name,
        symbol=resolved_symbol,
        timeframe=timeframe,
    ):
        return ExecutionResult(
            success=False,
            reason=(
                "existing_open_position: "
                f"strategy={strategy_name} symbol={resolved_symbol} timeframe={timeframe}"
            ),
        )

    tick = mt5.symbol_info_tick(resolved_symbol)
    if tick is None:
        return ExecutionResult(success=False, reason=f"no tick data for {resolved_symbol}")

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

    pv = pip_value_per_lot if pip_value_per_lot is not None else _pip_value_for_symbol(resolved_symbol)
    if pv <= 0:
        return ExecutionResult(success=False, reason=f"invalid pip_value_per_lot: {pv}")

    risk_amount = account.equity * (risk_perc / 100.0)
    raw_volume = risk_amount / (stop_loss_pips * pv)
    volume = _clamp_volume(raw_volume, resolved_symbol)

    logger.debug(
        "Sizing: strategy=%s symbol=%s equity=%.2f risk_pct=%.3f "
        "sl_pips=%.1f pip_val=%.4f raw_vol=%.4f clamped_vol=%.4f",
        strategy_name, resolved_symbol, account.equity, risk_perc,
        stop_loss_pips, pv, raw_volume, volume,
    )

    req = TradeRequest(
        strategy_name=strategy_name,
        symbol=resolved_symbol,
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
    sym_info = mt5.symbol_info(resolved_symbol)
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
    mode_map = {
        "IOC": mt5.ORDER_FILLING_IOC,
        "FOK": mt5.ORDER_FILLING_FOK,
        "RETURN": mt5.ORDER_FILLING_RETURN,
    }
    all_modes = [mode_map[name] for name in execution_config.filling_retry_order if name in mode_map]
    if initial_filling not in all_modes:
        all_modes = [initial_filling] + all_modes
    # Put detected mode first, then remaining modes in configured order
    retry_modes = [initial_filling] + [m for m in all_modes if m != initial_filling]

    comment = _build_comment(strategy_name, resolved_symbol, timeframe)

    base_request = {
        "action":    mt5.TRADE_ACTION_DEAL,
        "symbol":    resolved_symbol,
        "volume":    float(volume),
        "type":      order_type,
        "price":     price,
        "sl":        round(sl_price, 5),
        "tp":        round(tp_price, 5),
        "deviation": execution_config.order_deviation,
        "magic":     execution_config.order_magic,
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
            filling_mode, strategy_name, resolved_symbol, last_err,
        )

    if result is None:
        last_err = mt5.last_error()
        logger.error(
            "order_send() returned None after all filling modes: "
            "strategy=%s symbol=%s dir=%s vol=%.4f last_error=%s",
            strategy_name, resolved_symbol, direction, volume, last_err,
        )
        return ExecutionResult(
            success=False,
            reason=f"mt5.order_send() returned None after retries (last_error={last_err})",
        )

    res_dict = result._asdict()

    if result.retcode != mt5.TRADE_RETCODE_DONE:
        logger.warning(
            "Order failed: strategy=%s symbol=%s dir=%s retcode=%s filling=%s deal=%s",
            strategy_name, resolved_symbol, direction, result.retcode, used_filling, res_dict,
        )
        return ExecutionResult(
            success=False,
            reason=f"order_failed: retcode={result.retcode}",
            raw_result=res_dict,
        )

    ticket = int(result.order)
    _log_trade(strategy_name, resolved_symbol, direction, volume, price, sl_price, tp_price, ticket, "executed")

    return ExecutionResult(
        success=True,
        reason="ok",
        ticket=ticket,
        volume=volume,
        price=price,
        raw_result=res_dict,
    )