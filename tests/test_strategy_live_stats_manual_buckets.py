from __future__ import annotations

import json
from pathlib import Path

from autonomous_trading_ai.execution import audit_utils
from autonomous_trading_ai.execution import strategy_live_stats as sls
from autonomous_trading_ai.execution.live_decay import compute_live_decay_signal
from autonomous_trading_ai.scripts.reconcile_strategy_live_stats import _reconcile_unmatched_manual_buckets


def test_manual_bucket_name_uses_explicit_unmatched_prefix():
    assert sls.manual_bucket_name("XAUUSDc", unmatched=True) == "manual_unmatched_XAUUSDC"
    assert sls.manual_bucket_name("XAUUSDc", unmatched=False) == "manual_XAUUSDC"


def test_register_manual_bucket_pnl_writes_stats(tmp_path, monkeypatch):
    stats_path = tmp_path / "strategy_live_stats.json"
    monkeypatch.setattr(sls, "STATS_PATH", stats_path)

    bucket = sls.register_manual_bucket_pnl(symbol="XAUUSDc", pnl=-296.0, unmatched=True)

    stats = sls.load_all_strategy_stats()
    assert bucket == "manual_unmatched_XAUUSDC"
    assert bucket in stats
    assert stats[bucket].total_pnl == -296.0
    assert stats[bucket].num_trades == 1
    assert stats[bucket].recent_pnls == [-296.0]


def test_manual_bucket_is_ignored_by_live_decay():
    stats = sls.StrategyLiveStats(
        name="manual_unmatched_XAUUSDC",
        total_pnl=-500.0,
        num_trades=20,
        recent_pnls=[-50.0] * 10,
    )

    signal = compute_live_decay_signal("manual_unmatched_XAUUSDC", "active", stats)

    assert signal.signal_level == "healthy"
    assert signal.reason == "manual_bucket_ignored"
    assert signal.total_trades == 20


def test_reconcile_unmatched_manual_buckets_rolls_audit_rows_into_stats(tmp_path, monkeypatch):
    unmatched_path = tmp_path / "unmatched_closed_deals.json"
    unmatched_rows = [
        {
            "recorded_at": "2026-04-06T08:14:28+00:00",
            "manual_bucket": "manual_unmatched_XAUUSDC",
            "profit": -124.0,
        },
        {
            "recorded_at": "2026-04-06T08:19:28+00:00",
            "manual_bucket": "manual_unmatched_XAUUSDC",
            "profit": 55.0,
        },
    ]
    unmatched_path.write_text(json.dumps(unmatched_rows), encoding="utf-8")
    monkeypatch.setattr(audit_utils, "UNMATCHED_CLOSED_DEALS_PATH", unmatched_path)
    monkeypatch.setattr(
        "autonomous_trading_ai.scripts.reconcile_strategy_live_stats.UNMATCHED_CLOSED_DEALS_PATH",
        unmatched_path,
    )

    stats = {}
    applied = _reconcile_unmatched_manual_buckets(stats)

    rec = stats["manual_unmatched_XAUUSDC"]
    assert applied == 2
    assert rec.total_pnl == -69.0
    assert rec.num_trades == 2
    assert rec.recent_pnls == [-124.0, 55.0]
    assert rec.last_update == "2026-04-06T08:19:28+00:00"
