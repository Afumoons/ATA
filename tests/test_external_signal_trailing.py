import json
from pathlib import Path
from types import SimpleNamespace

from autonomous_trading_ai.execution.external_signal_trailing import (
    ExternalTrailingState,
    register_external_trailing_state,
    update_external_signal_trailing_stops,
)


def _mt5_stub(*, bid: float, ask: float, positions: list, sent: list):
    return SimpleNamespace(
        POSITION_TYPE_BUY=0,
        POSITION_TYPE_SELL=1,
        TRADE_ACTION_SLTP=6,
        TRADE_RETCODE_DONE=10009,
        positions_get=lambda: positions,
        symbol_info_tick=lambda symbol: SimpleNamespace(bid=bid, ask=ask),
        order_send=lambda request: sent.append(request) or SimpleNamespace(retcode=10009, _asdict=lambda: {"retcode": 10009}),
        last_error=lambda: (0, "ok"),
    )


def test_register_external_trailing_state_persists_ticket_config(tmp_path: Path) -> None:
    path = tmp_path / "trailing.json"

    register_external_trailing_state(
        ticket=123,
        signal_id="sig-1",
        source="telegram:japsku",
        symbol="XAUUSD",
        direction="long",
        entry_price=4500.0,
        initial_sl=4495.0,
        trailing_stop_pips=500.0,
        pip_size=0.01,
        path=path,
    )

    data = json.loads(path.read_text(encoding="utf-8"))
    rec = data["positions"]["123"]
    assert rec["signal_id"] == "sig-1"
    assert rec["symbol"] == "XAUUSD"
    assert rec["direction"] == "long"
    assert rec["entry_price"] == 4500.0
    assert rec["current_sl"] == 4495.0
    assert rec["highest_price"] == 4500.0
    assert rec["lowest_price"] == 4500.0
    assert rec["trailing_stop_pips"] == 500.0


def test_update_trailing_stop_moves_buy_sl_up_only_when_price_improves(tmp_path: Path, monkeypatch) -> None:
    path = tmp_path / "trailing.json"
    audit = tmp_path / "audit.jsonl"
    register_external_trailing_state(
        ticket=123,
        signal_id="sig-1",
        source="telegram:japsku",
        symbol="XAUUSD",
        direction="long",
        entry_price=4500.0,
        initial_sl=4495.0,
        trailing_stop_pips=500.0,
        pip_size=0.01,
        path=path,
    )
    pos = SimpleNamespace(ticket=123, symbol="XAUUSD", type=0, sl=4495.0, tp=0.0)
    sent = []
    monkeypatch.setattr(
        "autonomous_trading_ai.execution.external_signal_trailing.mt5",
        _mt5_stub(bid=4510.0, ask=4510.3, positions=[pos], sent=sent),
    )

    summary = update_external_signal_trailing_stops(path=path, audit_path=audit)

    assert summary["updated"] == 1
    assert sent == [
        {
            "action": 6,
            "position": 123,
            "symbol": "XAUUSD",
            "sl": 4505.0,
            "tp": 0.0,
        }
    ]
    data = json.loads(path.read_text(encoding="utf-8"))
    rec = data["positions"]["123"]
    assert rec["current_sl"] == 4505.0
    assert rec["highest_price"] == 4510.0
    row = json.loads(audit.read_text(encoding="utf-8").strip())
    assert row["event"] == "external_trailing_sl_update"
    assert row["old_sl"] == 4495.0
    assert row["new_sl"] == 4505.0


def test_update_trailing_stop_moves_sell_sl_down_only_when_price_improves(tmp_path: Path, monkeypatch) -> None:
    path = tmp_path / "trailing.json"
    audit = tmp_path / "audit.jsonl"
    register_external_trailing_state(
        ticket=456,
        signal_id="sig-2",
        source="telegram:japsku",
        symbol="XAUUSD",
        direction="short",
        entry_price=4500.0,
        initial_sl=4505.0,
        trailing_stop_pips=500.0,
        pip_size=0.01,
        path=path,
    )
    pos = SimpleNamespace(ticket=456, symbol="XAUUSD", type=1, sl=4505.0, tp=0.0)
    sent = []
    monkeypatch.setattr(
        "autonomous_trading_ai.execution.external_signal_trailing.mt5",
        _mt5_stub(bid=4489.7, ask=4490.0, positions=[pos], sent=sent),
    )

    summary = update_external_signal_trailing_stops(path=path, audit_path=audit)

    assert summary["updated"] == 1
    assert sent[0]["sl"] == 4495.0
    data = json.loads(path.read_text(encoding="utf-8"))
    rec = data["positions"]["456"]
    assert rec["current_sl"] == 4495.0
    assert rec["lowest_price"] == 4490.0


def test_update_trailing_stop_removes_closed_positions(tmp_path: Path, monkeypatch) -> None:
    path = tmp_path / "trailing.json"
    audit = tmp_path / "audit.jsonl"
    path.write_text(
        json.dumps(
            {
                "positions": {
                    "123": ExternalTrailingState(
                        ticket="123",
                        signal_id="sig-1",
                        source="telegram:japsku",
                        symbol="XAUUSD",
                        direction="long",
                        entry_price=4500.0,
                        current_sl=4495.0,
                        trailing_stop_pips=500.0,
                        pip_size=0.01,
                        highest_price=4500.0,
                        lowest_price=4500.0,
                    ).to_dict()
                }
            }
        ),
        encoding="utf-8",
    )
    sent = []
    monkeypatch.setattr(
        "autonomous_trading_ai.execution.external_signal_trailing.mt5",
        _mt5_stub(bid=4510.0, ask=4510.3, positions=[], sent=sent),
    )

    summary = update_external_signal_trailing_stops(path=path, audit_path=audit)

    assert summary["removed_closed"] == 1
    assert sent == []
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["positions"] == {}
