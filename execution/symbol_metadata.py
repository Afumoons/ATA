from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping, Optional

try:
    from ..config import canonical_symbol, execution_variants_for
except ImportError:
    from config import canonical_symbol, execution_variants_for

try:
    import MetaTrader5 as mt5  # type: ignore
except Exception:  # pragma: no cover - optional at import time for docs/tests
    mt5 = None


_REQUIRED_NUMERIC_FIELDS = (
    "digits",
    "point_size",
    "tick_size",
    "tick_value",
    "contract_size",
    "min_lot",
    "lot_step",
    "max_lot",
)


@dataclass(frozen=True)
class NormalizedSymbolSpec:
    symbol: str
    symbol_canonical: str
    execution_symbol: str
    instrument_class: str
    digits: int
    point_size: float
    tick_size: float
    tick_value: float
    contract_size: float
    min_lot: float
    lot_step: float
    max_lot: float
    source: str = "mt5.symbol_info"

    def to_payload(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SymbolSpecSnapshot:
    spec: NormalizedSymbolSpec
    warnings: tuple[str, ...] = ()

    def to_payload(self) -> dict[str, Any]:
        return {
            "spec": self.spec.to_payload(),
            "warnings": list(self.warnings),
        }


def classify_instrument(symbol: str | None) -> str:
    sym = canonical_symbol(symbol).upper()
    if not sym:
        return "unknown"
    if any(token in sym for token in ("XAU", "XAG", "GOLD", "SILVER")):
        return "metals"
    if any(token in sym for token in ("BTC", "ETH", "SOL", "XRP", "LTC", "DOGE", "ADA")):
        return "crypto"
    if len(sym) >= 6 and sym[:6].isalpha():
        return "forex"
    return "unknown"



def _get_attr(info: Any, *names: str, default: Any = None) -> Any:
    if info is None:
        return default
    if isinstance(info, Mapping):
        for name in names:
            if name in info and info[name] is not None:
                return info[name]
        return default
    for name in names:
        value = getattr(info, name, None)
        if value is not None:
            return value
    return default



def normalize_symbol_spec(symbol: str, info: Any, *, execution_symbol: Optional[str] = None, source: str = "mt5.symbol_info") -> SymbolSpecSnapshot:
    canon = canonical_symbol(symbol)
    resolved_execution_symbol = str(execution_symbol or _get_attr(info, "name", default=symbol) or symbol)
    spec = NormalizedSymbolSpec(
        symbol=str(symbol),
        symbol_canonical=canon,
        execution_symbol=resolved_execution_symbol,
        instrument_class=classify_instrument(canon),
        digits=int(_get_attr(info, "digits", default=0) or 0),
        point_size=float(_get_attr(info, "point", "point_size", default=0.0) or 0.0),
        tick_size=float(_get_attr(info, "trade_tick_size", "tick_size", default=0.0) or 0.0),
        tick_value=float(_get_attr(info, "trade_tick_value", "tick_value", default=0.0) or 0.0),
        contract_size=float(_get_attr(info, "trade_contract_size", "contract_size", default=0.0) or 0.0),
        min_lot=float(_get_attr(info, "volume_min", "min_lot", default=0.0) or 0.0),
        lot_step=float(_get_attr(info, "volume_step", "lot_step", default=0.0) or 0.0),
        max_lot=float(_get_attr(info, "volume_max", "max_lot", default=0.0) or 0.0),
        source=source,
    )
    warnings: list[str] = []
    if spec.digits < 0:
        warnings.append("invalid_digits")
    for field_name in _REQUIRED_NUMERIC_FIELDS[1:]:
        if float(getattr(spec, field_name) or 0.0) <= 0:
            warnings.append(f"missing_or_non_positive_{field_name}")
    if spec.max_lot > 0 and spec.min_lot > spec.max_lot:
        warnings.append("min_lot_exceeds_max_lot")
    if spec.lot_step > 0 and spec.min_lot > 0 and spec.lot_step > spec.max_lot > 0:
        warnings.append("lot_step_exceeds_max_lot")
    return SymbolSpecSnapshot(spec=spec, warnings=tuple(warnings))



def fetch_symbol_spec(symbol: str, *, ensure_visible: bool = True) -> SymbolSpecSnapshot:
    if mt5 is None:
        raise RuntimeError("MetaTrader5 module is unavailable")

    attempted: list[str] = []
    for candidate in execution_variants_for(symbol) or [symbol]:
        attempted.append(candidate)
        info = mt5.symbol_info(candidate)
        if info is None:
            continue
        if ensure_visible and not bool(getattr(info, "visible", False)):
            mt5.symbol_select(candidate, True)
            info = mt5.symbol_info(candidate)
        if info is not None:
            return normalize_symbol_spec(symbol, info, execution_symbol=candidate)

    raise RuntimeError(
        f"Could not resolve broker symbol metadata for {symbol}; attempted={attempted}"
    )


__all__ = [
    "NormalizedSymbolSpec",
    "SymbolSpecSnapshot",
    "classify_instrument",
    "fetch_symbol_spec",
    "normalize_symbol_spec",
]
