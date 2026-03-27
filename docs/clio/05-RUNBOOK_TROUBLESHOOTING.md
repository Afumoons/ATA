# RUNBOOK_TROUBLESHOOTING – autonomous_trading_ai

Quick troubleshooting checklist for Afu and Clio.

Use this when:

- no trades appear
- the scheduler is noisy or failing
- strategies seem to disappear or stop trading
- live state looks wrong
- you need a fast sanity check before deeper debugging

## 1. No trades at all

### Symptoms

- scheduler appears to run
- MT5 is open
- but no new positions are being opened

### Fast checks

1. **Is MT5 actually running and logged in?**
   - confirm live connection in MT5
   - confirm target symbols are visible and ticking

2. **Is the scheduler process actually running?**
   - expected command:

   ```powershell
   python -m autonomous_trading_ai.scheduler.main
   ```

3. **Do features exist?**
   - inspect `autonomous_trading_ai/data/features/`
   - if missing, run a manual data refresh

4. **Does the pool contain live-tier strategies?**
   - inspect `active` and `exploratory` strategies

   ```powershell
   python -m autonomous_trading_ai.scripts.print_top_strategies --symbol XAUUSDm --timeframe M15 --status active --limit 5
   python -m autonomous_trading_ai.scripts.print_top_strategies --symbol XAUUSDm --timeframe M15 --status exploratory --limit 5
   ```

5. **Is daily lock active?**
   - inspect `execution/live_state.json`
   - if `locked_for_day=true`, new trades will be blocked

6. **Is news lockout active?**
   - latest feature row may have `in_news_lockout=true`
   - in that case execution is intentionally skipped

7. **Did pass 3 routing intentionally reject everything?**
   - this is now normal in some contexts
   - common reasons:
     - blocked session
     - blocked regime
     - volatility mismatch
     - low routing confidence
     - no eligible specialist survived routing gates
     - no entry trigger on otherwise eligible strategies

## 2. A strategy that used to trade looks “dead”

Likely causes:

- it was degraded from `active` to `candidate`
- current session/regime blocks it
- it has an open slot already
- current edge is insufficient

### Check pool + live summary

```powershell
python -m autonomous_trading_ai.scripts.print_live_summary
python -m autonomous_trading_ai.scripts.print_top_strategies --symbol XAUUSDm --timeframe M15 --status candidate --limit 10
```

If it was degraded, check per-strategy live PnL and recent performance windows.

## 3. Scheduler jobs are erroring repeatedly

### Fast path

1. inspect logs under `autonomous_trading_ai/logs/`
2. search for job names such as:
   - `job_update_data`
   - `job_research_strategies`
   - `job_execute_signals`
   - `job_live_monitor`
3. focus on the **first real traceback**, not the repeated noise after it

### Common patterns

- **MT5/account calls failing**
  - MT5 not logged in
  - terminal connection lost
- **feature/data file missing**
  - data update has not run successfully yet
- **strategy definition missing**
  - pool entry references generated JSON that no longer exists
- **Chroma/research memory issue**
  - research may degrade, but live execution should still mostly work from existing pool state

## 4. Emergency stop

If you want to stop new trades immediately:

1. stop the scheduler process
   - `Ctrl + C` in the scheduler terminal
2. disable MT5 AutoTrading or close MT5

Without the scheduler and MT5 connection, no new automated orders will be sent.

## 5. Quick status snapshot

Use:

```powershell
python -m autonomous_trading_ai.scripts.print_live_summary
```

This is the fastest operator-facing snapshot for:

- daily equity / PnL
- strategy counts by status
- top active strategies
- live PnL summaries
- open-trade state when available

## 6. If routing feels too strict

Pass 3 intentionally makes the system more selective.

If the system is flat, that does **not** automatically mean it is broken.
The correct next question is:

- is the system skipping for a good reason?

Use:

- scheduler logs
- `debug_signals_for_latest_bar.py`
- `print_live_summary.py`

to distinguish:

- broken pipeline
- healthy but flat behavior

## 7. If state files look inconsistent

Important live-state artifacts to inspect:

- `execution/live_state.json`
- `execution/equity_history.json`
- `execution/closed_trades_state.json`
- `execution/strategy_live_stats.json`
- `execution/open_trades.json`
- `strategies/pool_state.json`

If something looks corrupted or clearly stale, stop the scheduler before doing
manual repair.

## 8. When everything feels wrong

Minimum safe sequence:

1. stop the scheduler
2. keep a copy of relevant logs and JSON state files
3. note the approximate time of the issue
4. inspect the latest commit and recent changes
5. restart only after the failure mode is understood

Safety rule:

> account safety and behavioral clarity matter more than keeping the bot active.

## Changelog (Docs)

- 2026-03-27: Rewrote the troubleshooting runbook to reflect pass 3 routing behavior, news lockout, expanded live-state files, and the distinction between “flat by design” vs “broken.”