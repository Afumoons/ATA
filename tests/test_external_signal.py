from autonomous_trading_ai.execution.external_signal import (
    ExternalSignalConfig,
    build_trade_plan,
    parse_external_signal,
)


def plan(text: str):
    cfg = ExternalSignalConfig()
    parsed = parse_external_signal(text, message_id="1", config=cfg)
    return build_trade_plan(parsed, config=cfg)


def test_buy_without_sl_defaults_500_pips_from_entry() -> None:
    p = plan("BUY XAUUSD 4500")

    assert p.decision == "planned"
    assert p.direction == "long"
    assert p.symbol == "XAUUSD"
    assert p.entry_reference == 4500.0
    assert p.stop_loss_price == 4495.0
    assert p.stop_loss_mode == "default_from_entry"
    assert p.stop_loss_pips_for_sizing == 500.0
    assert p.exit_mode == "trailing_stop"
    assert p.trailing_stop_pips == 500.0


def test_sell_without_sl_defaults_500_pips_from_entry() -> None:
    p = plan("SELL GOLD 4500")

    assert p.decision == "planned"
    assert p.direction == "short"
    assert p.stop_loss_price == 4505.0
    assert p.exit_mode == "trailing_stop"


def test_explicit_sl_and_tp1_full_close() -> None:
    p = plan("Gold buy entry 4500 sl 4492 tp1 4510 tp2 4525")

    assert p.decision == "planned"
    assert p.direction == "long"
    assert p.stop_loss_price == 4492.0
    assert p.stop_loss_mode == "explicit"
    assert p.take_profit_price == 4510.0
    assert p.exit_mode == "tp1_full_close"
    assert p.trailing_stop_pips is None
    assert p.stop_loss_pips_for_sizing == 800.0


def test_stoplose_takeprof_channel_format_is_recognized() -> None:
    p = plan(
        "🚀 XAUUSDr | SELL NOW 4532.55\n"
        "STOPLOSE : 4538.55 (60.0 Pips)\n"
        "TAKEPROF : 4526.55 (60.0 Pips)"
    )

    assert p.decision == "planned"
    assert p.direction == "short"
    assert p.entry_reference == 4532.55
    assert p.stop_loss_price == 4538.55
    assert p.stop_loss_mode == "explicit"
    assert p.take_profit_price == 4526.55
    assert p.exit_mode == "tp1_full_close"
    assert p.trailing_stop_pips is None
    assert "symbol_not_explicit_using_config_canonical_xauusd" not in p.notes


def test_reject_wrong_side_stop() -> None:
    p = plan("BUY XAUUSD 4500 SL 4505 TP 4510")

    assert p.decision == "rejected"
    assert "wrong side" in p.reason


def test_ignore_no_direction() -> None:
    p = plan("XAUUSD maybe setup later 4500 sl 4495")

    assert p.decision == "ignored"
    assert p.direction is None
