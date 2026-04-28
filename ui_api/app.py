from __future__ import annotations

from fastapi import FastAPI, HTTPException

from .adapters import (
    build_overview_payload,
    load_audit_timeline,
    load_drift_summary,
    load_execution_summary,
    load_manifest_payload,
    load_pool_summary_payload,
    load_research_summary,
    load_strategies_summary,
    load_strategy_detail,
)
from .logging_utils import ui_logger
from .models import (
    AuditTimelineResponse,
    DriftSummaryResponse,
    ExecutionSummaryResponse,
    HealthResponse,
    ManifestResponse,
    OverviewResponse,
    PoolSummaryResponse,
    ResearchSummaryResponse,
    StrategyDetailResponse,
)

app = FastAPI(title="autonomous_trading_ai UI API", version="v1")


@app.on_event("startup")
def log_startup() -> None:
    ui_logger.info("UI API startup")


@app.get("/api/health", response_model=HealthResponse)
def api_health() -> HealthResponse:
    return HealthResponse()


@app.get("/api/overview", response_model=OverviewResponse)
def api_overview() -> OverviewResponse:
    payload = build_overview_payload()
    return OverviewResponse.model_validate(payload)


@app.get("/api/execution/summary", response_model=ExecutionSummaryResponse)
def api_execution_summary() -> ExecutionSummaryResponse:
    return ExecutionSummaryResponse.model_validate(load_execution_summary())


@app.get("/api/pool/summary", response_model=PoolSummaryResponse)
def api_pool_summary() -> PoolSummaryResponse:
    return PoolSummaryResponse.model_validate(load_pool_summary_payload())


@app.get("/api/manifest", response_model=ManifestResponse)
def api_manifest() -> ManifestResponse:
    return ManifestResponse.model_validate(load_manifest_payload())


@app.get("/api/strategies")
def api_strategies() -> list[dict]:
    return load_strategies_summary()


@app.get("/api/strategies/{name}", response_model=StrategyDetailResponse)
def api_strategy_detail(name: str) -> StrategyDetailResponse:
    payload = load_strategy_detail(name)
    if payload is None:
        raise HTTPException(status_code=404, detail="strategy not found")
    return StrategyDetailResponse.model_validate(payload)


@app.get("/api/research/summary", response_model=ResearchSummaryResponse)
def api_research_summary(symbol: str = "XAUUSDm", timeframe: str = "M15") -> ResearchSummaryResponse:
    payload = load_research_summary(symbol=symbol, timeframe=timeframe)
    if payload is None:
        raise HTTPException(status_code=404, detail="research summary not found")
    return ResearchSummaryResponse.model_validate(payload)


@app.get("/api/drift/summary", response_model=DriftSummaryResponse)
def api_drift_summary() -> DriftSummaryResponse:
    return DriftSummaryResponse.model_validate(load_drift_summary())


@app.get("/api/audit/timeline", response_model=AuditTimelineResponse)
def api_audit_timeline(limit: int = 100) -> AuditTimelineResponse:
    limit = max(1, min(limit, 500))
    return AuditTimelineResponse.model_validate(load_audit_timeline(limit=limit))
