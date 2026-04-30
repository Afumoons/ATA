from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

from fastapi import FastAPI, HTTPException

from .adapters import (
    build_overview_payload,
    load_audit_timeline,
    load_drift_summary,
    load_execution_summary,
    load_live_state_snapshot,
    load_manifest_payload,
    load_pool_summary_payload,
    load_research_summary,
    load_review_queue,
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
    ManualTradeRiskCalcRequest,
    ManualTradeRiskCalcResponse,
    OverviewResponse,
    OperatorValidationErrorResponse,
    PoolSummaryResponse,
    ResearchSummaryResponse,
    ReviewQueueResponse,
    StrategyDetailResponse,
)
from ..execution.manual_trade_risk import (
    ManualTradeRiskError,
    ManualTradeRiskRequest,
    calculate_manual_trade_risk,
)
from ..execution.symbol_metadata import NormalizedSymbolSpec, fetch_symbol_spec

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


@app.get("/api/review/queue", response_model=ReviewQueueResponse)
def api_review_queue() -> ReviewQueueResponse:
    return ReviewQueueResponse.model_validate(load_review_queue())


@app.get("/api/audit/timeline", response_model=AuditTimelineResponse)
def api_audit_timeline(limit: int = 100) -> AuditTimelineResponse:
    limit = max(1, min(limit, 500))
    return AuditTimelineResponse.model_validate(load_audit_timeline(limit=limit))


@app.post(
    "/api/execution/risk-calc",
    response_model=ManualTradeRiskCalcResponse,
    responses={422: {"model": OperatorValidationErrorResponse}},
)
def api_execution_risk_calc(payload: ManualTradeRiskCalcRequest) -> ManualTradeRiskCalcResponse:
    order_type = _normalize_order_type(payload.order_type)
    spec_snapshot = _resolve_symbol_spec(payload)
    account_equity = payload.account_equity
    if str(payload.risk_mode or "").strip().lower() == "equity_pct" and account_equity is None:
        account_equity = _resolve_account_equity_from_live_state()

    try:
        result = calculate_manual_trade_risk(
            ManualTradeRiskRequest(
                symbol_spec=spec_snapshot.spec,
                side=payload.side,
                entry_price=payload.entry_price,
                risk_mode=payload.risk_mode,
                risk_value=payload.risk_value,
                stop_loss_mode=payload.stop_loss_mode,
                stop_loss_input=payload.stop_loss_input,
                take_profit_mode=payload.take_profit_mode,
                take_profit_input=payload.take_profit_input,
                account_equity=account_equity,
                leverage=payload.leverage,
            )
        )
    except ManualTradeRiskError as exc:
        raise _operator_validation_error(str(exc), field=_field_for_risk_error(str(exc))) from exc

    return ManualTradeRiskCalcResponse(
        generated_at=datetime.now(timezone.utc).isoformat(),
        symbol_spec=spec_snapshot.spec.to_payload(),
        symbol_spec_warnings=list(spec_snapshot.warnings),
        derived=result.to_payload(),
        preview_payload={
            "symbol": result.symbol,
            "symbol_canonical": result.symbol_canonical,
            "execution_symbol": result.execution_symbol,
            "instrument_class": result.instrument_class,
            "side": result.side,
            "order_type": order_type,
            "entry_price": result.entry_price,
            "stop_loss_price": result.stop_loss_price,
            "take_profit_price": result.take_profit_price,
            "lot_size": result.lot_size,
            "risk_mode": result.risk_mode,
            "risk_value": result.requested_risk_value,
            "risk_amount": result.risk_amount,
            "stop_loss_mode": payload.stop_loss_mode,
            "stop_loss_input": payload.stop_loss_input,
            "take_profit_mode": payload.take_profit_mode,
            "take_profit_input": payload.take_profit_input,
            "order_origin": "manual_user",
            "execution_origin": "operator_ui",
            "is_manual": True,
            "exclude_from_strategy_eval": True,
            "comment_tag": "clio-manual-user",
            "warnings": list(result.warnings),
        },
    )


def _resolve_symbol_spec(payload: ManualTradeRiskCalcRequest):
    if payload.symbol_spec is not None:
        return SimpleNamespace(**{
            "spec": NormalizedSymbolSpec(**payload.symbol_spec.model_dump()),
            "warnings": (),
        })
    try:
        return fetch_symbol_spec(payload.symbol)
    except Exception as exc:
        raise _operator_validation_error(
            "symbol_metadata_unavailable",
            field="symbol",
            meta={"symbol": payload.symbol},
        ) from exc


def _resolve_account_equity_from_live_state() -> float:
    live_state = load_live_state_snapshot()
    equity = float(live_state.get("equity_current") or 0.0)
    if equity <= 0:
        raise _operator_validation_error("account_equity_unavailable", field="account_equity")
    return equity


def _normalize_order_type(value: str) -> str:
    normalized = str(value or "market").strip().lower()
    if normalized not in {"market", "limit"}:
        raise _operator_validation_error("order_type_must_be_market_or_limit", field="order_type")
    return normalized


def _operator_validation_error(code: str, *, field: str | None = None, meta: dict | None = None) -> HTTPException:
    detail = {
        "code": code,
        "message": _operator_message_for(code),
    }
    if field:
        detail["field"] = field
    if meta:
        detail["meta"] = meta
    return HTTPException(status_code=422, detail=detail)


def _field_for_risk_error(code: str) -> str | None:
    mapping = {
        "side_must_be_buy_or_sell": "side",
        "risk_mode_must_be_money_or_equity_pct": "risk_mode",
        "stop_loss_mode_must_be_pips_or_price": "stop_loss_mode",
        "take_profit_mode_must_be_pips_or_price": "take_profit_mode",
        "entry_price_must_be_positive": "entry_price",
        "risk_value_must_be_positive": "risk_value",
        "account_equity_must_be_positive": "account_equity",
        "leverage_must_be_positive": "leverage",
        "stop_loss_must_be_below_entry_for_buy": "stop_loss_input",
        "stop_loss_must_be_above_entry_for_sell": "stop_loss_input",
        "take_profit_must_be_above_entry_for_buy": "take_profit_input",
        "take_profit_must_be_below_entry_for_sell": "take_profit_input",
    }
    return mapping.get(code)


def _operator_message_for(code: str) -> str:
    messages = {
        "symbol_metadata_unavailable": "Metadata simbol broker tidak tersedia, jadi kalkulator manual trade belum bisa dipakai untuk simbol ini.",
        "account_equity_unavailable": "Equity akun terbaru tidak tersedia. Isi account_equity secara eksplisit atau pastikan snapshot live state terbarui.",
        "order_type_must_be_market_or_limit": "Jenis order harus market atau limit untuk tiket manual versi pertama.",
        "side_must_be_buy_or_sell": "Sisi order harus buy atau sell.",
        "risk_mode_must_be_money_or_equity_pct": "Mode risiko harus money atau equity_pct.",
        "stop_loss_mode_must_be_pips_or_price": "Mode stop loss harus pips atau price.",
        "take_profit_mode_must_be_pips_or_price": "Mode take profit harus pips atau price.",
        "entry_price_must_be_positive": "Harga entry harus lebih besar dari nol.",
        "risk_value_must_be_positive": "Nilai risiko harus lebih besar dari nol.",
        "account_equity_must_be_positive": "Equity akun harus lebih besar dari nol untuk mode equity_pct.",
        "leverage_must_be_positive": "Leverage harus lebih besar dari nol bila diisi.",
        "stop_loss_distance_must_be_positive": "Jarak stop loss harus positif setelah dinormalisasi ke tick broker.",
        "take_profit_distance_must_be_positive": "Jarak take profit harus positif setelah dinormalisasi ke tick broker.",
        "stop_loss_must_be_below_entry_for_buy": "Untuk posisi buy, stop loss harus berada di bawah entry.",
        "stop_loss_must_be_above_entry_for_sell": "Untuk posisi sell, stop loss harus berada di atas entry.",
        "take_profit_must_be_above_entry_for_buy": "Untuk posisi buy, take profit harus berada di atas entry.",
        "take_profit_must_be_below_entry_for_sell": "Untuk posisi sell, take profit harus berada di bawah entry.",
        "raw_lot_size_non_positive": "Ukuran lot hasil kalkulasi tidak valid untuk parameter risiko ini.",
        "stop_loss_money_per_lot_non_positive": "Nilai uang per lot untuk stop loss tidak valid dari metadata simbol broker.",
    }
    return messages.get(code, code.replace("_", " "))
