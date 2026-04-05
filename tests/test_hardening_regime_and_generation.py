import pandas as pd

from autonomous_trading_ai.backtests.engine import run_backtest
from autonomous_trading_ai.backtests.evaluation import evaluate_strategy
from autonomous_trading_ai.backtests.explain import _derive_routing_confidence
from autonomous_trading_ai.config import canonical_symbol
from autonomous_trading_ai.strategies.base import StrategyDefinition
from autonomous_trading_ai.strategies.generator import FAMILY_LIBRARY, random_strategy
from autonomous_trading_ai.strategies.pool import StrategyPool


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


def test_canonical_symbol_maps_btc_execution_aliases_to_research_symbol():
    assert canonical_symbol('BTCUSDm') == 'BTCUSDm'
    assert canonical_symbol('BTCUSD') == 'BTCUSDm'
    assert canonical_symbol('BTCUSDT') == 'BTCUSDm'
    assert canonical_symbol('BTCUSDc') == 'BTCUSDm'


def test_core_m15_generation_produces_broader_families():
    families = set()
    for _ in range(40):
        strat = random_strategy('BTCUSDm', 'M15')
        families.add(strat.params.get('family'))
    assert len(families) >= 4


def test_family_aware_pool_prune_preserves_diversity_floor():
    pool = StrategyPool()
    families = ['ma_trend', 'rsi_range', 'pullback_trend', 'vol_breakout', 'compression_breakout', 'session_breakout']

    for family in families:
        for idx in range(5):
            strat = random_strategy('BTCUSDm', 'M15', family=family)
            stats = {
                'family': family,
                'playbook_type': family,
                'strategy': {
                    'family': family,
                    'playbook_type': family,
                    'long_entry_rule': strat.long_entry_rule,
                    'short_entry_rule': strat.short_entry_rule,
                    'exit_rule': strat.exit_rule,
                    'sl_atr_mult': strat.sl_atr_mult,
                    'tp_atr_mult': strat.tp_atr_mult,
                },
            }
            pool.upsert_strategy(strat, stats=stats, score=float(100 - idx), status='candidate')

    pruned = pool.prune(max_inactive=18, min_family_keep=2)
    assert pruned > 0
    remaining_families = {}
    for rec in pool.strategies.values():
        fam = (rec.stats.get('strategy', {}) or {}).get('family', 'unknown')
        remaining_families[fam] = remaining_families.get(fam, 0) + 1

    for family in families:
        assert remaining_families.get(family, 0) >= 2


def test_d4a_non_xau_generation_remaps_xau_specialist_families():
    strat = random_strategy('XAGUSDc', 'M15', family='xau_impulse_pullback')
    assert strat.params.get('family') == 'pullback_trend'
    assert strat.params.get('playbook_type') == 'pullback_trend'

    strat2 = random_strategy('XAGUSDc', 'M15', family='xau_session_continuation')
    assert strat2.params.get('family') == 'session_breakout'
    assert strat2.params.get('playbook_type') == 'session_breakout'


def test_d4b_rebuild_strategy_preserves_non_xau_family_normalization():
    from autonomous_trading_ai.strategies.generator import rebuild_strategy_from_params

    rebuilt = rebuild_strategy_from_params(
        'XAGUSDm',
        'M15',
        params={
            'family': 'xau_impulse_pullback',
            'playbook_type': 'xau_impulse_pullback',
            'preferred_symbols': ['XAGUSDm'],
        },
        name_prefix='xau_impulse_pullback',
    )
    assert rebuilt.params.get('family') == 'pullback_trend'
    assert rebuilt.params.get('playbook_type') == 'pullback_trend'


def test_d4b_xag_m15_family_priors_are_market_specific_and_conservative():
    breakout = random_strategy('XAGUSDm', 'M15', family='session_breakout')
    assert 0.40 <= float(breakout.params.get('vol_min', 0.0)) <= 0.80
    assert 0.04 <= float(breakout.params.get('trend_min', 0.0)) <= 0.14

    compression = random_strategy('XAGUSDm', 'M15', family='compression_breakout')
    assert 0.28 <= float(compression.params.get('vol_max', 0.0)) <= 0.65
    assert 0.03 <= float(compression.params.get('trend_min', 0.0)) <= 0.12


def test_d4a_family_exit_pools_are_constrained_by_archetype():
    assert FAMILY_LIBRARY['ma_trend']['exit_templates'] != FAMILY_LIBRARY['rsi_range']['exit_templates']
    assert any('close < ma_short' in tpl for tpl in FAMILY_LIBRARY['pullback_trend']['exit_templates'])
    assert any('close < ma_short' in tpl or 'close > ma_short' in tpl for tpl in FAMILY_LIBRARY['vol_breakout']['exit_templates'])


def test_backtest_tracks_same_bar_ambiguity_when_sl_and_tp_hit_in_same_candle():
    strat = StrategyDefinition(
        name='same_bar_probe',
        symbol='XAUUSDm',
        timeframe='M15',
        long_entry_rule='close > 0',
        short_entry_rule=None,
        exit_rule='False',
        stop_loss_pips=10,
        take_profit_pips=10,
        sl_atr_mult=None,
        tp_atr_mult=None,
        params={},
    )

    df = pd.DataFrame([
        {'time': '2026-01-01 00:00:00', 'open': 100.0, 'high': 100.0, 'low': 100.0, 'close': 100.0},
        {'time': '2026-01-01 00:15:00', 'open': 100.0, 'high': 100.3, 'low': 99.7, 'close': 100.0},
    ])

    result = run_backtest(
        df,
        strat,
        initial_equity=10000.0,
        risk_per_trade_pct=1.0,
        pip_size=0.01,
        max_positions_total=1,
        max_positions_per_strategy=1,
        spread=0.0,
        commission_per_lot=0.0,
        slippage_pips=0.0,
    )

    assert result.stats['same_bar_ambiguity_count'] == 1.0
    assert result.stats['same_bar_ambiguity_stop_loss_count'] == 1.0
    assert result.stats['same_bar_ambiguity_rate'] > 0.0
