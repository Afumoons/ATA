from types import SimpleNamespace

from autonomous_trading_ai.execution import signals


class DummyStrategy:
    def __init__(self, name: str, family: str):
        self.name = name
        self.params = {"family": family}


class DummySignal:
    def __init__(self, strategy_name: str, family: str, direction: str):
        self.strategy = DummyStrategy(strategy_name, family)
        self.direction = direction


def test_dedupe_correlated_signals_blocks_when_active_direction_exposure_already_full(monkeypatch):
    monkeypatch.setattr(signals, "_recent_signal_overlap_count", lambda *args, **kwargs: 0)
    monkeypatch.setattr(signals, "_active_directional_exposure", lambda symbol: ({"long": 2}, {}))

    kept, blocked = signals._dedupe_correlated_signals(
        [DummySignal("core15_XAUUSDm_M15_aaaa", "core15", "long")],
        "XAUUSDm",
    )

    assert kept == []
    assert blocked
    assert "direction_cap:long:active=2" in blocked[0]


def test_dedupe_correlated_signals_blocks_when_active_family_exposure_already_full(monkeypatch):
    monkeypatch.setattr(signals, "_recent_signal_overlap_count", lambda *args, **kwargs: 0)
    monkeypatch.setattr(signals, "_active_directional_exposure", lambda symbol: ({"short": 1}, {("short", "meanrev"): 2}))

    kept, blocked = signals._dedupe_correlated_signals(
        [DummySignal("core15_XAUUSDm_M15_bbbb", "meanrev", "short")],
        "XAUUSDm",
    )

    assert kept == []
    assert blocked
    assert "family_cap:meanrev:short:active=2" in blocked[0]
