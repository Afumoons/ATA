# scripts/ – Utility & Research Scripts

## Purpose

This directory contains **utility scripts** that operate on the
`autonomous_trading_ai` project from the outside:

- Inspect and debug the strategy pool and live state.
- Prepare compact inputs for AI-assisted research (Clio) without affecting
  live trading logic.
- Maintain/clean research memory and strategy pool.
- Run pre-session health checks.

These scripts are intended to be run manually from the command line. They do
not change trading rules at runtime; they only read or write supporting
artifacts (JSON files, logs, vector DB), or call existing execution code
in a controlled way.

> Run all scripts from the **workspace root** so `autonomous_trading_ai` is
> importable as a package.
>
> Example base command (PowerShell):
>
> ```powershell
> cd C:\Users\afusi\.openclaw\workspace
> .\autonomous_trading_ai\.venv\Scripts\python.exe -m autonomous_trading_ai.scripts.<script_name>
> ```

---

## `print_top_strategies.py`

### Purpose

Inspect the **top strategies in the pool** and print a concise but rich
summary to the console, including:

- Core stats (return %, Sharpe, max DD, PF, trade count).
- Regime-level PnL (`regime_pnl`).
- Stability metrics (sub-period Sharpe, Sharpe std).
- News behavior and meta tags (trend follower vs range trader, best/worst regime).

Useful when you want to quickly understand *which* strategies the system
currently considers best and **why**.

### Usage

From workspace root:

```powershell
cd C:\Users\afusi\.openclaw\workspace
.autonomous_trading_ai\.venv\Scripts\python.exe -m autonomous_trading_ai.scripts.print_top_strategies `
  --symbol XAUUSDm `
  --timeframe M15 `
  --status active `
  --limit 10
```

Arguments:

- `--symbol` (default: `XAUUSDm`)
- `--timeframe` (default: `M15`)
- `--status` (optional): filter by `active` / `candidate` / `disabled`.
  - If omitted, shows any status.
- `--limit` (default: `10`): number of strategies to display.

### What It Reads

- `strategies/pool_state.json` via `strategies.pool.load_pool()`.

### What It Writes

- Console output only. No files are modified.

---

## `ai_generate_strategies.py`

### Purpose

Prepare a **compact JSON summary** of the current strategy pool for
AI-assisted research. The script itself **does not call any AI**; it just
materializes a view that Clio can read and reason about.

Typical workflow:

1. Run this script to dump the top/bottom strategies into
   `backtests/results/ai_research_input.json`.
2. Clio reads that JSON, analyses patterns (what works/fails in which
   regimes/sessions), and proposes new `StrategyDefinition` configs.
3. Proposed strategies are written as JSON files into
   `strategies/generated/` and picked up by the normal research loop.

Live trading remains deterministic; AI is used **offline** for idea
generation.

### Usage

From workspace root:

```powershell
cd C:\Users\afusi\.openclaw\workspace
.autonomous_trading_ai\.venv\Scripts\python.exe -m autonomous_trading_ai.scripts.ai_generate_strategies `
  --symbol XAUUSDm `
  --timeframe M15 `
  --limit 20 `
  --include_bottom 5
```

Arguments:

- `--symbol` (default: `XAUUSDm`)
- `--timeframe` (default: `M15`)
- `--limit` (default: `20`): number of **top-scoring** strategies to include.
- `--include_bottom` (default: `5`): number of **worst** strategies to add for
  contrast.

The script will:

- Load the pool via `strategies.pool.load_pool()`.
- Filter by symbol/timeframe.
- Take top-N and bottom-M by score (deduplicated).
- Extract a light-weight subset of stats and `strategy_explain`.
- Write JSON to:

```text
backtests/results/ai_research_input.json
```

### What It Writes

- `backtests/results/ai_research_input.json` with structure:

```json
{
  "symbol": "XAUUSDm",
  "timeframe": "M15",
  "total_strategies": 123,
  "selected_count": 25,
  "strategies": [
    {
      "name": "core15_XAUUSDm_M15_...",
      "symbol": "XAUUSDm",
      "timeframe": "M15",
      "status": "active",
      "score": 2.32,
      "stats": {
        "return_pct": 9.53,
        "sharpe_ratio": 4.17,
        "max_drawdown_pct": -7.39,
        "profit_factor": 1.75,
        "win_rate": 0.52,
        "num_trades": 56
      },
      "strategy_explain": {
        "regime_pnl": { "...": "..." },
        "stability": { "...": "..." },
        "news_behavior": { "...": "..." },
        "meta": { "...": "..." }
      }
    }
  ]
}
```

Clio uses this file as context for offline research; the trading system does
not read it at runtime.

---

## `analyze_mt5_report.py`

### Purpose

Parse an exported **MT5 HTML history report** and calculate summary statistics
for different trade comment groups (manual vs various Clio bridges).

It groups closed trades by:

- `comment` pattern (e.g. `manual`, `clio_bridge`, `clio_auto_manual`, `other`).
- `symbol`.

For each group it prints number of trades, win rate, average PnL, and total PnL,
plus the top 10 winners and losers.

### Usage

1. Export `ReportHistory-415292731.html` from MT5 into:

   ```text
   mt5_report/ReportHistory-415292731.html
   ```

2. From workspace root:

   ```powershell
   cd C:\Users\afusi\.openclaw\workspace
   .autonomous_trading_ai\.venv\Scripts\python.exe -m autonomous_trading_ai.scripts.analyze_mt5_report
   ```

### What It Reads

- `mt5_report/ReportHistory-415292731.html` (HTML export from MT5).

### What It Writes

- Console output only (group statistics and top winners/losers).

> Requires `beautifulsoup4` to be installed in the virtualenv.

---

## `backfill_research_memory_from_pool.py`

### Purpose

Backfill the **vector ResearchMemory** with strategy results from the current
strategy pool. This is meant to sync `strategies.pool` → `vector_memory`
so that research tools have up-to-date stats for all strategies.

### Usage

From workspace root:

```powershell
cd C:\Users\afusi\.openclaw\workspace
.autonomous_trading_ai\.venv\Scripts\python.exe -m autonomous_trading_ai.scripts.backfill_research_memory_from_pool
```

### What It Reads

- Strategy pool via `strategies.pool.load_pool()`.

### What It Writes

- For each strategy that has `rec.stats` populated, calls
  `ResearchMemory.store_strategy_result(...)`.
- Under the hood this updates the Chroma collection used by
  `vector_memory/research_memory.py` (`strategy_research` collection).
- Prints `BACKFILL_WRITTEN <count>` to the console.

> Idempotent at the logical level; re-running will re-store stats for all
> current strategies but does **not** change any trading logic.

---

## `debug_signals_for_latest_bar.py`

### Purpose

Debug what the system is doing **on the latest bar** for each managed symbol.

For each symbol in `scheduler.main.MANAGED_SYMBOLS` it:

- Loads the latest features & regimes for `TIMEFRAME`.
- Prints latest bar time and current regime.
- Prints current daily risk state (equity, daily PnL/return, trades today,
  daily lock flags).
- Lists all pool strategies for that symbol/timeframe with status and score.
- Computes per-strategy "regime edge" for the current regime.
- Calls `execute_signals_for_symbol(...)` and prints any signals that actually
  execute.

### WARNING

This script calls the **real execution pipeline** via
`execution.signals.execute_signals_for_symbol`. It is meant for
supervised debugging while connected to a demo or low-risk environment.

It will:

- Initialize MT5 (`initialize_mt5()`),
- Call the live account equity API,
- Potentially place trades, depending on current signals and risk limits.

Use only when you fully understand the current environment.

### Usage

From workspace root:

```powershell
cd C:\Users\afusi\.openclaw\workspace
.autonomous_trading_ai\.venv\Scripts\python.exe -m autonomous_trading_ai.scripts.debug_signals_for_latest_bar
```

### What It Reads

- Features for each managed symbol/timeframe via `research.features.load_features`.
- Strategy pool via `strategies.pool.load_pool()`.
- Risk config via `config.risk_config`.
- Live MT5 account state via `_get_account_equity()` and
  `live_state_utils.load_daily_state`.

### What It Writes

- Console output (debug info and any executed signals).
- Any live trades and live_state updates are handled by the underlying
  execution stack, **not** by this script directly.

---

## `inspect_research_memory.py`

### Purpose

Summarize the current **ResearchMemory (Chroma)** contents, grouped by
`symbol` and `timeframe`, focusing on key performance metrics:

- Sharpe ratio (`stat_sharpe_ratio`).
- Profit factor (`stat_profit_factor`).
- Return % (`stat_return_pct`).

For each metric and symbol/timeframe it computes quantiles (min, 25%, median,
75%, max, mean).

### Usage

From workspace root:

```powershell
cd C:\Users\afusi\.openclaw\workspace
.autonomous_trading_ai\.venv\Scripts\python.exe -m autonomous_trading_ai.scripts.inspect_research_memory
```

### What It Reads

- Entire `ResearchMemory` collection (`strategy_research` in Chroma) via
  `ResearchMemory().collection.get()`.

### What It Writes

- Markdown summary to `vector_memory/MEMORY_SUMMARY.md`.
- Console output:
  - `TOTAL_DOCS <n>`
  - For each symbol/timeframe: median and IQR of return %.

This is purely analytical; it does **not** affect live trading.

---

## `manual_execute_trade.py`

### Purpose

Manually fire a **single test trade** through the real execution engine.

Hard-coded example:

- Strategy name: `manual_test_xau`.
- Symbol: `XAUUSDm`.
- Direction: `long`.
- Risk: `0.5%` of equity.
- SL/TP: 150 pips each, `pip_size=0.01`.

### WARNING

This uses `execution.engine.execute_trade`, which will place a real trade on
whichever MT5 terminal the Python process is connected to.

- Use only in a **demo account** or in very controlled conditions.
- Adapt parameters in the script before using in production.

### Usage

From workspace root:

```powershell
cd C:\Users\afusi\.openclaw\workspace
.autonomous_trading_ai\.venv\Scripts\python.exe -m autonomous_trading_ai.scripts.manual_execute_trade
```

### What It Reads/Writes

- Uses MT5 via `initialize_mt5()` and `shutdown_mt5()`.
- All order placement and state updates are handled by the execution engine.
- Prints the result object of `execute_trade` to console.

---

## `pre_session_check.py`

### Purpose

Automated version of the **manual pre-session routine**:

1. Refresh data, features, and regimes.
2. Run one research/evolution cycle.
3. Print a concise summary of risk config and top `XAUUSDm M15` strategies.

### Usage

From workspace root:

```powershell
cd C:\Users\afusi\.openclaw\workspace
.autonomous_trading_ai\.venv\Scripts\python.exe -m autonomous_trading_ai.scripts.pre_session_check
```

### What It Does

- Calls `scheduler.main.job_update_data()`.
- Calls `scheduler.main.job_research_strategies()`.
- Prints current `risk_config` values (per-trade risk, max DD, daily limits).
- Loads the strategy pool and prints details for the top 5 active strategies
  for `XAUUSDm M15`, including:
  - Core stats (return%, Sharpe, max DD, PF, trade count).
  - Regime PnL breakdown.
  - News behavior and meta (trend/range, best/worst regime).

### What It Reads/Writes

- Reads/writes whatever `job_update_data` and `job_research_strategies`
  normally touch (data, backtests, pool files).
- Does **not** place trades directly.

---

## `print_live_summary.py`

### Purpose

Quick, read-only **status dashboard** for the autonomous trading system.

It prints:

- Daily account equity and PnL.
- Count of strategies by status.
- Top-N active strategies by backtest score.
- (If available) per-strategy live PnL from execution stats.
- (If available) summary of currently open MT5 positions.

### Usage

From workspace root, venv activated:

```powershell
cd C:\Users\afusi\.openclaw\workspace
python -m autonomous_trading_ai.scripts.print_live_summary
```

### What It Reads

- `execution/live_state.json`.
- `strategies/pool_state.json`.
- `execution/strategy_live_stats.json` (if present, usually from `live_observer.py`).
- `execution/open_trades.json` (if present, usually from `live_observer.py`).

### What It Writes

- Console output only. No files are modified.

---

## `promote_strategies.py`

### Purpose

Automatically **promote top candidate strategies** to `active` status in the
pool.

By default it promotes the top 3 candidates by score.

### Usage

From workspace root:

```powershell
cd C:\Users\afusi\.openclaw\workspace
.autonomous_trading_ai\.venv\Scripts\python.exe -m autonomous_trading_ai.scripts.promote_strategies
```

### What It Reads/Writes

- Loads pool via `strategies.pool.load_pool()`.
- Selects `pool.top_strategies(status_filter="candidate", limit=3)`.
- For each selected strategy, sets status to `active`.
- Saves updated pool via `strategies.pool.save_pool()`.

> This only changes the JSON `pool_state.json` and **does not** alter
> individual strategy definitions or any live trades.

---

## `prune_strategies.py`

### Purpose

Prune obviously **weak or dummy strategies** from the pool for
`XAUUSDm M15`, and clean up their generated JSON configs.

### Pruning Logic (XAUUSDm M15)

A strategy is pruned if **symbol == `XAUUSDm`** and **timeframe == `M15`** and
**any** of the following groups match:

1. **Disabled / weak candidates**:
   - `status` in `{"disabled", "candidate"}` AND `accepted == False`, and
   - any of:
     - `return_pct < -3.0`,
     - `profit_factor < 1.0`,
     - `wf_overall_sharpe < 0.0`,
     - `num_trades < 10`,
     - `final_equity < 7500` (if present).
2. **Dummy strategies**:
   - `num_trades == 0`, `return_pct == 0`, and `accepted == False`.

### Usage

From workspace root:

```powershell
cd C:\Users\afusi\.openclaw\workspace
.autonomous_trading_ai\.venv\Scripts\python.exe -m autonomous_trading_ai.scripts.prune_strategies
```

### What It Reads/Writes

- Reads `strategies/pool_state.json`.
- Writes a pruned version back to `strategies/pool_state.json` (via a
  `.tmp` file + replace).
- Deletes any corresponding `strategies/generated/<name>.json` files for
  pruned strategies.
- Prints summary counts to console (before/after/pruned, JSON files removed).

> Only affects `XAUUSDm M15` strategies. All other symbols/timeframes are
> left unchanged.

---

## `prune_strategies_btc.py`

### Purpose

Same as `prune_strategies.py`, but focusing on **BTCUSDm M15** strategies.

### Pruning Logic (BTCUSDm M15)

A strategy is pruned if **symbol == `BTCUSDm`** and **timeframe == `M15`** and
**any** of the following groups match:

1. **Disabled / weak candidates**:
   - `status` in `{"disabled", "candidate"}` AND `accepted == False`, and
   - any of:
     - `return_pct < -3.0`,
     - `profit_factor < 1.0`,
     - `wf_overall_sharpe < 0.0`,
     - `num_trades < 10`,
     - `final_equity < 7500` (if present).
2. **Dummy strategies**:
   - `num_trades == 0`, `return_pct == 0`, and `accepted == False`.

### Usage

From workspace root:

```powershell
cd C:\Users\afusi\.openclaw\workspace
.autonomous_trading_ai\.venv\Scripts\python.exe -m autonomous_trading_ai.scripts.prune_strategies_btc
```

### What It Reads/Writes

- Same behavior as `prune_strategies.py`, but only for `BTCUSDm M15`.
- Reads and rewrites `strategies/pool_state.json`.
- Deletes any `strategies/generated/<name>.json` belonging to pruned
  BTCUSDm M15 strategies.

---

## `reset_strategy_memory.py`

### Purpose

**Interactively reset** the `strategy_research` Chroma collection used by
`vector_memory/ResearchMemory`.

This is useful when you want to wipe all historical research docs and start
from a clean slate, without touching other collections.

### WARNING – Destructive

- This script **deletes** the entire `strategy_research` collection and then
  recreates an empty collection with the same name.
- Other collections under `chroma_data` are not modified.
- Use only when you intentionally want to clear research memory.

### Usage

From workspace root:

```powershell
cd C:\Users\afusi\.openclaw\workspace
.autonomous_trading_ai\.venv\Scripts\python.exe -m autonomous_trading_ai.scripts.reset_strategy_memory
```

The script will:

1. List all existing Chroma collections under `chroma_data`.
2. Show current document count for `strategy_research`.
3. Ask for confirmation: `Hapus collection ini? (y/n):`
4. If you type `y`:
   - Delete the collection.
   - Recreate an empty `strategy_research` collection.

### What It Reads/Writes

- Uses `chroma_data/` as the persistent storage path.
- Deletes and recreates the `strategy_research` collection only.

---

## `scrape_news.py`

### Purpose

Standalone **Forex Factory news scraper** that pulls the public JSON economic
calendar (same CDN used by common FF indicators) and normalizes it into the
`news_events.parquet` format expected by `features.py`.

Designed for:

- Keeping a local **economic calendar cache** aligned with FF.
- Marking **gold-relevant events** (based on currency + title keywords).
- Quickly inspecting upcoming high-impact events around XAU.

### Usage

From workspace root:

```powershell
cd C:\Users\afusi\.openclaw\workspace
.autonomous_trading_ai\.venv\Scripts\python.exe -m autonomous_trading_ai.scripts.scrape_news `
  --weeks 2 `
  --csv `
  --min-impact 2
```

Common options:

- `--weeks N` (default: `2`)
  - `1` = this week only.
  - `2` = this week + next week (default).
- `--include-last`
  - Also fetch **last week** (useful for recent backfill).
- `--output PATH`
  - Custom parquet output path. Default: `scripts/news_events.parquet`.
- `--csv`
  - Also export `PATH.csv` for manual inspection.
- `--show`
  - **Do not save**; only print table to terminal.
- `--gold-only`
  - Filter to **gold-relevant** events only (based on currency + keywords).
- `--min-impact {0,1,2,3}`
  - Minimum impact to keep (`0`=all, `3`=High only).
- `--upcoming HOURS`
  - Show summary of gold-relevant impact≥2 events in the next N hours
    (default: 24h).
- `--no-color`
  - Disable ANSI colors in terminal output.

### What It Reads

- Forex Factory JSON CDN:
  - `https://nfs.faireconomy.media/ff_calendar_thisweek.json`
  - `https://nfs.faireconomy.media/ff_calendar_nextweek.json`
  - (optionally) `https://nfs.faireconomy.media/ff_calendar_lastweek.json`

### What It Writes

- Default: `scripts/news_events.parquet` with columns:
  - `datetime_utc` (UTC timestamp)
  - `currency`
  - `impact` (`0–3`)
  - `impact_label` (`Holiday`, `Low`, `Medium`, `High`)
  - `event_name`
  - `forecast`, `previous`, `actual` (stringified)
  - `is_gold_relevant` (bool)
- Optional: `scripts/news_events.csv` when `--csv` is passed.
- Console output:
  - Fetch status per week.
  - Summary counts (gold-relevant, high-impact, date range).
  - Upcoming-event summary for next N hours.
  - Full formatted table (unless filters remove all rows).

### Dependencies

- `requests`
- `pandas`

If missing, the script prints a clear install hint and exits cleanly.

---

## Changelog (Docs)

- 2026-03-21: Initial README for `scripts/` documenting
  `print_top_strategies` and `ai_generate_strategies`.
- 2026-03-21: Expanded README to cover `analyze_mt5_report`,
  `backfill_research_memory_from_pool`, `debug_signals_for_latest_bar`,
  `inspect_research_memory`, `manual_execute_trade`, `pre_session_check`,
  `print_live_summary`, `promote_strategies`, `prune_strategies`,
  `prune_strategies_btc`, and `reset_strategy_memory`.
- 2026-03-22: Added documentation for `scrape_news` (FF calendar scraper).
