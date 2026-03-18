from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Any, Optional


@dataclass
class StrategyDefinition:
    """Serializable definition of a strategy.

    This is a config object, not executable code. The backtest/execute layers
    interpret these rules over feature data.
    """

    name: str
    symbol: str
    timeframe: str

    long_entry_rule: Optional[str]
    short_entry_rule: Optional[str]
    exit_rule: str

    stop_loss_pips: float
    take_profit_pips: float

    sl_atr_mult: Optional[float] = None
    tp_atr_mult: Optional[float] = None

    # Dict[str, Any] — not Dict[str, float] — because it contains nested
    # structures (lists, dicts, strings) in addition to numeric params.
    params: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "long_entry_rule": self.long_entry_rule,
            "short_entry_rule": self.short_entry_rule,
            "exit_rule": self.exit_rule,
            "stop_loss_pips": self.stop_loss_pips,
            "take_profit_pips": self.take_profit_pips,
            "sl_atr_mult": self.sl_atr_mult,
            "tp_atr_mult": self.tp_atr_mult,
            "params": self.params,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "StrategyDefinition":
        return cls(
            name=data["name"],
            symbol=data["symbol"],
            timeframe=data["timeframe"],
            long_entry_rule=data.get("long_entry_rule"),
            short_entry_rule=data.get("short_entry_rule"),
            exit_rule=data["exit_rule"],
            stop_loss_pips=float(data["stop_loss_pips"]),
            take_profit_pips=float(data["take_profit_pips"]),
            sl_atr_mult=data.get("sl_atr_mult"),
            tp_atr_mult=data.get("tp_atr_mult"),
            params=data.get("params", {}),
        )