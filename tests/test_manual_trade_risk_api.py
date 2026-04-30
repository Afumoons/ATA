from __future__ import annotations

import importlib

import pytest
from fastapi.testclient import TestClient

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


def _snapshot(spec: dict):
    class Snapshot:
        def __init__(self, payload: dict):
            self.spec = api_app.NormalizedSymbolSpec(**payload)
            self.warnings = ()

    return Snapshot(spec)
