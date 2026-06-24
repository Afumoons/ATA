from pathlib import Path
from types import SimpleNamespace

import pytest

pytest.importorskip("MetaTrader5")

from autonomous_trading_ai.execution.external_signal import (
    ExternalSignalConfig,
    build_trade_plan,
    parse_external_signal,
)
from autonomous_trading_ai.execution.external_signal_executor import (
    SignalDuplicateStore,
    build_external_order_request,
    execute_external_trade_plan,
)


def _plan(text: str):
    cfg = ExternalSignalConfig()
    parsed = parse_external_signal(text, message_id="42", config=cfg)
    return build_trade_plan(parsed, config=cfg)


def test_shadow_execution_marks_duplicate(tmp_path: Path) -> None:
    plan = _plan("BUY XAUUSD 4500 SL 4495 TP 4510")
    store = SignalDuplicateStore(tmp_path / "seen.json")
    audit = tmp_path / "audit.jsonl"

    first = execute_external_trade_plan(plan, mode="shadow", duplicate_store=store, audit_path=audit)
    second = execute_external_trade_plan(plan, mode="shadow", duplicate_store=store, audit_path=audit)

    assert first.action == "shadow"
    assert second.action == "skip"
    assert second.reason == "duplicate_signal"
    assert audit.read_text(encoding="utf-8").count("\n") == 2


def test_auto_live_blocked_without_env(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("ATA_TELEGRAM_SIGNAL_LIVE", raising=False)
    plan = _plan("BUY XAUUSD 4500 SL 4495 TP 4510")
    decision = execute_external_trade_plan(
        plan,
        mode="auto_live",
        duplicate_store=SignalDuplicateStore(tmp_path / "seen.json"),
        audit_path=tmp_path / "audit.jsonl",
    )

    assert decision.action == "blocked"
    assert "ATA_TELEGRAM_SIGNAL_LIVE" in decision.reason


def test_build_external_order_request_keeps_absolute_sl_on_worse_fill(monkeypatch) -> None:
    plan = _plan("BUY XAUUSD 4500")

    monkeypatch.setattr(
        "autonomous_trading_ai.execution.external_signal_executor._resolve_execution_symbol",
        lambda symbol: "XAUUSDm",
    )
    monkeypatch.setattr(
        "autonomous_trading_ai.execution.external_signal_executor._clamp_volume",
        lambda volume, symbol: round(volume, 2),
    )
    monkeypatch.setattr(
        "autonomous_trading_ai.execution.external_signal_executor.validate_trade",
        lambda account, req, equity_peak: SimpleNamespace(allowed=True, reason="ok"),
    )
    monkeypatch.setattr(
        "autonomous_trading_ai.execution.external_signal_executor._account_state",
        lambda: SimpleNamespace(equity=1000.0, balance=1000.0, open_positions=0),
    )
    monkeypatch.setattr(
        "autonomous_trading_ai.execution.external_signal_executor.mt5.symbol_info_tick",
        lambda symbol: SimpleNamespace(ask=4507.0, bid=4506.5),
    )

    request = build_external_order_request(plan)

    assert request["symbol"] == "XAUUSDm"
    assert request["price"] == 4507.0
    assert request["sl"] == 4490.0
    assert request["tp"] == 0.0
    assert request["external_signal"]["sizing_stop_pips"] == 1700.0
    assert request["volume"] == 0.0
    assert request["comment"] == "TLGXAUUSDJAPSKU"



def test_build_external_order_request_uses_explicit_pip_sl_from_fill(monkeypatch) -> None:
    plan = _plan("GOLD SELL NOW SL 60 PIP")

    monkeypatch.setattr(
        "autonomous_trading_ai.execution.external_signal_executor._resolve_execution_symbol",
        lambda symbol: "XAUUSDm",
    )
    monkeypatch.setattr(
        "autonomous_trading_ai.execution.external_signal_executor._clamp_volume",
        lambda volume, symbol: round(volume, 2),
    )
    monkeypatch.setattr(
        "autonomous_trading_ai.execution.external_signal_executor.validate_trade",
        lambda account, req, equity_peak: SimpleNamespace(allowed=True, reason="ok"),
    )
    monkeypatch.setattr(
        "autonomous_trading_ai.execution.external_signal_executor._account_state",
        lambda: SimpleNamespace(equity=1000.0, balance=1000.0, open_positions=0),
    )
    monkeypatch.setattr(
        "autonomous_trading_ai.execution.external_signal_executor.mt5.symbol_info_tick",
        lambda symbol: SimpleNamespace(ask=4507.0, bid=4506.5),
    )

    request = build_external_order_request(plan)

    assert request["price"] == 4506.5
    assert request["sl"] == 4512.5
    assert request["external_signal"]["sizing_stop_pips"] == 600.0
