from autonomous_trading_ai.strategies.pool import StrategyPool, StrategyRecord, normalize_status, summarize_status_counts


def test_normalize_status_accepts_known_values_and_falls_back_to_candidate():
    assert normalize_status("active") == "active"
    assert normalize_status("disabled") == "disabled"
    assert normalize_status(None) == "candidate"
    assert normalize_status("weird-status") == "candidate"


def test_strategy_record_from_dict_normalizes_unknown_status_to_candidate():
    rec = StrategyRecord.from_dict(
        {
            "name": "s1",
            "symbol": "XAUUSDm",
            "timeframe": "M15",
            "status": "broken-status",
            "score": 1.23,
            "stats": {},
        }
    )
    assert rec.status == "candidate"


def test_summarize_status_counts_includes_disabled_without_keyerror():
    pool = StrategyPool(
        strategies={
            "a": StrategyRecord("a", "XAUUSDm", "M15", "active", 1.0, {}),
            "b": StrategyRecord("b", "XAUUSDm", "M15", "disabled", 0.5, {}),
            "c": StrategyRecord("c", "BTCUSDm", "M15", "candidate", 0.3, {}),
        }
    )

    counts = summarize_status_counts(pool.strategies)

    assert counts["active"] == 1
    assert counts["disabled"] == 1
    assert counts["candidate"] == 1
    assert counts["exploratory"] == 0
    assert counts["retired"] == 0
    assert counts["other"] == 0
