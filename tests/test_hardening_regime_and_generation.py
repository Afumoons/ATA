from autonomous_trading_ai.backtests.evaluation import evaluate_strategy
from autonomous_trading_ai.backtests.explain import _derive_routing_confidence
from autonomous_trading_ai.strategies.generator import random_strategy


def test_routing_confidence_penalizes_leakage():
    strong = _derive_routing_confidence(best_ret=8.0, worst_ret=-1.0, total_trades=120, num_allowed=3, num_blocked=1)
    leaky = _derive_routing_confidence(best_ret=8.0, worst_ret=-9.0, total_trades=120, num_allowed=3, num_blocked=1)
    assert strong > leaky
    assert leaky >= 0.0


def test_evaluation_penalizes_blocked_contexts_and_low_routing_confidence():
    stats = {
        'num_trades': 120,
        'sharpe_ratio': 0.6,
        'profit_factor': 1.3,
        'max_drawdown_pct': -10.0,
        'strategy_explain': {
            'regime_pnl': {
                'trending_up': {'return_pct': 3.0},
                'trending_down': {'return_pct': -8.0},
                'ranging': {'return_pct': -7.0},
            },
            'stability': {'sharpe_std': 0.05},
            'news_behavior': {'trades_around_high_impact': {'num_trades': 0, 'return_pct': 0.0}, 'avoidance_rate': 0.0},
            'meta': {
                'routing_confidence': 0.35,
                'blocked_regimes': ['trending_down', 'ranging'],
                'blocked_sessions': ['new_york'],
            },
        },
    }
    result = evaluate_strategy(stats)
    assert result['score'] < 1.0


def test_core_m15_generation_produces_broader_families():
    families = set()
    for _ in range(40):
        strat = random_strategy('BTCUSDm', 'M15')
        families.add(strat.params.get('family'))
    assert len(families) >= 4
