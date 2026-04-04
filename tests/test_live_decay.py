from autonomous_trading_ai.execution.live_decay import (
    compute_live_decay_signal,
    evaluate_live_decay,
    apply_live_decay_actions,
)
from autonomous_trading_ai.execution.strategy_live_stats import StrategyLiveStats
from autonomous_trading_ai.strategies.pool import StrategyPool, StrategyRecord


def test_compute_live_decay_warning_on_negative_recent_avg_and_loss_streak():
    stats = StrategyLiveStats(
        name='s1',
        total_pnl=-12.0,
        num_trades=10,
        recent_pnls=[1, -1, -2, -1, -1, -1, -2, -3],
    )
    signal = compute_live_decay_signal('s1', 'active', stats)
    assert signal.signal_level == 'warning'
    assert signal.loss_streak >= 4


def test_compute_live_decay_degrade_on_stronger_recent_decay():
    stats = StrategyLiveStats(
        name='s2',
        total_pnl=-20.0,
        num_trades=14,
        recent_pnls=[1, -1, -1, -2, -2, -1, -1, -1, -3, -2],
    )
    signal = compute_live_decay_signal('s2', 'active', stats)
    assert signal.signal_level == 'degrade'


def test_apply_live_decay_actions_downgrades_active_to_exploratory():
    pool = StrategyPool(
        strategies={
            's2': StrategyRecord(name='s2', symbol='XAUUSDm', timeframe='M15', status='active', score=1.0, stats={})
        }
    )
    live_stats = {
        's2': StrategyLiveStats(
            name='s2',
            total_pnl=-20.0,
            num_trades=14,
            recent_pnls=[1, -1, -1, -2, -2, -1, -1, -1, -3, -2],
        )
    }
    actions = evaluate_live_decay(pool, live_stats)
    changed = apply_live_decay_actions(pool, actions)
    assert changed == 1
    assert pool.strategies['s2'].status == 'exploratory'
    assert pool.strategies['s2'].stats.get('live_decay', {}).get('signal_level') == 'degrade'


def test_apply_live_decay_actions_can_disable_exploratory():
    pool = StrategyPool(
        strategies={
            's3': StrategyRecord(name='s3', symbol='BTCUSDm', timeframe='M15', status='exploratory', score=1.0, stats={})
        }
    )
    live_stats = {
        's3': StrategyLiveStats(
            name='s3',
            total_pnl=-15.0,
            num_trades=12,
            recent_pnls=[-1, -1, -1, -1, -1, -1, -2, -1, -2, -2],
        )
    }
    actions = evaluate_live_decay(pool, live_stats)
    changed = apply_live_decay_actions(pool, actions)
    assert changed == 1
    assert pool.strategies['s3'].status == 'disabled'
