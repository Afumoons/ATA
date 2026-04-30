from __future__ import annotations

import importlib

import pytest
from fastapi.testclient import TestClient

from autonomous_trading_ai.ui_api import adapters

api_app = importlib.import_module("autonomous_trading_ai.ui_api.app")


client = TestClient(api_app.app)


@pytest.mark.parametrize(
    ("symbol_spec", "payload", "expected_lot", "expected_stop", "expected_tp"),
    [
        (
            {
                "symbol": "EURUSDm",
                "symbol_canonical": "EURUSDm",
                "execution_symbol": "EURUSDm",
                "instrument_class": "forex",
                "digits": 5,
                "point_size": 0.00001,
                "tick_size": 0.00001,
                "tick_value": 1.0,
                "contract_size": 100000.0,
                "min_lot": 0.01,
                "lot_step": 0.01,
                "max_lot": 100.0,
            },
            {
                "symbol": "EURUSDm",
                "side": "buy",
                "entry_price": 1.1,
                "risk_mode": "money",
                "risk_value": 100.0,
                "stop_loss_mode": "pips",
                "stop_loss_input": 20.0,
                "take_profit_mode": "pips",
                "take_profit_input": 40.0,
                "symbol_spec": None,
            },
            0.5,
            1.098,
            1.104,
        ),
        (
            {
                "symbol": "XAUUSDm",
                "symbol_canonical": "XAUUSDm",
                "execution_symbol": "XAUUSDm",
                "instrument_class": "metals",
                "digits": 2,
                "point_size": 0.01,
                "tick_size": 0.01,
                "tick_value": 1.0,
                "contract_size": 100.0,
                "min_lot": 0.01,
                "lot_step": 0.01,
                "max_lot": 100.0,
            },
            {
                "symbol": "XAUUSDm",
                "side": "buy",
                "entry_price": 2300.0,
                "risk_mode": "equity_pct",
                "risk_value": 1.0,
                "stop_loss_mode": "price",
                "stop_loss_input": 2295.0,
                "take_profit_mode": "price",
                "take_profit_input": 2310.0,
                "account_equity": 10000.0,
                "leverage": 100.0,
                "symbol_spec": None,
            },
            0.2,
            2295.0,
            2310.0,
        ),
        (
            {
                "symbol": "BTCUSDm",
                "symbol_canonical": "BTCUSDm",
                "execution_symbol": "BTCUSDm",
                "instrument_class": "crypto",
                "digits": 2,
                "point_size": 0.01,
                "tick_size": 0.01,
                "tick_value": 1.0,
                "contract_size": 1.0,
                "min_lot": 0.01,
                "lot_step": 0.01,
                "max_lot": 10.0,
            },
            {
                "symbol": "BTCUSDm",
                "side": "sell",
                "entry_price": 60000.0,
                "risk_mode": "money",
                "risk_value": 25.0,
                "stop_loss_mode": "pips",
                "stop_loss_input": 100.0,
                "take_profit_mode": "pips",
                "take_profit_input": 300.0,
                "symbol_spec": None,
            },
            0.25,
            60001.0,
            59997.0,
        ),
        (
            {
                "symbol": "XAGUSDm",
                "symbol_canonical": "XAGUSDm",
                "execution_symbol": "XAGUSDm",
                "instrument_class": "metals",
                "digits": 3,
                "point_size": 0.001,
                "tick_size": 0.001,
                "tick_value": 5.0,
                "contract_size": 5000.0,
                "min_lot": 0.1,
                "lot_step": 0.1,
                "max_lot": 50.0,
            },
            {
                "symbol": "XAGUSDm",
                "side": "buy",
                "entry_price": 28.0,
                "risk_mode": "money",
                "risk_value": 1.0,
                "stop_loss_mode": "price",
                "stop_loss_input": 27.99,
                "symbol_spec": None,
            },
            None,
            27.99,
            None,
        ),
    ],
)
def test_manual_trade_risk_calc_api_supports_representative_symbols(monkeypatch, symbol_spec, payload, expected_lot, expected_stop, expected_tp):
    monkeypatch.setattr(api_app, "fetch_symbol_spec", lambda symbol: _snapshot(symbol_spec))

    response = client.post("/api/execution/risk-calc", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert data["symbol_spec"]["symbol"] == payload["symbol"]
    assert data["derived"]["stop_loss_price"] == pytest.approx(expected_stop)
    if expected_tp is None:
        assert data["derived"]["take_profit_price"] is None
    else:
        assert data["derived"]["take_profit_price"] == pytest.approx(expected_tp)
    if expected_lot is None:
        assert data["derived"]["lot_size"] is None
    else:
        assert data["derived"]["lot_size"] == pytest.approx(expected_lot)
    assert data["preview_payload"]["order_origin"] == "manual_user"
    assert data["preview_payload"]["execution_origin"] == "operator_ui"
    assert data["preview_payload"]["is_manual"] is True
    assert data["preview_payload"]["exclude_from_strategy_eval"] is True
    assert data["preview_payload"]["comment_tag"] == "clio-manual-user"
    assert isinstance(data["preview_payload"]["magic_number"], int)


def test_manual_trade_risk_calc_api_uses_live_state_equity_when_missing(monkeypatch):
    symbol_spec = {
        "symbol": "XAUUSDm",
        "symbol_canonical": "XAUUSDm",
        "execution_symbol": "XAUUSDm",
        "instrument_class": "metals",
        "digits": 2,
        "point_size": 0.01,
        "tick_size": 0.01,
        "tick_value": 1.0,
        "contract_size": 100.0,
        "min_lot": 0.01,
        "lot_step": 0.01,
        "max_lot": 100.0,
    }
    monkeypatch.setattr(api_app, "fetch_symbol_spec", lambda symbol: _snapshot(symbol_spec))
    monkeypatch.setattr(api_app, "load_live_state_snapshot", lambda: {"equity_current": 10000.0})

    response = client.post(
        "/api/execution/risk-calc",
        json={
            "symbol": "XAUUSDm",
            "side": "buy",
            "entry_price": 2300.0,
            "risk_mode": "equity_pct",
            "risk_value": 1.0,
            "stop_loss_mode": "price",
            "stop_loss_input": 2295.0,
        },
    )

    assert response.status_code == 200
    assert response.json()["derived"]["risk_amount"] == pytest.approx(100.0)


def test_manual_trade_risk_calc_api_returns_operator_readable_validation_errors(monkeypatch):
    symbol_spec = {
        "symbol": "EURUSDm",
        "symbol_canonical": "EURUSDm",
        "execution_symbol": "EURUSDm",
        "instrument_class": "forex",
        "digits": 5,
        "point_size": 0.00001,
        "tick_size": 0.00001,
        "tick_value": 1.0,
        "contract_size": 100000.0,
        "min_lot": 0.01,
        "lot_step": 0.01,
        "max_lot": 100.0,
    }
    monkeypatch.setattr(api_app, "fetch_symbol_spec", lambda symbol: _snapshot(symbol_spec))

    response = client.post(
        "/api/execution/risk-calc",
        json={
            "symbol": "EURUSDm",
            "side": "buy",
            "entry_price": 1.1,
            "risk_mode": "money",
            "risk_value": 100.0,
            "stop_loss_mode": "price",
            "stop_loss_input": 1.11,
        },
    )

    assert response.status_code == 422
    data = response.json()["detail"]
    assert data["code"] == "stop_loss_must_be_below_entry_for_buy"
    assert data["field"] == "stop_loss_input"
    assert "stop loss harus berada di bawah entry" in data["message"].lower()


def test_manual_trade_risk_calc_api_reports_missing_symbol_metadata(monkeypatch):
    monkeypatch.setattr(api_app, "fetch_symbol_spec", lambda symbol: (_ for _ in ()).throw(RuntimeError("missing")))

    response = client.post(
        "/api/execution/risk-calc",
        json={
            "symbol": "UNKNOWN",
            "side": "buy",
            "entry_price": 1.0,
            "risk_mode": "money",
            "risk_value": 10.0,
            "stop_loss_mode": "pips",
            "stop_loss_input": 10.0,
        },
    )

    assert response.status_code == 422
    data = response.json()["detail"]
    assert data["code"] == "symbol_metadata_unavailable"
    assert data["field"] == "symbol"
    assert data["meta"]["symbol"] == "UNKNOWN"


def test_manual_trade_preview_intent_api_records_audit_event(tmp_path, monkeypatch):
    symbol_spec = {
        "symbol": "XAUUSDm",
        "symbol_canonical": "XAUUSDm",
        "execution_symbol": "XAUUSDm",
        "instrument_class": "metals",
        "digits": 2,
        "point_size": 0.01,
        "tick_size": 0.01,
        "tick_value": 1.0,
        "contract_size": 100.0,
        "min_lot": 0.01,
        "lot_step": 0.01,
        "max_lot": 100.0,
    }
    pool_audit_path = tmp_path / "pool_audit_trail.json"
    pool_audit_path.write_text("[]", encoding="utf-8")

    monkeypatch.setattr(api_app, "fetch_symbol_spec", lambda symbol: _snapshot(symbol_spec))
    monkeypatch.setattr(api_app, "load_live_state_snapshot", lambda: {"equity_current": 10000.0})
    monkeypatch.setattr(api_app, "validate_manual_trade_preview", lambda preview_payload: {"ok": True, "retcode": 0, "message": "validated", "request": {"magic": preview_payload.get("magic_number")}})
    monkeypatch.setattr(importlib.import_module("autonomous_trading_ai.execution.audit_utils"), "POOL_AUDIT_TRAIL_PATH", pool_audit_path)
    monkeypatch.setattr(adapters, "POOL_AUDIT_TRAIL_PATH", pool_audit_path)
    monkeypatch.setattr(adapters, "load_recent_trade_log", lambda limit=100: [])

    response = client.post(
        "/api/execution/manual-ticket/preview-intent",
        json={
            "symbol": "XAUUSDm",
            "side": "buy",
            "entry_price": 2300.0,
            "risk_mode": "equity_pct",
            "risk_value": 1.0,
            "stop_loss_mode": "price",
            "stop_loss_input": 2295.0,
            "take_profit_mode": "price",
            "take_profit_input": 2310.0,
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["broker_validation"]["ok"] is True
    assert data["broker_validation"]["retcode"] == 0
    assert data["audit_event"]["event"] == "manual_ticket_preview_intent"
    assert data["audit_event"]["audit_stage"] == "preview_intent"
    assert data["audit_event"]["order_origin"] == "manual_user"
    assert data["audit_event"]["execution_origin"] == "operator_ui"
    assert data["audit_event"]["is_manual"] is True
    assert data["audit_event"]["exclude_from_strategy_eval"] is True
    assert data["audit_event"]["preview_fingerprint"]

    timeline = adapters.load_audit_timeline(limit=10)
    preview_event = next(event for event in timeline["events"] if event.get("event") == "manual_ticket_preview_intent")
    assert preview_event["event_origin"] == "manual_user"
    assert preview_event["exclude_from_strategy_eval"] is True




def test_manual_trade_preview_intent_api_surfaces_broker_validation_failure(monkeypatch):
    symbol_spec = {
        "symbol": "XAUUSDm",
        "symbol_canonical": "XAUUSDm",
        "execution_symbol": "XAUUSDm",
        "instrument_class": "metals",
        "digits": 2,
        "point_size": 0.01,
        "tick_size": 0.01,
        "tick_value": 1.0,
        "contract_size": 100.0,
        "min_lot": 0.01,
        "lot_step": 0.01,
        "max_lot": 100.0,
    }
    monkeypatch.setattr(api_app, "fetch_symbol_spec", lambda symbol: _snapshot(symbol_spec))
    monkeypatch.setattr(api_app, "validate_manual_trade_preview", lambda preview_payload: {"ok": False, "retcode": 10016, "message": "Invalid stops", "request": {"magic": preview_payload.get("magic_number")}, "last_error": None})

    response = client.post(
        "/api/execution/manual-ticket/preview-intent",
        json={
            "symbol": "XAUUSDm",
            "side": "buy",
            "entry_price": 2300.0,
            "risk_mode": "money",
            "risk_value": 100.0,
            "stop_loss_mode": "price",
            "stop_loss_input": 2299.99,
        },
    )

    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail["code"] == "broker_validation_failed"
    assert detail["meta"]["retcode"] == 10016
    assert detail["meta"]["message"] == "Invalid stops"


def test_manual_trade_submit_api_records_pre_and_post_audit_for_market_order(tmp_path, monkeypatch):
    symbol_spec = {
        "symbol": "XAUUSDm",
        "symbol_canonical": "XAUUSDm",
        "execution_symbol": "XAUUSDm",
        "instrument_class": "metals",
        "digits": 2,
        "point_size": 0.01,
        "tick_size": 0.01,
        "tick_value": 1.0,
        "contract_size": 100.0,
        "min_lot": 0.01,
        "lot_step": 0.01,
        "max_lot": 100.0,
    }
    pool_audit_path = tmp_path / "pool_audit_trail.json"
    pool_audit_path.write_text("[]", encoding="utf-8")

    monkeypatch.setattr(api_app, "fetch_symbol_spec", lambda symbol: _snapshot(symbol_spec))
    monkeypatch.setattr(api_app, "validate_manual_trade_preview", lambda preview_payload: {"ok": True, "retcode": 0, "message": "validated", "request": {"magic": preview_payload.get("magic_number")}})
    monkeypatch.setattr(api_app, "submit_manual_trade", lambda preview_payload: {
        "ok": True,
        "submit_status": "submitted",
        "retcode": 10009,
        "message": "done",
        "request": {"symbol": preview_payload.get("execution_symbol"), "comment": preview_payload.get("comment_tag")},
        "raw_result": {"retcode": 10009, "comment": "done", "order": 81234},
        "order_ticket": 81234,
        "deal_ticket": 81235,
        "position_id": 81234,
    })
    monkeypatch.setattr(importlib.import_module("autonomous_trading_ai.execution.audit_utils"), "POOL_AUDIT_TRAIL_PATH", pool_audit_path)
    monkeypatch.setattr(api_app, "POOL_AUDIT_TRAIL_PATH", pool_audit_path)
    monkeypatch.setattr(adapters, "POOL_AUDIT_TRAIL_PATH", pool_audit_path)
    monkeypatch.setattr(adapters, "load_recent_trade_log", lambda limit=100: [])

    response = client.post(
        "/api/execution/manual-ticket/submit",
        json={
            "symbol": "XAUUSDm",
            "side": "buy",
            "entry_price": 2300.0,
            "risk_mode": "money",
            "risk_value": 100.0,
            "stop_loss_mode": "price",
            "stop_loss_input": 2295.0,
            "take_profit_mode": "price",
            "take_profit_input": 2310.0,
            "order_type": "market",
            "confirm_submit": True,
            "client_submission_id": "manual-submit-001",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["submit_status"] == "submitted"
    assert data["duplicate_submission"] is False
    assert data["broker_response"]["order_ticket"] == 81234
    assert data["audit_event_before"]["event"] == "manual_ticket_submit_intent"
    assert data["audit_event_after"]["event"] == "manual_ticket_execution_result"
    assert data["audit_event_after"]["client_submission_id"] == "manual-submit-001"
    assert data["audit_event_after"]["order_origin"] == "manual_user"
    assert data["audit_event_after"]["order_ticket"] == 81234
    assert data["audit_event_after"]["deal_ticket"] == 81235
    assert data["audit_event_after"]["position_id"] == 81234

    timeline = adapters.load_audit_timeline(limit=10)
    submit_events = [event for event in timeline["events"] if event.get("event") in {"manual_ticket_submit_intent", "manual_ticket_execution_result"}]
    assert len(submit_events) == 2
    assert all(event["event_origin"] == "manual_user" for event in submit_events)


def test_manual_trade_submit_api_is_retry_safe_for_duplicate_submission_id(tmp_path, monkeypatch):
    symbol_spec = {
        "symbol": "XAUUSDm",
        "symbol_canonical": "XAUUSDm",
        "execution_symbol": "XAUUSDm",
        "instrument_class": "metals",
        "digits": 2,
        "point_size": 0.01,
        "tick_size": 0.01,
        "tick_value": 1.0,
        "contract_size": 100.0,
        "min_lot": 0.01,
        "lot_step": 0.01,
        "max_lot": 100.0,
    }
    pool_audit_path = tmp_path / "pool_audit_trail.json"
    pool_audit_path.write_text("[]", encoding="utf-8")
    submit_calls = []

    monkeypatch.setattr(api_app, "fetch_symbol_spec", lambda symbol: _snapshot(symbol_spec))
    monkeypatch.setattr(api_app, "validate_manual_trade_preview", lambda preview_payload: {"ok": True, "retcode": 0, "message": "validated", "request": {"magic": preview_payload.get("magic_number")}})
    monkeypatch.setattr(api_app, "submit_manual_trade", lambda preview_payload: submit_calls.append(preview_payload) or {
        "ok": True,
        "submit_status": "submitted",
        "retcode": 10008,
        "message": "placed",
        "request": {"symbol": preview_payload.get("execution_symbol"), "comment": preview_payload.get("comment_tag")},
        "raw_result": {"retcode": 10008, "comment": "placed", "order": 91234},
        "order_ticket": 91234,
        "deal_ticket": None,
        "position_id": 91234,
    })
    monkeypatch.setattr(importlib.import_module("autonomous_trading_ai.execution.audit_utils"), "POOL_AUDIT_TRAIL_PATH", pool_audit_path)
    monkeypatch.setattr(api_app, "POOL_AUDIT_TRAIL_PATH", pool_audit_path)
    monkeypatch.setattr(adapters, "POOL_AUDIT_TRAIL_PATH", pool_audit_path)
    monkeypatch.setattr(adapters, "load_recent_trade_log", lambda limit=100: [])

    payload = {
        "symbol": "XAUUSDm",
        "side": "buy",
        "entry_price": 2298.0,
        "risk_mode": "money",
        "risk_value": 100.0,
        "stop_loss_mode": "price",
        "stop_loss_input": 2295.0,
        "take_profit_mode": "price",
        "take_profit_input": 2305.0,
        "order_type": "limit",
        "confirm_submit": True,
        "client_submission_id": "manual-submit-dup-001",
    }

    first = client.post("/api/execution/manual-ticket/submit", json=payload)
    second = client.post("/api/execution/manual-ticket/submit", json=payload)

    assert first.status_code == 200
    assert second.status_code == 200
    assert len(submit_calls) == 1
    assert first.json()["duplicate_submission"] is False
    assert second.json()["duplicate_submission"] is True
    assert second.json()["broker_response"]["order_ticket"] == 91234


def test_manual_trade_submit_api_requires_explicit_confirmation(monkeypatch):
    symbol_spec = {
        "symbol": "EURUSDm",
        "symbol_canonical": "EURUSDm",
        "execution_symbol": "EURUSDm",
        "instrument_class": "forex",
        "digits": 5,
        "point_size": 0.00001,
        "tick_size": 0.00001,
        "tick_value": 1.0,
        "contract_size": 100000.0,
        "min_lot": 0.01,
        "lot_step": 0.01,
        "max_lot": 100.0,
    }
    monkeypatch.setattr(api_app, "fetch_symbol_spec", lambda symbol: _snapshot(symbol_spec))

    response = client.post(
        "/api/execution/manual-ticket/submit",
        json={
            "symbol": "EURUSDm",
            "side": "buy",
            "entry_price": 1.1,
            "risk_mode": "money",
            "risk_value": 100.0,
            "stop_loss_mode": "price",
            "stop_loss_input": 1.095,
            "confirm_submit": False,
            "client_submission_id": "manual-submit-no-confirm",
        },
    )

    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail["code"] == "manual_submit_confirmation_required"
    assert detail["field"] == "confirm_submit"


def _snapshot(spec: dict):
    class Snapshot:
        def __init__(self, payload: dict):
            self.spec = api_app.NormalizedSymbolSpec(**payload)
            self.warnings = ()

    return Snapshot(spec)
