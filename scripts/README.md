# scripts/ – Utility, Debug & Operator Tools

## Purpose

This directory contains manually-invoked tools that help inspect, maintain,
and operate the `autonomous_trading_ai` project.

These scripts are intentionally outside the always-on scheduler loop. They are
for:

- operator inspection
- debugging
- one-off maintenance
- research support
- manual health checks

## General Usage

Run scripts from the **package parent directory** so the package imports correctly.

Typical pattern:

```powershell
cd C:\laragon\www
python -m autonomous_trading_ai.scripts.<script_name>
```

## What This Folder Contains

Current scripts in this folder include:

- `ai_generate_strategies.py`
- `analyze_mt5_report.py`
- `backfill_research_memory_from_pool.py`
- `debug_signals_for_latest_bar.py`
- `inspect_research_memory.py`
- `manual_execute_trade.py`
- `mt5_analyze_history_html.py`
- `mt5_analyze_history_tmp.py`
- `pre_session_check.py`
- `print_live_summary.py`
- `print_top_strategies.py`
- `promote_strategies.py`
- `prune_strategies.py`
- `prune_strategies_btc.py`
- `rebuild_pool_status.py`
- `reset_strategy_memory.py`
- `scrape_news.py`
- `reconcile_strategy_live_stats.py`
- `telegram_signal_listener.py`

## Script Categories

### Research / analysis helpers

- `print_top_strategies.py`
- `ai_generate_strategies.py`
- `inspect_research_memory.py`
- `backfill_research_memory_from_pool.py`

### MT5 history / report helpers

- `analyze_mt5_report.py`
- `mt5_analyze_history_html.py`
- `mt5_analyze_history_tmp.py`

### Live debugging / operations

- `debug_signals_for_latest_bar.py`
- `manual_execute_trade.py`
- `print_live_summary.py`
- `pre_session_check.py`

### Pool maintenance

- `promote_strategies.py`
- `prune_strategies.py`
- `prune_strategies_btc.py`
- `rebuild_pool_status.py`
- `reconcile_strategy_live_stats.py`

### News / memory maintenance

- `scrape_news.py`
- `reset_strategy_memory.py`

### External signal ingestion

- `telegram_signal_listener.py`

## Pass 3 Relevance

Pass 3 increases the value of operator/debug scripts because the live system is
now more selective and context-driven. When a strategy does **not** execute,
there are many more legitimate reasons than before:

- blocked session
- blocked regime
- poor regime edge
- low regime confidence
- volatility mismatch
- daily risk lock
- existing open slot
- no entry trigger

That makes scripts like:

- `debug_signals_for_latest_bar.py`
- `print_live_summary.py`
- `print_top_strategies.py`

more operationally important.

## Notable Scripts

### `print_top_strategies.py`

Read-only inspection of the strongest pool entries, including score and explain
metadata.

### `ai_generate_strategies.py`

Exports a compact JSON summary of top/bottom strategies for AI-assisted idea
work. It does not itself call an AI service.

### `debug_signals_for_latest_bar.py`

Most important live-debug script. It helps inspect the current routing context,
strategy set, regime-edge view, execution summary, and signal outcomes for the latest bar.

**Warning:** because it routes through real execution code, it may place trades
if conditions and guards allow.

### `print_live_summary.py`

Quick status dashboard for daily equity, pool counts, live stats, and open
trades.

### `rebuild_pool_status.py`

Useful maintenance helper for reconstructing/reconciling strategy statuses when
pool state needs repair or normalization.

### `telegram_signal_listener.py`

Telethon-based Telegram public-channel/user-session listener for mentor signals.

Typical shadow run:

```powershell
cd C:\laragon\www
python -m autonomous_trading_ai.scripts.telegram_signal_listener --channel japsku --history 20 --mode shadow
```

It is also autostarted by `scheduler.main` when Telegram credentials are configured in `.env`.

### `scrape_news.py`

Standalone Forex Factory scraper useful for manual inspection, cache refresh,
or validating news normalization outside the main scheduler loop.

## Safety Notes

Some scripts are read-only. Some are definitely **not**.

### Read-mostly / analysis-oriented

Usually safe for inspection:

- `print_top_strategies.py`
- `ai_generate_strategies.py`
- `inspect_research_memory.py`
- `analyze_mt5_report.py`
- `print_live_summary.py`
- `scrape_news.py`

### State-mutating / potentially risky

Use with intent:

- `promote_strategies.py`
- `prune_strategies.py`
- `prune_strategies_btc.py`
- `rebuild_pool_status.py`
- `reset_strategy_memory.py`

### Can hit live execution

Treat as production-sensitive:

- `debug_signals_for_latest_bar.py`
- `manual_execute_trade.py`
- `telegram_signal_listener.py --mode auto_live`

## Gotchas / Notes

- Scripts assume the package is importable from the package parent directory (`C:\laragon\www`).
- Some scripts rely on the project venv having optional dependencies installed.
- Any script touching MT5 should be assumed capable of interacting with real
  account state unless proven otherwise.
- The README should stay aligned with the actual script inventory; this folder
  evolves quickly.

## Changelog (Docs)

- 2026-04-03: Added `reconcile_strategy_live_stats.py` and refreshed script inventory around live-attribution maintenance.

- 2026-03-21 to 2026-03-22: Initial script inventory documentation, including
  research, MT5 analysis, maintenance, and news tooling.
- 2026-03-27: Updated for pass 3, refreshed the inventory, added newer scripts
  such as `rebuild_pool_status.py`, and reframed the folder around operator
  visibility/debugging for a more selective live-routing system.

- 2026-05-20: Added `telegram_signal_listener.py`, corrected package-parent run path, and documented shadow/autostart/live sensitivity.
