from autonomous_trading_ai.backtests.engine import Trade
from autonomous_trading_ai.backtests.monte_carlo import monte_carlo_pnl


def _trade(pnl: float, size: float = 1.0) -> Trade:
    return Trade(
        entry_time=None,
        exit_time=None,
        direction='long',
        entry_price=0.0,
        exit_price=0.0,
        stop_loss=0.0,
        take_profit=0.0,
        size=size,
        pnl=pnl,
        regime=None,
    )


def test_monte_carlo_shuffle_returns_backward_compatible_keys():
    trades = [_trade(50.0), _trade(-20.0), _trade(30.0), _trade(-10.0)]
    stats = monte_carlo_pnl(trades, n_runs=200, method='shuffle', seed=42)

    for key in [
        'mc_final_pnl_mean',
        'mc_final_pnl_p5',
        'mc_final_pnl_p95',
        'mc_max_dd_mean',
        'mc_max_dd_p5',
        'mc_max_dd_p95',
        'mc_loss_prob',
        'mc_cvar_p5',
        'mc_method',
    ]:
        assert key in stats

    assert stats['mc_method'] == 'shuffle'


def test_monte_carlo_block_method_changes_distribution_and_reports_block_metadata():
    trades = [
        _trade(100.0), _trade(90.0), _trade(-120.0), _trade(-110.0),
        _trade(80.0), _trade(70.0), _trade(-95.0), _trade(-85.0),
    ]

    shuffle_stats = monte_carlo_pnl(trades, n_runs=400, method='shuffle', seed=7)
    block_stats = monte_carlo_pnl(trades, n_runs=400, method='block', block_size=2, seed=7)

    assert block_stats['mc_method'] == 'block'
    assert block_stats['mc_block_size'] == 2.0
    assert block_stats['mc_max_dd_p95'] >= shuffle_stats['mc_max_dd_p95']
    assert block_stats['mc_final_pnl_p5'] <= shuffle_stats['mc_final_pnl_p5']


def test_monte_carlo_reports_dd_threshold_probabilities_and_cvar():
    trades = [_trade(-100.0), _trade(-80.0), _trade(40.0), _trade(30.0), _trade(-60.0)]
    stats = monte_carlo_pnl(trades, n_runs=300, method='shuffle', seed=123, initial_equity=1000.0)

    assert 0.0 <= stats['mc_loss_prob'] <= 1.0
    assert 0.0 <= stats['mc_dd_over_10pct_prob'] <= 1.0
    assert 0.0 <= stats['mc_dd_over_20pct_prob'] <= 1.0
    assert stats['mc_cvar_p5'] <= stats['mc_final_pnl_p5']
