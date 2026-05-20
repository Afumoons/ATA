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
     - negative-edge exploratory fallback being blocked instead of force-kept
     - concentration-aware runtime selection preferring a less clustered execution pool
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

If it was degraded, check per-strategy live PnL, recent performance windows, and whether the newer live decay logic emitted a warning/degrade signal in scheduler logs.

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

## 4. Telegram signal listener issues

`scheduler.main` autostarts the Telegram mentor-signal listener when `TELEGRAM_API_ID` and `TELEGRAM_API_HASH` are available in `.env` / environment.

Fast checks:

1. Confirm `.env` contains:

   ```text
   TELEGRAM_API_ID=...
   TELEGRAM_API_HASH=...
   TELEGRAM_SIGNAL_SESSION=ata_telegram_signals
   ```

2. Confirm autostart is not disabled:

   ```text
   ATA_TELEGRAM_SIGNAL_AUTOSTART=false
   ```

   If this exists, the listener intentionally will not start.

3. Check mode flags:

   ```text
   ATA_TELEGRAM_SIGNAL_MODE=shadow
   # live requires both:
   # ATA_TELEGRAM_SIGNAL_MODE=auto_live
   # ATA_TELEGRAM_SIGNAL_LIVE=true
   ```

4. Check audit files:

   ```text
   execution/external_signal_audit.jsonl
   execution/external_signal_execution.jsonl
   execution/external_signal_seen.json
   ```

5. For first-time Telegram login, run standalone once so Telethon can ask for login code / 2FA:

   ```powershell
   cd C:\laragon\www
   python -m autonomous_trading_ai.scripts.telegram_signal_listener --channel japsku --history 5 --mode shadow
   ```

Known limitation: no-TP signals are recorded as trailing-stop plans, but the background SL-modification loop is not implemented yet.

## 5. Emergency stop

If you want to stop new trades immediately:

1. stop the scheduler process
   - `Ctrl + C` in the scheduler terminal
2. disable MT5 AutoTrading or close MT5
3. for Telegram external-signal live mode, also remove/unset:

   ```text
   ATA_TELEGRAM_SIGNAL_LIVE=true
   ```

Without the scheduler and MT5 connection, no new automated orders will be sent.

## 6. Quick status snapshot

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

## 7. If routing feels too strict

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

## 8. If state files look inconsistent

Important live-state artifacts to inspect:

- `execution/live_state.json`
- `execution/equity_history.json`
- `execution/closed_trades_state.json`
- `execution/strategy_live_stats.json`
- `execution/open_trades.json`
- `execution/unmatched_closed_deals.json`
- `execution/pool_audit_trail.json`
- `strategies/pool_state.json`

If something looks corrupted or clearly stale, stop the scheduler before doing
manual repair.

## 9. When everything feels wrong

Minimum safe sequence:

1. stop the scheduler
2. keep a copy of relevant logs and JSON state files
3. note the approximate time of the issue
4. inspect the latest commit and recent changes
5. restart only after the failure mode is understood

Safety rule:

> account safety and behavioral clarity matter more than keeping the bot active.

## Changelog (Docs)

- 2026-05-20: Added Telegram signal listener troubleshooting, autostart/env checks, audit files, and live-mode emergency stop note.
- 2026-04-04: Updated troubleshooting guidance for live decay review signals and concentration-aware routing behavior.
- 2026-04-03: Added new Track B audit files to the troubleshooting checklist.

- 2026-03-27: Rewrote the troubleshooting runbook to reflect pass 3 routing behavior, news lockout, expanded live-state files, and the distinction between “flat by design” vs “broken.”