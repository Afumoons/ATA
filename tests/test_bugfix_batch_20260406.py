import sys
import types

import pandas as pd

from autonomous_trading_ai.backtests.engine import run_backtest
from autonomous_trading_ai.backtests.walkforward import WalkForwardConfig, _split_walkforward_indices
from autonomous_trading_ai.execution.signals import Signal, _pip_params, execute_signals_for_symbol
from autonomous_trading_ai.scheduler.main import _memory_dead_zone_penalty, _memory_is_clearly_bad
from autonomous_trading_ai.strategies.base import StrategyDefinition
from autonomous_trading_ai.strategies.evolution import _strategy_fingerprint
from autonomous_trading_ai.strategies.pool import StrategyPool, StrategyRecord, _structural_fingerprint
from autonomous_trading_ai.vector_memory.research_memory import ResearchMemory


class _FakeCollection:
    def __init__(self):
        self.upserts = []

    def upsert(self, **kwargs):
        self.upserts.append(kwargs)


class _FakeMemory(ResearchMemory):
    pass


class _Result:
    def __init__(self, success=True, reason="ok", ticket=1, volume=0.1):
        self.success = success
        self.reason = reason
        self.ticket = ticket
        self.volume = volume


def _strategy(name="probe", stop_loss_pips=100, take_profit_pips=200):
    return StrategyDefinition(
        name=name,
        symbol="BTCUSDm",
        timeframe="M15",
        long_entry_rule="close > 0",
        short_entry_rule=None,
        exit_rule="False",
        stop_loss_pips=stop_loss_pips,
        take_profit_pips=take_profit_pips,
        sl_atr_mult=None,
        tp_atr_mult=None,
        params={"family": "ma_trend", "playbook_type": "ma_trend"},
    )


def test_signal_pip_params_match_execution_engine_defaults():
    assert _pip_params("XAUUSDm") == (0.01, 1.0)
    assert _pip_params("XAGUSDm") == (0.01, 0.5)
    assert _pip_params("BTCUSDm") == (1.0, 1.0)


def test_btc_execution_engine_uses_one_dollar_per_point_pip_value():
    from autonomous_trading_ai.execution.engine import _pip_value_for_symbol

    assert _pip_value_for_symbol("BTCUSDm") == 1.0
    assert _pip_value_for_symbol("BTCUSDc") == 1.0
    assert _pip_value_for_symbol("BTCUSD") == 1.0


def test_strategy_fingerprints_include_fixed_sl_tp_pips():
    base = _strategy(name="a", stop_loss_pips=100, take_profit_pips=200)
    changed_sl = _strategy(name="b", stop_loss_pips=150, take_profit_pips=200)
    changed_tp = _strategy(name="c", stop_loss_pips=100, take_profit_pips=250)

    assert _strategy_fingerprint(base) != _strategy_fingerprint(changed_sl)
    assert _strategy_fingerprint(base) != _strategy_fingerprint(changed_tp)
    assert _structural_fingerprint(base) != _structural_fingerprint(changed_sl)
    assert _structural_fingerprint(base) != _structural_fingerprint(changed_tp)


def test_walkforward_config_no_longer_exposes_unused_train_ratio():
    cfg = WalkForwardConfig()
    assert not hasattr(cfg, "train_ratio")
    assert _split_walkforward_indices(700, cfg.n_splits, cfg.min_test_bars)


def test_backtest_tracks_take_profit_touch_in_same_bar_ambiguity():
    strat = StrategyDefinition(
        name="same_bar_probe",
        symbol="XAUUSDm",
        timeframe="M15",
        long_entry_rule="close > 0",
        short_entry_rule=None,
        exit_rule="False",
        stop_loss_pips=10,
        take_profit_pips=10,
        sl_atr_mult=None,
        tp_atr_mult=None,
        params={},
    )

    df = pd.DataFrame([
        {"time": "2026-01-01 00:00:00", "open": 100.0, "high": 100.0, "low": 100.0, "close": 100.0},
        {"time": "2026-01-01 00:15:00", "open": 100.0, "high": 100.3, "low": 99.7, "close": 100.0},
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

    assert result.stats["same_bar_ambiguity_count"] == 1.0
    assert result.stats["same_bar_ambiguity_stop_loss_count"] == 1.0
    assert result.stats["same_bar_ambiguity_take_profit_count"] == 1.0


def test_research_memory_store_clears_query_cache():
    mem = ResearchMemory.__new__(ResearchMemory)
    mem.cfg = None
    mem.collection = _FakeCollection()
    mem._query_cache = {"stale": [{"id": "old"}]}
    mem._query_cache_max = 256

    mem.store_strategy_result(
        strategy_name="s1",
        symbol="XAUUSDm",
        timeframe="M15",
        stats={"return_pct": 1.2, "score": 3.4},
    )

    assert mem.collection.upserts
    assert mem._query_cache == {}


def test_memory_veto_and_dead_zone_can_share_prefetched_neighbors():
    strat = _strategy(name="memory_probe")
    queried = []
    neighbors = [
        {
            "stat_sharpe_ratio": -0.2,
            "stat_profit_factor": 0.95,
            "stat_return_pct": -8.0,
            "stat_wf_overall_sharpe": 0.01,
            "meta_family": "ma_trend",
            "stat_family": "ma_trend",
        }
        for _ in range(12)
    ]

    class _QueryMemory:
        def query_similar_strategies(self, **kwargs):
            queried.append(kwargs)
            return list(neighbors)

    memory = _QueryMemory()
    prefetched = memory.query_similar_strategies(symbol="BTCUSDm", timeframe="M15", text="probe", n_results=12)

    assert _memory_is_clearly_bad(strat, memory, "BTCUSDm", "M15", neighbors=prefetched) is True
    penalty, meta = _memory_dead_zone_penalty(strat, memory, "BTCUSDm", "M15", neighbors=prefetched)

    assert penalty > 0.0
    assert meta["same_family_ratio"] == 1.0
    assert len(queried) == 1


def test_execute_signals_refreshes_open_position_snapshot_after_success(monkeypatch):
    latest = pd.DataFrame([
        {
            "time": "2026-01-01 00:00:00",
            "close": 100.0,
            "ma_short": 1.0,
            "ma_long": 1.0,
            "trend_strength": 0.5,
            "rsi": 50.0,
            "regime": "unknown",
            "regime_class": "range",
            "regime_type": "range",
            "regime_confidence": 1.0,
            "vol_regime": "normal",
            "session": "london",
            "in_news_lockout": False,
        }
    ])
    strat = _strategy(name="dup_guard")
    pool = StrategyPool(
        strategies={
            strat.name: StrategyRecord(
                name=strat.name,
                symbol="BTCUSDm",
                timeframe="M15",
                status="active",
                score=1.0,
                stats={
                    "strategy": {
                        "long_entry_rule": strat.long_entry_rule,
                        "short_entry_rule": strat.short_entry_rule,
                        "exit_rule": strat.exit_rule,
                        "stop_loss_pips": strat.stop_loss_pips,
                        "take_profit_pips": strat.take_profit_pips,
                        "sl_atr_mult": strat.sl_atr_mult,
                        "tp_atr_mult": strat.tp_atr_mult,
                        "params": strat.params,
                    },
                    "strategy_explain": {},
                },
            )
        }
    )

    monkeypatch.setitem(sys.modules, "MetaTrader5", types.SimpleNamespace())

    positions_calls = iter([[], [types.SimpleNamespace(ticket=1, comment="", symbol="BTCUSDm")]])
    monkeypatch.setattr(
        "autonomous_trading_ai.execution.signals.generate_signals_for_row",
        lambda row, strategies: [Signal(strategy=strat, direction="long"), Signal(strategy=strat, direction="long")],
    )
    monkeypatch.setattr(
        "autonomous_trading_ai.execution.signals._build_routing_context",
        lambda row: types.SimpleNamespace(
            regime_label="unknown",
            candidate_regime_labels=["unknown"],
            regime_class="range",
            regime_type="range",
            regime_confidence=1.0,
            vol_regime="normal",
            session="london",
            trend_strength=0.5,
        ),
    )
    monkeypatch.setattr(
        "autonomous_trading_ai.execution.signals.can_open_new_trade",
        lambda **kwargs: True,
    )
    monkeypatch.setattr(
        "autonomous_trading_ai.execution.signals.strategy_has_open_position",
        lambda strategy_name, symbol, timeframe, positions=None: bool(positions),
    )
    monkeypatch.setattr(
        "autonomous_trading_ai.execution.signals.execute_trade",
        lambda **kwargs: _Result(success=True, reason="ok", ticket=1, volume=0.1),
    )
    monkeypatch.setattr(
        "autonomous_trading_ai.execution.signals.register_ticket",
        lambda ticket, strategy_name: None,
    )
    monkeypatch.setattr(
        "autonomous_trading_ai.execution.signals.strategy_definition_from_manifest_entry",
        lambda entry: strat,
        raising=False,
    )

    import autonomous_trading_ai.execution.signals as signals_mod
    fake_mt5 = types.SimpleNamespace(positions_get=lambda symbol=None: next(positions_calls))
    monkeypatch.setitem(sys.modules, "MetaTrader5", fake_mt5)

    live_monitor_mod = types.SimpleNamespace(_get_account_equity=lambda: 10000.0)
    monkeypatch.setitem(sys.modules, "autonomous_trading_ai.execution.live_monitor", live_monitor_mod)

    results, summary = execute_signals_for_symbol("BTCUSDm", "M15", latest, pool, risk_perc=1.0)

    assert [reason for _, reason in results] == ["ok", "blocked_existing_position"]
    assert summary["blocked_existing_position"] is True


def test_empty_backtest_returns_full_zero_trade_stats():
    strat = _strategy(name="empty_df_probe")
    df = pd.DataFrame(columns=["time", "open", "high", "low", "close"])

    result = run_backtest(df, strat, initial_equity=1234.0)

    assert result.stats["initial_equity"] == 1234.0
    assert result.stats["final_equity"] == 1234.0
    assert result.stats["return_pct"] == 0.0
    assert result.stats["num_trades"] == 0.0
    assert result.stats["profit_factor"] == 0.0
    assert result.stats["max_drawdown_pct"] == 0.0
