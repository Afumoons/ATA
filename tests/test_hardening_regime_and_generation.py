import pandas as pd

from autonomous_trading_ai.backtests.engine import run_backtest
from autonomous_trading_ai.backtests.evaluation import evaluate_strategy
from autonomous_trading_ai.backtests.explain import _derive_routing_confidence
from autonomous_trading_ai.config import canonical_symbol
from autonomous_trading_ai.scheduler.main import _challenger_research_min_trades, _passes_symbol_specific_mc_tail_relief
from autonomous_trading_ai.strategies.base import StrategyDefinition
from autonomous_trading_ai.strategies.generator import FAMILY_LIBRARY, XAG_M15_FAMILY_WEIGHTS, random_strategy, generated_family_counts
from autonomous_trading_ai.strategies.pool import StrategyPool, semantic_similarity, strategy_motif


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
    assert 0.0025 <= float(breakout.params.get('vol_min', 0.0)) <= 0.0065
    assert 0.02 <= float(breakout.params.get('trend_min', 0.0)) <= 0.10
    assert breakout.params.get('time_stop_bars') in {6, 8, 10, 12}

    compression = random_strategy('XAGUSDm', 'M15', family='compression_breakout')
    assert 0.003 <= float(compression.params.get('vol_max', 0.0)) <= 0.008
    assert 0.01 <= float(compression.params.get('trend_min', 0.0)) <= 0.08

    pullback = random_strategy('XAGUSDm', 'M15', family='pullback_trend')
    assert 0.12 <= float(pullback.params.get('trend_min', 0.0)) <= 0.22
    assert pullback.params.get('rsi_exit') >= 52


def test_btc_challenger_trade_floor_is_softened_not_hardened():
    assert _challenger_research_min_trades('BTCUSDm') == 30
    assert _challenger_research_min_trades('XAGUSDm') == 25
    assert _challenger_research_min_trades('XAUUSDm') == 60


def test_btc_mc_tail_relief_is_narrow_and_family_aware():
    assert _passes_symbol_specific_mc_tail_relief(
        symbol='BTCUSDm',
        family='mixed:ma_trend+rsi_range',
        num_trades=46,
        pf=1.19,
        sharpe=1.63,
        dd_abs=3.7,
        wf_sharpe=4.2,
        mc_p5=-423.0,
        mc_loss_prob=0.27,
        mc_dd_p95=733.0,
    ) is True
    assert _passes_symbol_specific_mc_tail_relief(
        symbol='XAUUSDm',
        family='mixed:ma_trend+rsi_range',
        num_trades=46,
        pf=1.19,
        sharpe=1.63,
        dd_abs=3.7,
        wf_sharpe=4.2,
        mc_p5=-423.0,
        mc_loss_prob=0.27,
        mc_dd_p95=733.0,
    ) is False
    assert _passes_symbol_specific_mc_tail_relief(
        symbol='BTCUSDm',
        family='ma_trend',
        num_trades=46,
        pf=1.19,
        sharpe=1.63,
        dd_abs=3.7,
        wf_sharpe=4.2,
        mc_p5=-423.0,
        mc_loss_prob=0.27,
        mc_dd_p95=733.0,
    ) is False


def test_xag_m15_generation_weights_bias_away_from_known_bad_families():
    assert XAG_M15_FAMILY_WEIGHTS['vol_breakout'] > XAG_M15_FAMILY_WEIGHTS['ma_trend']
    assert XAG_M15_FAMILY_WEIGHTS['session_breakout'] > XAG_M15_FAMILY_WEIGHTS['rsi_range']


def test_xag_session_breakout_templates_are_no_longer_all_ma_gated():
    saw_light_template = False
    for _ in range(40):
        strat = random_strategy('XAGUSDm', 'M15', family='session_breakout')
        rule_text = f"{strat.long_entry_rule} || {strat.short_entry_rule}"
        if 'session_london == 1 and volatility > vol_min and trend_strength' in rule_text:
            saw_light_template = True
            break
    assert saw_light_template


def test_d4a_family_exit_pools_are_constrained_by_archetype():
    assert FAMILY_LIBRARY['ma_trend']['exit_templates'] != FAMILY_LIBRARY['rsi_range']['exit_templates']
    assert any('close < ma_short' in tpl for tpl in FAMILY_LIBRARY['pullback_trend']['exit_templates'])
    assert any('close < ma_short' in tpl or 'close > ma_short' in tpl for tpl in FAMILY_LIBRARY['vol_breakout']['exit_templates'])


def test_generated_family_counts_returns_counter():
    counts = generated_family_counts()
    assert hasattr(counts, 'items')


def test_structural_duplicate_pool_upsert_keeps_better_record():
    pool = StrategyPool()
    strat_a = random_strategy('BTCUSDm', 'M15', family='ma_trend')
    stats = {
        'family': 'ma_trend',
        'playbook_type': 'ma_trend',
        'strategy': {
            'family': 'ma_trend',
            'playbook_type': 'ma_trend',
            'params': strat_a.params,
            'long_entry_rule': strat_a.long_entry_rule,
            'short_entry_rule': strat_a.short_entry_rule,
            'exit_rule': strat_a.exit_rule,
            'sl_atr_mult': strat_a.sl_atr_mult,
            'tp_atr_mult': strat_a.tp_atr_mult,
            'stop_loss_pips': strat_a.stop_loss_pips,
            'take_profit_pips': strat_a.take_profit_pips,
        },
    }
    pool.upsert_strategy(strat_a, stats=stats, score=1.0, status='candidate')

    strat_b = StrategyDefinition(
        name='better_clone',
        symbol=strat_a.symbol,
        timeframe=strat_a.timeframe,
        long_entry_rule=strat_a.long_entry_rule,
        short_entry_rule=strat_a.short_entry_rule,
        exit_rule=strat_a.exit_rule,
        stop_loss_pips=strat_a.stop_loss_pips,
        take_profit_pips=strat_a.take_profit_pips,
        sl_atr_mult=strat_a.sl_atr_mult,
        tp_atr_mult=strat_a.tp_atr_mult,
        params=dict(strat_a.params),
    )
    pool.upsert_strategy(strat_b, stats=stats, score=2.0, status='active')
    assert 'better_clone' in pool.strategies
    assert strat_a.name not in pool.strategies


def test_semantic_similarity_detects_near_duplicates():
    a = random_strategy('BTCUSDm', 'M15', family='ma_trend')
    b = StrategyDefinition(
        name='near_dup',
        symbol=a.symbol,
        timeframe=a.timeframe,
        long_entry_rule=a.long_entry_rule,
        short_entry_rule=a.short_entry_rule,
        exit_rule=a.exit_rule,
        stop_loss_pips=a.stop_loss_pips,
        take_profit_pips=a.take_profit_pips,
        sl_atr_mult=a.sl_atr_mult,
        tp_atr_mult=a.tp_atr_mult,
        params={**a.params, 'trend_min': float(a.params.get('trend_min', 0.1) or 0.1) + 0.03},
    )
    c = random_strategy('BTCUSDm', 'M15', family='rsi_range')
    assert semantic_similarity(a, b) > semantic_similarity(a, c)


def test_strategy_motif_maps_core_families_to_canonical_motifs():
    assert strategy_motif(random_strategy('BTCUSDm', 'M15', family='ma_trend')) == 'trend_continuation'
    assert strategy_motif(random_strategy('BTCUSDm', 'M15', family='pullback_trend')) == 'trend_pullback'
    assert strategy_motif(random_strategy('BTCUSDm', 'M15', family='rsi_range')) == 'range_fade'


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
