from autonomous_trading_ai.strategies.generator import random_strategy
from autonomous_trading_ai.strategies.live_manifest import (
    build_live_manifest,
    build_strategy_index,
    manifest_entries_for_slot,
    strategy_definition_from_manifest_entry,
    strategy_pool_from_manifest_entries,
)
from autonomous_trading_ai.strategies.pool import StrategyPool


def _stats_for(strat, family: str, wf: float = 1.0, specialist_score: float = 0.5):
    return {
        'wf_overall_sharpe': wf,
        'family': family,
        'playbook_type': family,
        'strategy': {
            'family': family,
            'playbook_type': family,
            'long_entry_rule': strat.long_entry_rule,
            'short_entry_rule': strat.short_entry_rule,
            'exit_rule': strat.exit_rule,
            'stop_loss_pips': strat.stop_loss_pips,
            'take_profit_pips': strat.take_profit_pips,
            'sl_atr_mult': strat.sl_atr_mult,
            'tp_atr_mult': strat.tp_atr_mult,
            'params': dict(strat.params or {}),
        },
        'strategy_explain': {
            'meta': {
                'specialist_score': specialist_score,
            }
        }
    }



def test_live_manifest_only_contains_live_statuses_and_embeds_strategy_payload():
    pool = StrategyPool()
    active = random_strategy('BTCUSDm', 'M15', family='ma_trend')
    exploratory = random_strategy('BTCUSDm', 'M15', family='rsi_range')
    candidate = random_strategy('BTCUSDm', 'M15', family='vol_breakout')

    pool.upsert_strategy(active, stats=_stats_for(active, 'ma_trend', wf=1.4, specialist_score=0.8), score=91.0, status='active')
    pool.upsert_strategy(exploratory, stats=_stats_for(exploratory, 'rsi_range', wf=1.0, specialist_score=0.6), score=77.0, status='exploratory')
    pool.upsert_strategy(candidate, stats=_stats_for(candidate, 'vol_breakout', wf=0.6, specialist_score=0.3), score=55.0, status='candidate')

    manifest = build_live_manifest(pool)
    names = [entry['name'] for entry in manifest['entries']]

    assert manifest['entry_count'] == 2
    assert active.name in names
    assert exploratory.name in names
    assert candidate.name not in names

    first = manifest['entries'][0]
    assert first['exit_rule']
    assert isinstance(first['params'], dict)
    assert first['family'] in {'ma_trend', 'rsi_range'}



def test_strategy_index_separates_live_index_and_archive_tiers():
    pool = StrategyPool()
    active = random_strategy('BTCUSDm', 'M15', family='ma_trend')
    candidate_a = random_strategy('BTCUSDm', 'M15', family='rsi_range')
    candidate_b = random_strategy('BTCUSDm', 'M15', family='vol_breakout')
    retired = random_strategy('BTCUSDm', 'M15', family='session_breakout')

    pool.upsert_strategy(active, stats=_stats_for(active, 'ma_trend', wf=1.5, specialist_score=0.9), score=90.0, status='active')
    pool.upsert_strategy(candidate_a, stats=_stats_for(candidate_a, 'rsi_range', wf=0.9), score=80.0, status='candidate')
    pool.upsert_strategy(candidate_b, stats=_stats_for(candidate_b, 'vol_breakout', wf=0.7), score=10.0, status='candidate')
    pool.upsert_strategy(retired, stats=_stats_for(retired, 'session_breakout', wf=0.1), score=5.0, status='retired')

    index_payload = build_strategy_index(pool, max_archive_per_slot=1)
    entries = {entry['name']: entry for entry in index_payload['entries']}

    assert entries[active.name]['tier'] == 'live'
    assert entries[candidate_a.name]['tier'] == 'index'
    assert entries[candidate_a.name]['archived'] is False
    assert entries[candidate_b.name]['tier'] == 'archive'
    assert entries[candidate_b.name]['archived'] is True
    assert entries[retired.name]['tier'] == 'archive'
    assert entries[retired.name]['archived'] is True
    assert entries[active.name]['last_manifest_rank'] == 1



def test_manifest_slot_helpers_rebuild_strategy_pool_without_json_files():
    pool = StrategyPool()
    active = random_strategy('BTCUSDm', 'M15', family='ma_trend')
    exploratory = random_strategy('XAUUSDm', 'M15', family='pullback_trend')

    pool.upsert_strategy(active, stats=_stats_for(active, 'ma_trend', wf=1.6, specialist_score=0.8), score=92.0, status='active')
    pool.upsert_strategy(exploratory, stats=_stats_for(exploratory, 'pullback_trend', wf=1.1, specialist_score=0.7), score=75.0, status='exploratory')

    manifest = build_live_manifest(pool)
    btc_entries = manifest_entries_for_slot(manifest, symbol='BTCUSDm', timeframe='M15')
    runtime_pool = strategy_pool_from_manifest_entries(btc_entries)

    assert list(runtime_pool.strategies.keys()) == [active.name]

    rebuilt = strategy_definition_from_manifest_entry(btc_entries[0])
    assert rebuilt.name == active.name
    assert rebuilt.long_entry_rule == active.long_entry_rule
    assert rebuilt.params == active.params


def test_live_manifest_applies_light_concentration_caps_before_filling_remaining_slots():
    pool = StrategyPool()

    dominant = []
    for idx in range(10):
        strat = random_strategy('BTCUSDm', 'M15', family='ma_trend')
        stats = _stats_for(strat, 'ma_trend', wf=10.0 - idx * 0.1, specialist_score=0.9)
        stats['strategy_explain']['meta']['best_regime'] = 'ranging'
        pool.upsert_strategy(strat, stats=stats, score=100.0 - idx, status='active')
        dominant.append(strat.name)

    alt_a = random_strategy('BTCUSDm', 'M15', family='pullback_trend')
    alt_a_stats = _stats_for(alt_a, 'pullback_trend', wf=7.0, specialist_score=0.8)
    alt_a_stats['strategy_explain']['meta']['best_regime'] = 'trending_up'
    pool.upsert_strategy(alt_a, stats=alt_a_stats, score=80.0, status='active')

    alt_b = random_strategy('BTCUSDm', 'M15', family='session_breakout')
    alt_b_stats = _stats_for(alt_b, 'session_breakout', wf=6.5, specialist_score=0.75)
    alt_b_stats['strategy_explain']['meta']['best_regime'] = 'high_vol'
    pool.upsert_strategy(alt_b, stats=alt_b_stats, score=79.0, status='active')

    manifest = build_live_manifest(pool, max_live_per_slot=10)
    btc_entries = manifest_entries_for_slot(manifest, symbol='BTCUSDm', timeframe='M15')

    best_regimes = [((entry.get('stats') or {}).get('strategy_explain', {}) or {}).get('meta', {}).get('best_regime') for entry in btc_entries]
    families = [entry['family'] for entry in btc_entries]

    assert len(btc_entries) == 10
    assert best_regimes.count('ranging') <= 8
    assert 'trending_up' in best_regimes
    assert 'high_vol' in best_regimes
    # Family cap is soft because final fill may relax family overflow to avoid underfilled slots.
    assert families.count('ma_trend') < 10


def test_live_manifest_recovers_family_from_legacy_rule_only_payloads():
    pool = StrategyPool()
    strat = random_strategy('BTCUSDm', 'M15', family='ma_trend')
    legacy_stats = {
        'wf_overall_sharpe': 1.2,
        'strategy': {
            'long_entry_rule': strat.long_entry_rule,
            'short_entry_rule': strat.short_entry_rule,
            'exit_rule': strat.exit_rule,
            'sl_atr_mult': strat.sl_atr_mult,
            'tp_atr_mult': strat.tp_atr_mult,
        },
        'strategy_explain': {'meta': {'specialist_score': 0.7}},
    }
    pool.upsert_strategy(strat, stats=legacy_stats, score=88.0, status='active')

    manifest = build_live_manifest(pool)
    entry = manifest_entries_for_slot(manifest, symbol='BTCUSDm', timeframe='M15')[0]

    assert entry['family'] == 'ma_trend'
    assert entry['params'].get('family') == 'ma_trend'
