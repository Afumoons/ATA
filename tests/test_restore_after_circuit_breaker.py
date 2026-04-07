from autonomous_trading_ai.scripts.restore_after_circuit_breaker import _eligible_for_exploratory_restore
from autonomous_trading_ai.strategies.pool import StrategyRecord


def test_restore_after_circuit_breaker_requires_marker_and_quality():
    rec = StrategyRecord(
        name="s1",
        symbol="XAUUSDm",
        timeframe="M15",
        status="disabled",
        score=1.0,
        stats={
            "circuit_breaker_previous_status": "active",
            "wf_overall_sharpe": 0.35,
            "max_drawdown_pct": 12.0,
            "num_trades": 55,
            "mc_final_pnl_p5": 10.0,
        },
    )
    assert _eligible_for_exploratory_restore(rec) is True


def test_restore_after_circuit_breaker_rejects_weak_or_unmarked_entries():
    unmarked = StrategyRecord(
        name="s2",
        symbol="BTCUSDm",
        timeframe="M15",
        status="disabled",
        score=1.0,
        stats={
            "wf_overall_sharpe": 0.40,
            "max_drawdown_pct": 10.0,
            "num_trades": 80,
            "mc_final_pnl_p5": 12.0,
        },
    )
    weak = StrategyRecord(
        name="s3",
        symbol="BTCUSDm",
        timeframe="M15",
        status="disabled",
        score=1.0,
        stats={
            "circuit_breaker_previous_status": "exploratory",
            "wf_overall_sharpe": 0.05,
            "max_drawdown_pct": 40.0,
            "num_trades": 8,
            "mc_final_pnl_p5": -50.0,
        },
    )
    assert _eligible_for_exploratory_restore(unmarked) is False
    assert _eligible_for_exploratory_restore(weak) is False
