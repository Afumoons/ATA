from __future__ import annotations

"""Execution bridge for externally parsed Telegram trade plans.

Live execution is deliberately guarded by two switches:
1. caller must pass mode="auto_live"
2. env ATA_TELEGRAM_SIGNAL_LIVE must be "true"

This protects shadow deployments from accidentally sending orders while still
keeping the live path explicit and testable.
"""

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
from typing import Any, Literal, Optional

import MetaTrader5 as mt5

from ..config import execution_config
from ..logging_utils import get_logger
from ..risk.manager import AccountState, RiskDecision, TradeRequest, validate_trade
from .engine import ExecutionResult, _build_comment, _clamp_volume, _resolve_execution_symbol
from .external_signal import ExternalSignalConfig, ExternalTradePlan, resolve_default_pip_value
from .trade_context_journal import register_trade_entry_context

logger = get_logger(__name__)

Mode = Literal["shadow", "auto_live"]

BASE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_DUPLICATE_STORE = BASE_DIR / "execution" / "external_signal_seen.json"
DEFAULT_EXECUTION_AUDIT = BASE_DIR / "execution" / "external_signal_execution.jsonl"
EXTERNAL_SIGNAL_STRATEGY = "telegram_signal_xau"
EXTERNAL_SIGNAL_TIMEFRAME = "EXT"
LIVE_ENV_FLAG = "ATA_TELEGRAM_SIGNAL_LIVE"


@dataclass(frozen=True)
class ExternalExecutionDecision:
    signal_id: str
    mode: Mode
    action: str
    reason: str
    request: Optional[dict[str, Any]] = None
    result: Optional[dict[str, Any]] = None

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["ts"] = datetime.now(timezone.utc).isoformat()
        return payload


def _append_execution_audit(decision: ExternalExecutionDecision, path: Path | None = None) -> None:
    audit_path = path or DEFAULT_EXECUTION_AUDIT
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    with audit_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(decision.to_dict(), ensure_ascii=False, sort_keys=True) + "\n")


class SignalDuplicateStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or DEFAULT_DUPLICATE_STORE

    def _load(self) -> set[str]:
        if not self.path.exists():
            return set()
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            logger.exception("Failed to read duplicate store %s; treating as empty", self.path)
            return set()
        if isinstance(data, list):
            return {str(x) for x in data}
        if isinstance(data, dict):
            return {str(x) for x in data.get("signal_ids", [])}
        return set()

    def seen(self, signal_id: str) -> bool:
        return signal_id in self._load()

    def mark_seen(self, signal_id: str) -> None:
        values = self._load()
        values.add(signal_id)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "signal_ids": sorted(values),
        }
        self.path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _account_state() -> AccountState:
    info = mt5.account_info()
    if info is None:
        raise RuntimeError("MT5 account_info() returned None — not logged in?")
    positions = mt5.positions_get()
    return AccountState(
        equity=float(info.equity),
        balance=float(info.balance),
        open_positions=len(positions) if positions else 0,
    )


def _pick_filling_modes(symbol: str) -> list[int]:
    sym_info = mt5.symbol_info(symbol)
    if sym_info is not None:
        fm = int(getattr(sym_info, "filling_mode", 0) or 0)
        if fm == 0:
            initial = mt5.ORDER_FILLING_IOC
        elif fm & 1:
            initial = mt5.ORDER_FILLING_FOK
        elif fm & 2:
            initial = mt5.ORDER_FILLING_IOC
        else:
            initial = mt5.ORDER_FILLING_RETURN
    else:
        initial = mt5.ORDER_FILLING_IOC

    mode_map = {
        "IOC": mt5.ORDER_FILLING_IOC,
        "FOK": mt5.ORDER_FILLING_FOK,
        "RETURN": mt5.ORDER_FILLING_RETURN,
    }
    configured = [mode_map[name] for name in execution_config.filling_retry_order if name in mode_map]
    return [initial] + [m for m in configured if m != initial]


def _derive_prices_from_plan(
    plan: ExternalTradePlan,
    *,
    fill_reference: float,
    cfg: ExternalSignalConfig,
) -> tuple[float, float, Optional[float]]:
    if plan.direction not in {"long", "short"}:
        raise ValueError("plan direction is required for execution")

    sl = plan.stop_loss_price
    if sl is None:
        distance = cfg.default_sl_pips * cfg.pip_size
        sl = fill_reference - distance if plan.direction == "long" else fill_reference + distance

    tp = plan.take_profit_price
    return fill_reference, float(sl), float(tp) if tp is not None else None


def build_external_order_request(
    plan: ExternalTradePlan,
    *,
    cfg: ExternalSignalConfig | None = None,
    equity_peak: Optional[float] = None,
) -> dict[str, Any]:
    """Build an MT5 order request from an absolute-SL external plan.

    This function reads current tick/account state and sizes risk against the
    distance from actual market fill reference to the absolute SL.  Therefore a
    worse fill reduces lot size instead of widening the invalidation level.
    """

    config = cfg or ExternalSignalConfig()
    if plan.decision != "planned":
        raise ValueError(f"plan is not executable: {plan.decision} {plan.reason}")
    if plan.direction not in {"long", "short"}:
        raise ValueError("plan direction is required")

    resolved_symbol = _resolve_execution_symbol(plan.symbol)
    tick = mt5.symbol_info_tick(resolved_symbol)
    if tick is None:
        raise RuntimeError(f"no tick data for {resolved_symbol}")

    order_type = mt5.ORDER_TYPE_BUY if plan.direction == "long" else mt5.ORDER_TYPE_SELL
    market_price = float(tick.ask if plan.direction == "long" else tick.bid)
    _, sl_price, tp_price = _derive_prices_from_plan(plan, fill_reference=market_price, cfg=config)

    if plan.direction == "long" and sl_price >= market_price:
        raise ValueError(f"long SL must be below market price: market={market_price} sl={sl_price}")
    if plan.direction == "short" and sl_price <= market_price:
        raise ValueError(f"short SL must be above market price: market={market_price} sl={sl_price}")

    stop_pips = abs(market_price - sl_price) / config.pip_size
    if stop_pips <= 0:
        raise ValueError(f"invalid stop distance: {stop_pips}")

    account = _account_state()
    if equity_peak is None:
        equity_peak = account.equity
    pip_value = resolve_default_pip_value(resolved_symbol)
    raw_volume = (account.equity * (plan.risk_perc / 100.0)) / (stop_pips * pip_value)
    volume = _clamp_volume(raw_volume, resolved_symbol)

    req = TradeRequest(
        strategy_name=EXTERNAL_SIGNAL_STRATEGY,
        symbol=resolved_symbol,
        direction=plan.direction,
        volume=volume,
        risk_perc=plan.risk_perc,
    )
    decision: RiskDecision = validate_trade(account, req, equity_peak)
    if not decision.allowed:
        raise RuntimeError(f"risk_reject: {decision.reason}")

    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": resolved_symbol,
        "volume": float(volume),
        "type": order_type,
        "price": market_price,
        "sl": round(sl_price, 5),
        "tp": round(tp_price, 5) if tp_price is not None else 0.0,
        "deviation": execution_config.order_deviation,
        "magic": execution_config.order_magic,
        "comment": _build_comment(EXTERNAL_SIGNAL_STRATEGY, resolved_symbol, EXTERNAL_SIGNAL_TIMEFRAME),
    }
    request["external_signal"] = {
        "signal_id": plan.signal_id,
        "source": plan.source,
        "message_id": plan.message_id,
        "exit_mode": plan.exit_mode,
        "trailing_stop_pips": plan.trailing_stop_pips,
        "entry_reference": plan.entry_reference,
        "sizing_stop_pips": stop_pips,
        "raw_volume": raw_volume,
    }
    return request


def execute_external_trade_plan(
    plan: ExternalTradePlan,
    *,
    mode: Mode = "shadow",
    cfg: ExternalSignalConfig | None = None,
    duplicate_store: SignalDuplicateStore | None = None,
    audit_path: Path | None = None,
) -> ExternalExecutionDecision:
    store = duplicate_store or SignalDuplicateStore()

    if plan.decision != "planned":
        decision = ExternalExecutionDecision(plan.signal_id, mode, "skip", plan.reason)
        _append_execution_audit(decision, audit_path)
        return decision

    if store.seen(plan.signal_id):
        decision = ExternalExecutionDecision(plan.signal_id, mode, "skip", "duplicate_signal")
        _append_execution_audit(decision, audit_path)
        return decision

    if mode == "shadow":
        decision = ExternalExecutionDecision(plan.signal_id, mode, "shadow", "would_execute_if_live")
        _append_execution_audit(decision, audit_path)
        store.mark_seen(plan.signal_id)
        return decision

    if os.getenv(LIVE_ENV_FLAG, "").strip().lower() != "true":
        decision = ExternalExecutionDecision(
            plan.signal_id,
            mode,
            "blocked",
            f"live guard disabled; set {LIVE_ENV_FLAG}=true to allow orders",
        )
        _append_execution_audit(decision, audit_path)
        return decision

    try:
        request = build_external_order_request(plan, cfg=cfg)
        mt5_request = {k: v for k, v in request.items() if k != "external_signal"}
        result = None
        used_filling = None
        for filling in _pick_filling_modes(str(mt5_request["symbol"])):
            result = mt5.order_send({**mt5_request, "type_filling": filling})
            used_filling = filling
            if result is not None:
                break
        if result is None:
            raise RuntimeError(f"mt5.order_send returned None after retries last_error={mt5.last_error()}")
        raw_result = result._asdict()
        raw_result["used_filling"] = used_filling
        if result.retcode != mt5.TRADE_RETCODE_DONE:
            decision = ExternalExecutionDecision(
                plan.signal_id,
                mode,
                "rejected",
                f"order_failed: retcode={result.retcode}",
                request=request,
                result=raw_result,
            )
            _append_execution_audit(decision, audit_path)
            return decision

        store.mark_seen(plan.signal_id)
        try:
            register_trade_entry_context(
                ticket=int(result.order),
                strategy_name=EXTERNAL_SIGNAL_STRATEGY,
                symbol=str(mt5_request["symbol"]),
                timeframe=EXTERNAL_SIGNAL_TIMEFRAME,
            )
        except Exception:
            logger.exception("Failed to register external signal trade context")
        decision = ExternalExecutionDecision(plan.signal_id, mode, "executed", "ok", request=request, result=raw_result)
        _append_execution_audit(decision, audit_path)
        return decision
    except Exception as exc:
        logger.exception("External signal execution failed")
        decision = ExternalExecutionDecision(plan.signal_id, mode, "error", str(exc))
        _append_execution_audit(decision, audit_path)
        return decision
