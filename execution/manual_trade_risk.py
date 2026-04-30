from __future__ import annotations

from dataclasses import asdict, dataclass
from math import floor, isfinite
from typing import Any, Optional

from .symbol_metadata import NormalizedSymbolSpec


_PRICE_EPSILON = 1e-9


class ManualTradeRiskError(ValueError):
    """Raised when a manual trade risk calculation cannot be performed."""


@dataclass(frozen=True)
class ManualTradeRiskRequest:
    symbol_spec: NormalizedSymbolSpec
    side: str
    entry_price: float
    risk_mode: str
    risk_value: float
    stop_loss_mode: str
    stop_loss_input: float
    take_profit_mode: Optional[str] = None
    take_profit_input: Optional[float] = None
    account_equity: Optional[float] = None
    leverage: Optional[float] = None


@dataclass(frozen=True)
class ManualTradeRiskResult:
    symbol: str
    symbol_canonical: str
    execution_symbol: str
    instrument_class: str
    side: str
    entry_price: float
    stop_loss_price: float
    take_profit_price: Optional[float]
    stop_loss_distance_price: float
    take_profit_distance_price: Optional[float]
    pip_size: float
    risk_mode: str
    risk_amount: float
    requested_risk_value: float
    lot_size: Optional[float]
    raw_lot_size: Optional[float]
    estimated_loss_at_stop: Optional[float]
    estimated_profit_at_take_profit: Optional[float]
    risk_reward_ratio: Optional[float]
    notional_estimate: Optional[float]
    margin_estimate: Optional[float]
    warnings: tuple[str, ...] = ()

    def to_payload(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["warnings"] = list(self.warnings)
        return payload


def calculate_manual_trade_risk(request: ManualTradeRiskRequest) -> ManualTradeRiskResult:
    spec = request.symbol_spec
    _validate_symbol_spec(spec)

    side = _normalize_side(request.side)
    entry_price = _require_positive_number(request.entry_price, "entry_price")
    risk_mode = _normalize_risk_mode(request.risk_mode)
    risk_value = _require_positive_number(request.risk_value, "risk_value")
    stop_loss_mode = _normalize_price_mode(request.stop_loss_mode, "stop_loss_mode")
    take_profit_mode = _normalize_optional_price_mode(request.take_profit_mode)

    risk_amount = _resolve_risk_amount(
        risk_mode=risk_mode,
        risk_value=risk_value,
        account_equity=request.account_equity,
    )
    pip_size = pip_size_for_spec(spec)

    stop_loss_price = _resolve_exit_price(
        spec=spec,
        side=side,
        anchor_price=entry_price,
        mode=stop_loss_mode,
        value=request.stop_loss_input,
        pip_size=pip_size,
        is_stop_loss=True,
    )
    stop_loss_distance = abs(entry_price - stop_loss_price)
    if stop_loss_distance <= 0:
        raise ManualTradeRiskError("stop_loss_distance_must_be_positive")

    warnings: list[str] = []
    if stop_loss_distance < spec.tick_size:
        warnings.append("stop_loss_tighter_than_tick_size")

    take_profit_price: Optional[float] = None
    take_profit_distance: Optional[float] = None
    if take_profit_mode and request.take_profit_input is not None:
        take_profit_price = _resolve_exit_price(
            spec=spec,
            side=side,
            anchor_price=entry_price,
            mode=take_profit_mode,
            value=request.take_profit_input,
            pip_size=pip_size,
            is_stop_loss=False,
        )
        take_profit_distance = abs(take_profit_price - entry_price)
        if take_profit_distance <= 0:
            raise ManualTradeRiskError("take_profit_distance_must_be_positive")

    loss_per_lot = _money_per_price_distance(spec, stop_loss_distance)
    if loss_per_lot <= 0:
        raise ManualTradeRiskError("stop_loss_money_per_lot_non_positive")

    raw_lot_size = risk_amount / loss_per_lot
    if raw_lot_size <= 0 or not isfinite(raw_lot_size):
        raise ManualTradeRiskError("raw_lot_size_non_positive")

    lot_size = _round_lot_down(raw_lot_size, spec.min_lot, spec.lot_step)
    if lot_size is None:
        warnings.append("risk_sizing_below_min_lot")
    elif lot_size > spec.max_lot + _PRICE_EPSILON:
        warnings.append("risk_sizing_exceeds_max_lot")
        lot_size = spec.max_lot
        lot_size = _round_lot_down(lot_size, spec.min_lot, spec.lot_step)

    estimated_loss_at_stop = None
    estimated_profit_at_take_profit = None
    risk_reward_ratio = None
    notional_estimate = None
    margin_estimate = None

    if lot_size is not None:
        estimated_loss_at_stop = loss_per_lot * lot_size
        if estimated_loss_at_stop + _PRICE_EPSILON < risk_amount:
            warnings.append("rounded_lot_reduces_risk_below_requested")
        if take_profit_distance is not None:
            estimated_profit_at_take_profit = _money_per_price_distance(spec, take_profit_distance) * lot_size
            if estimated_loss_at_stop > 0:
                risk_reward_ratio = estimated_profit_at_take_profit / estimated_loss_at_stop
        notional_estimate = entry_price * spec.contract_size * lot_size
        margin_estimate = _estimate_margin(notional_estimate, request.leverage)

    return ManualTradeRiskResult(
        symbol=spec.symbol,
        symbol_canonical=spec.symbol_canonical,
        execution_symbol=spec.execution_symbol,
        instrument_class=spec.instrument_class,
        side=side,
        entry_price=_normalize_price(spec, entry_price),
        stop_loss_price=stop_loss_price,
        take_profit_price=take_profit_price,
        stop_loss_distance_price=stop_loss_distance,
        take_profit_distance_price=take_profit_distance,
        pip_size=pip_size,
        risk_mode=risk_mode,
        risk_amount=risk_amount,
        requested_risk_value=risk_value,
        lot_size=lot_size,
        raw_lot_size=raw_lot_size,
        estimated_loss_at_stop=estimated_loss_at_stop,
        estimated_profit_at_take_profit=estimated_profit_at_take_profit,
        risk_reward_ratio=risk_reward_ratio,
        notional_estimate=notional_estimate,
        margin_estimate=margin_estimate,
        warnings=tuple(warnings),
    )


def pip_size_for_spec(spec: NormalizedSymbolSpec) -> float:
    _validate_symbol_spec(spec)
    if spec.instrument_class == "forex":
        multiplier = 10 if spec.digits in (3, 5) else 1
        pip_size = spec.point_size * multiplier
    else:
        pip_size = max(spec.point_size, spec.tick_size)
    if pip_size <= 0:
        raise ManualTradeRiskError("pip_size_non_positive")
    return pip_size


def _validate_symbol_spec(spec: NormalizedSymbolSpec) -> None:
    if spec.digits < 0:
        raise ManualTradeRiskError("symbol_spec_digits_invalid")
    for field_name in (
        "point_size",
        "tick_size",
        "tick_value",
        "contract_size",
        "min_lot",
        "lot_step",
        "max_lot",
    ):
        value = float(getattr(spec, field_name) or 0.0)
        if value <= 0:
            raise ManualTradeRiskError(f"symbol_spec_{field_name}_must_be_positive")
    if spec.min_lot > spec.max_lot:
        raise ManualTradeRiskError("symbol_spec_min_lot_exceeds_max_lot")


def _normalize_side(value: str) -> str:
    normalized = str(value or "").strip().lower()
    if normalized not in {"buy", "sell"}:
        raise ManualTradeRiskError("side_must_be_buy_or_sell")
    return normalized


def _normalize_risk_mode(value: str) -> str:
    normalized = str(value or "").strip().lower()
    if normalized not in {"money", "equity_pct"}:
        raise ManualTradeRiskError("risk_mode_must_be_money_or_equity_pct")
    return normalized


def _normalize_price_mode(value: str, field_name: str) -> str:
    normalized = str(value or "").strip().lower()
    if normalized not in {"pips", "price"}:
        raise ManualTradeRiskError(f"{field_name}_must_be_pips_or_price")
    return normalized


def _normalize_optional_price_mode(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    return _normalize_price_mode(value, "take_profit_mode")


def _require_positive_number(value: float, field_name: str) -> float:
    number = float(value)
    if not isfinite(number) or number <= 0:
        raise ManualTradeRiskError(f"{field_name}_must_be_positive")
    return number


def _resolve_risk_amount(*, risk_mode: str, risk_value: float, account_equity: Optional[float]) -> float:
    if risk_mode == "money":
        return risk_value
    equity = _require_positive_number(account_equity, "account_equity")
    return equity * (risk_value / 100.0)


def _resolve_exit_price(
    *,
    spec: NormalizedSymbolSpec,
    side: str,
    anchor_price: float,
    mode: str,
    value: float,
    pip_size: float,
    is_stop_loss: bool,
) -> float:
    normalized_anchor = _normalize_price(spec, anchor_price)
    raw_value = _require_positive_number(value, "exit_value")

    if mode == "pips":
        distance = raw_value * pip_size
        price = normalized_anchor - distance if (side == "buy") == is_stop_loss else normalized_anchor + distance
    else:
        price = raw_value

    normalized_price = _normalize_price(spec, price)
    if normalized_price <= 0:
        raise ManualTradeRiskError("normalized_price_must_be_positive")

    if is_stop_loss:
        if side == "buy" and normalized_price >= normalized_anchor:
            raise ManualTradeRiskError("stop_loss_must_be_below_entry_for_buy")
        if side == "sell" and normalized_price <= normalized_anchor:
            raise ManualTradeRiskError("stop_loss_must_be_above_entry_for_sell")
    else:
        if side == "buy" and normalized_price <= normalized_anchor:
            raise ManualTradeRiskError("take_profit_must_be_above_entry_for_buy")
        if side == "sell" and normalized_price >= normalized_anchor:
            raise ManualTradeRiskError("take_profit_must_be_below_entry_for_sell")

    return normalized_price


def _normalize_price(spec: NormalizedSymbolSpec, price: float) -> float:
    units = round(float(price) / spec.tick_size)
    normalized = units * spec.tick_size
    return round(normalized, spec.digits)


def _money_per_price_distance(spec: NormalizedSymbolSpec, price_distance: float) -> float:
    if price_distance <= 0:
        return 0.0
    ticks = price_distance / spec.tick_size
    return ticks * spec.tick_value


def _round_lot_down(raw_lot_size: float, min_lot: float, lot_step: float) -> Optional[float]:
    if raw_lot_size + _PRICE_EPSILON < min_lot:
        return None
    steps = floor(((raw_lot_size - min_lot) / lot_step) + _PRICE_EPSILON)
    lot_size = min_lot + max(steps, 0) * lot_step
    decimals = _decimal_places(lot_step)
    return round(lot_size, decimals)


def _decimal_places(value: float) -> int:
    text = f"{value:.10f}".rstrip("0")
    if "." not in text:
        return 0
    return len(text.split(".", 1)[1])


def _estimate_margin(notional_estimate: Optional[float], leverage: Optional[float]) -> Optional[float]:
    if notional_estimate is None or leverage is None:
        return None
    leverage_value = _require_positive_number(leverage, "leverage")
    return notional_estimate / leverage_value


__all__ = [
    "ManualTradeRiskError",
    "ManualTradeRiskRequest",
    "ManualTradeRiskResult",
    "calculate_manual_trade_risk",
    "pip_size_for_spec",
]
