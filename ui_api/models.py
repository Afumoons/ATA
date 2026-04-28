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
    attention_queue: List[Dict[str, Any]] = Field(default_factory=list)


class ExecutionSummaryResponse(BaseModel):
    generated_at: str
    live_state: Dict[str, Any] = Field(default_factory=dict)
    strategy_live_stats: Dict[str, Any] = Field(default_factory=dict)
    open_trades: Dict[str, Any] = Field(default_factory=dict)
    unmatched_closed_deals: Dict[str, Any] = Field(default_factory=dict)
    recent_trade_log: List[Dict[str, Any]] = Field(default_factory=list)


class PoolSummaryResponse(BaseModel):
    generated_at: str
    total: int = 0
    status_counts: Dict[str, int] = Field(default_factory=dict)
    by_slot: List[Dict[str, Any]] = Field(default_factory=list)
    top_strategies: List[Dict[str, Any]] = Field(default_factory=list)
    family_counts: Dict[str, int] = Field(default_factory=dict)
    symbol_counts: Dict[str, int] = Field(default_factory=dict)


class ManifestResponse(BaseModel):
    schema_version: int = 1
    generated_at: Optional[str] = None
    source: str = "pool_state"
    entry_count: int = 0
    entries: List[Dict[str, Any]] = Field(default_factory=list)


class StrategyDetailResponse(BaseModel):
    name: str
    manifest_entry: Optional[Dict[str, Any]] = None
    index_entry: Optional[Dict[str, Any]] = None
    pool_record: Optional[Dict[str, Any]] = None
    live_stats: Optional[Dict[str, Any]] = None
    derived: Dict[str, Any] = Field(default_factory=dict)


class ResearchSummaryResponse(BaseModel):
    generated_at: str
    symbol: str
    timeframe: str
    families: Dict[str, Any] = Field(default_factory=dict)
    funnel_totals: Dict[str, int] = Field(default_factory=dict)
    rejection_totals: Dict[str, int] = Field(default_factory=dict)
    top_rejection_samples: Dict[str, List[str]] = Field(default_factory=dict)


class DriftSummaryResponse(BaseModel):
    generated_at: str
    rows: List[Dict[str, Any]] = Field(default_factory=list)
    summary: Dict[str, Any] = Field(default_factory=dict)


class AuditTimelineResponse(BaseModel):
    generated_at: str
    events: List[Dict[str, Any]] = Field(default_factory=list)
