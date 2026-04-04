from autonomous_trading_ai.scheduler.main import _select_diversified_execution_pool
from autonomous_trading_ai.strategies.pool import StrategyRecord


def _rec(name, family, best_regime, score):
    return StrategyRecord(
        name=name,
        symbol='BTCUSDm',
        timeframe='M15',
        status='active',
        score=score,
        stats={
            'wf_overall_sharpe': score,
            'strategy': {
                'family': family,
                'playbook_type': family,
                'params': {'family': family, 'playbook_type': family},
            },
            'strategy_explain': {
                'meta': {
                    'best_regime': best_regime,
                    'specialist_score': 0.9,
                },
                'regime_pnl': {
                    best_regime: {'return_pct': 8.0},
                },
            },
        },
    )


def test_execution_pool_selection_applies_light_diversification_before_final_fill():
    records = []
    for idx in range(7):
        records.append(_rec(f'dom_{idx}', 'ma_trend', 'ranging', 100 - idx))
    records.append(_rec('alt_1', 'pullback_trend', 'trending_up', 80))
    records.append(_rec('alt_2', 'session_breakout', 'high_vol', 79))
    records.append(_rec('alt_3', 'compression_breakout', 'trending_down', 78))

    selected = _select_diversified_execution_pool(records, current_regime='ranging', current_session='london', limit=8)
    regimes = [((r.stats.get('strategy_explain', {}) or {}).get('meta', {}) or {}).get('best_regime') for r in selected]

    assert len(selected) == 8
    assert regimes.count('ranging') <= 5
    assert 'trending_up' in regimes
    assert 'high_vol' in regimes
