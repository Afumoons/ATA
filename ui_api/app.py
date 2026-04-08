from __future__ import annotations

from fastapi import FastAPI

from .adapters import build_overview_payload
from .logging_utils import ui_logger
from .models import HealthResponse, OverviewResponse

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
