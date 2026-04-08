from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str = "ok"
    service: str = "autonomous_trading_ai.ui_api"


class SlotCount(BaseModel):
    symbol: str
    timeframe: str
    count: int


class OverviewResponse(BaseModel):
    generated_at: str
    live_state_date: Optional[str] = None
    equity_current: Optional[float] = None
    daily_pnl: Optional[float] = None
    trades_today: Optional[int] = None
    locked_for_day: Optional[bool] = None
    pool_total: int = 0
    pool_status_counts: Dict[str, int] = Field(default_factory=dict)
    manifest_entry_count: int = 0
    strategy_index_entry_count: int = 0
    live_slots: List[SlotCount] = Field(default_factory=list)
    diagnostics: Dict[str, Any] = Field(default_factory=dict)
