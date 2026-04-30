from __future__ import annotations

import pytest

from autonomous_trading_ai.execution.manual_trade_risk import (
    ManualTradeRiskError,
    ManualTradeRiskRequest,
    calculate_manual_trade_risk,
    pip_size_for_spec,
)
from autonomous_trading_ai.execution.symbol_metadata import NormalizedSymbolSpec


@pytest.fixture()
def forex_spec() -> NormalizedSymbolSpec:
    return NormalizedSymbolSpec(
        symbol="EURUSDm",
        symbol_canonical="EURUSDm",
        execution_symbol="EURUSDm",
        instrument_class="forex",
        digits=5,
        point_size=0.00001,
        tick_size=0.00001,
        tick_value=1.0,
        contract_size=100000.0,
        min_lot=0.01,
        lot_step=0.01,
        max_lot=100.0,
    )


def test_forex_risk_engine_supports_money_risk_and_pip_distances(forex_spec: NormalizedSymbolSpec):
    result = calculate_manual_trade_risk(
        ManualTradeRiskRequest(
            symbol_spec=forex_spec,
            side="buy",
            entry_price=1.10000,
            risk_mode="money",
            risk_value=100.0,
            stop_loss_mode="pips",
            stop_loss_input=20.0,
            take_profit_mode="pips",
            take_profit_input=40.0,
        )
    )

    assert result.pip_size == pytest.approx(0.0001)
    assert result.stop_loss_price == pytest.approx(1.098)
    assert result.take_profit_price == pytest.approx(1.104)
    assert result.raw_lot_size == pytest.approx(0.5)
    assert result.lot_size == pytest.approx(0.5)
    assert result.estimated_loss_at_stop == pytest.approx(100.0)
    assert result.estimated_profit_at_take_profit == pytest.approx(200.0)
    assert result.risk_reward_ratio == pytest.approx(2.0)
    assert result.notional_estimate == pytest.approx(55000.0)


def test_metals_risk_engine_supports_equity_pct_and_price_stop_with_margin():
    spec = NormalizedSymbolSpec(
        symbol="XAUUSDm",
        symbol_canonical="XAUUSDm",
        execution_symbol="XAUUSDm",
        instrument_class="metals",
        digits=2,
        point_size=0.01,
        tick_size=0.01,
        tick_value=1.0,
        contract_size=100.0,
        min_lot=0.01,
        lot_step=0.01,
        max_lot=100.0,
    )

    result = calculate_manual_trade_risk(
        ManualTradeRiskRequest(
            symbol_spec=spec,
            side="buy",
            entry_price=2300.00,
            risk_mode="equity_pct",
            risk_value=1.0,
            account_equity=10000.0,
            stop_loss_mode="price",
            stop_loss_input=2295.00,
            take_profit_mode="price",
            take_profit_input=2310.00,
            leverage=100.0,
        )
    )

    assert result.risk_amount == pytest.approx(100.0)
    assert result.raw_lot_size == pytest.approx(0.2)
    assert result.lot_size == pytest.approx(0.2)
    assert result.estimated_loss_at_stop == pytest.approx(100.0)
    assert result.estimated_profit_at_take_profit == pytest.approx(200.0)
    assert result.risk_reward_ratio == pytest.approx(2.0)
    assert result.notional_estimate == pytest.approx(46000.0)
    assert result.margin_estimate == pytest.approx(460.0)


def test_crypto_and_metals_pips_follow_broker_point_geometry():
    btc = NormalizedSymbolSpec(
        symbol="BTCUSDm",
        symbol_canonical="BTCUSDm",
        execution_symbol="BTCUSDm",
        instrument_class="crypto",
        digits=2,
        point_size=0.01,
        tick_size=0.01,
        tick_value=1.0,
        contract_size=1.0,
        min_lot=0.01,
        lot_step=0.01,
        max_lot=10.0,
    )
    xag = NormalizedSymbolSpec(
        symbol="XAGUSDm",
        symbol_canonical="XAGUSDm",
        execution_symbol="XAGUSDm",
        instrument_class="metals",
        digits=3,
        point_size=0.001,
        tick_size=0.001,
        tick_value=5.0,
        contract_size=5000.0,
        min_lot=0.1,
        lot_step=0.1,
        max_lot=50.0,
    )

    assert pip_size_for_spec(btc) == pytest.approx(0.01)
    assert pip_size_for_spec(xag) == pytest.approx(0.001)

    btc_result = calculate_manual_trade_risk(
        ManualTradeRiskRequest(
            symbol_spec=btc,
            side="sell",
            entry_price=60000.00,
            risk_mode="money",
            risk_value=25.0,
            stop_loss_mode="pips",
            stop_loss_input=100.0,
            take_profit_mode="pips",
            take_profit_input=300.0,
        )
    )
    assert btc_result.stop_loss_price == pytest.approx(60001.0)
    assert btc_result.take_profit_price == pytest.approx(59997.0)
    assert btc_result.lot_size == pytest.approx(0.25)


def test_risk_engine_warns_when_requested_risk_is_below_min_lot():
    spec = NormalizedSymbolSpec(
        symbol="XAGUSDm",
        symbol_canonical="XAGUSDm",
        execution_symbol="XAGUSDm",
        instrument_class="metals",
        digits=3,
        point_size=0.001,
        tick_size=0.001,
        tick_value=5.0,
        contract_size=5000.0,
        min_lot=0.1,
        lot_step=0.1,
        max_lot=50.0,
    )

    result = calculate_manual_trade_risk(
        ManualTradeRiskRequest(
            symbol_spec=spec,
            side="buy",
            entry_price=28.000,
            risk_mode="money",
            risk_value=1.0,
            stop_loss_mode="price",
            stop_loss_input=27.990,
        )
    )

    assert result.lot_size is None
    assert "risk_sizing_below_min_lot" in result.warnings


def test_risk_engine_rejects_missing_symbol_geometry(forex_spec: NormalizedSymbolSpec):
    bad_spec = NormalizedSymbolSpec(
        symbol=forex_spec.symbol,
        symbol_canonical=forex_spec.symbol_canonical,
        execution_symbol=forex_spec.execution_symbol,
        instrument_class=forex_spec.instrument_class,
        digits=forex_spec.digits,
        point_size=forex_spec.point_size,
        tick_size=0.0,
        tick_value=forex_spec.tick_value,
        contract_size=forex_spec.contract_size,
        min_lot=forex_spec.min_lot,
        lot_step=forex_spec.lot_step,
        max_lot=forex_spec.max_lot,
    )

    with pytest.raises(ManualTradeRiskError, match="symbol_spec_tick_size_must_be_positive"):
        calculate_manual_trade_risk(
            ManualTradeRiskRequest(
                symbol_spec=bad_spec,
                side="buy",
                entry_price=1.10000,
                risk_mode="money",
                risk_value=100.0,
                stop_loss_mode="pips",
                stop_loss_input=20.0,
            )
        )
