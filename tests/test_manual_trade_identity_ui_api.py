from __future__ import annotations

import json

from autonomous_trading_ai.execution.manual_trade_identity import manual_trade_marker_payload
from autonomous_trading_ai.ui_api import adapters


def test_manual_trade_marker_payload_matches_ticket_contract():
    payload = manual_trade_marker_payload()

    assert payload == {
        "order_origin": "manual_user",
        "execution_origin": "operator_ui",
        "is_manual": True,
        "exclude_from_strategy_eval": True,
        "comment_tag": "clio-manual-user",
    }


def test_load_strategy_live_stats_snapshot_excludes_manual_buckets_from_autonomous_totals(tmp_path, monkeypatch):
    stats_path = tmp_path / "strategy_live_stats.json"
    stats_path.write_text(
        json.dumps(
            {
                "strategies": {
                    "alpha_strategy": {
                        "total_pnl": 125.5,
                        "num_trades": 3,
                        "last_update": "2026-04-30T16:00:00+00:00",
                        "recent_pnls": [40.0, 35.5, 50.0],
                    },
                    "manual_unmatched_XAUUSDC": {
                        "total_pnl": -20.0,
                        "num_trades": 2,
                        "last_update": "2026-04-30T16:05:00+00:00",
                        "recent_pnls": [-10.0, -10.0],
                    },
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(adapters, "STATS_PATH", stats_path)

    snapshot = adapters.load_strategy_live_stats_snapshot()

    assert snapshot["strategy_count"] == 1
    assert snapshot["total_realized_pnl"] == 125.5
    assert snapshot["total_trades"] == 3
    assert [row["name"] for row in snapshot["top_active"]] == ["alpha_strategy"]
    assert "alpha_strategy" in snapshot["strategies"]
    assert "manual_unmatched_XAUUSDC" not in snapshot["strategies"]
    assert snapshot["manual_bucket_count"] == 1
    assert snapshot["manual_total_realized_pnl"] == -20.0
    assert snapshot["manual_total_trades"] == 2
    assert "manual_unmatched_XAUUSDC" in snapshot["manual_buckets"]
