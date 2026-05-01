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
    execution_artifact_warnings: Dict[str, Any] = Field(default_factory=dict)
    trade_context_registration_failures: Dict[str, Any] = Field(default_factory=dict)
    recent_activity: Dict[str, Any] = Field(default_factory=dict)
    no_trade_diagnosis: Dict[str, Any] = Field(default_factory=dict)
    manual_trade_lifecycle: Dict[str, Any] = Field(default_factory=dict)
    recent_trade_log: List[Dict[str, Any]] = Field(default_factory=list)


class PoolSummaryResponse(BaseModel):
    generated_at: str
    total: int = 0
    status_counts: Dict[str, int] = Field(default_factory=dict)
    by_slot: List[Dict[str, Any]] = Field(default_factory=list)
    top_strategies: List[Dict[str, Any]] = Field(default_factory=list)
    family_counts: Dict[str, int] = Field(default_factory=dict)
    symbol_counts: Dict[str, int] = Field(default_factory=dict)
    family_comparison: Dict[str, Any] = Field(default_factory=dict)


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
    family_skip_drilldown: List[Dict[str, Any]] = Field(default_factory=list)
    available_filters: Dict[str, Any] = Field(default_factory=dict)
    comparison: Dict[str, Any] = Field(default_factory=dict)


class DriftSummaryResponse(BaseModel):
    generated_at: str
    rows: List[Dict[str, Any]] = Field(default_factory=list)
    manual_review_queue: List[Dict[str, Any]] = Field(default_factory=list)
    summary: Dict[str, Any] = Field(default_factory=dict)


class ReviewQueueResponse(BaseModel):
    generated_at: str
    rows: List[Dict[str, Any]] = Field(default_factory=list)
    summary: Dict[str, Any] = Field(default_factory=dict)


class AuditTimelineResponse(BaseModel):
    generated_at: str
    events: List[Dict[str, Any]] = Field(default_factory=list)


class ManualTradeSymbolSpecModel(BaseModel):
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


class ManualTradeRiskCalcRequest(BaseModel):
    symbol: str
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
    order_type: str = "market"
    symbol_spec: Optional[ManualTradeSymbolSpecModel] = None


class ManualTradeRiskCalcResponse(BaseModel):
    generated_at: str
    symbol_spec: Dict[str, Any] = Field(default_factory=dict)
    symbol_spec_warnings: List[str] = Field(default_factory=list)
    derived: Dict[str, Any] = Field(default_factory=dict)
    preview_payload: Dict[str, Any] = Field(default_factory=dict)


class ManualTradePreviewAuditResponse(BaseModel):
    generated_at: str
    broker_validation: Dict[str, Any] = Field(default_factory=dict)
    audit_event: Dict[str, Any] = Field(default_factory=dict)


class ManualTradeQuoteResponse(BaseModel):
    generated_at: str
    symbol: str
    symbol_canonical: str
    execution_symbol: str
    bid: Optional[float] = None
    ask: Optional[float] = None
    last: Optional[float] = None
    spread: Optional[float] = None
    point_size: Optional[float] = None
    tick_size: Optional[float] = None
    digits: Optional[int] = None
    account_equity: Optional[float] = None
    account_balance: Optional[float] = None
    account_margin_free: Optional[float] = None
    source: str = "mt5.symbol_info_tick"


class ManualTradeSubmitRequest(ManualTradeRiskCalcRequest):
    confirm_submit: bool = False
    client_submission_id: str


class ManualTradeSubmitResponse(BaseModel):
    generated_at: str
    submit_status: str
    duplicate_submission: bool = False
    client_submission_id: str
    preview_fingerprint: str
    broker_validation: Dict[str, Any] = Field(default_factory=dict)
    broker_response: Dict[str, Any] = Field(default_factory=dict)
    audit_event_before: Dict[str, Any] = Field(default_factory=dict)
    audit_event_after: Dict[str, Any] = Field(default_factory=dict)


class OperatorValidationErrorResponse(BaseModel):
    detail: Dict[str, Any]
