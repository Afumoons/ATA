# Telegram Signal Hook

Purpose: read external Telegram mentor signals from `https://t.me/japsku`, parse changing XAUUSD buy/sell formats, and produce an auditable trade plan. The default startup path is shadow mode; live mode exists but requires an explicit environment kill-switch to be enabled.

## Current Afu Rules

- Symbol: canonical `XAUUSD` only; broker suffix resolution happens inside ATA execution (`XAUUSDm`, etc.).
- Direction: detect `buy/long` or `sell/short`.
- Risk: `1%` per trade.
- SL:
  - Use explicit SL when present.
  - If missing, default to `500 pips` = `5.00` XAU price units (`pip_size=0.01`).
  - If a signal says `BUY 4500` and no SL, planned SL is `4495`.
  - If execution fills worse, the invalidation SL remains based on the signal/default reference, not widened just because spread/slippage is bad.
  - Position size is reduced/increased from the actual fill-to-SL distance to keep risk near 1%.
- TP:
  - If TP exists, full-close at TP1.
  - If TP is missing, plan `trailing_stop` with `500 pips` distance.
- Do not skip solely on parser confidence.
- No max-exposure gate at this parser layer.
- No spread/slippage skip at this parser layer.

## Implemented Components

- `execution/external_signal.py` — side-effect-free parser and trade planner.
- `execution/external_signal_executor.py` — duplicate store, live guard, and MT5 absolute-SL order bridge.
- `scripts/telegram_signal_listener.py` — Telethon listener for Telegram public channel/user-session mode.
- `tests/test_external_signal.py` — parser tests.
- `tests/test_external_signal_executor.py` — duplicate/live-guard/absolute-SL sizing tests.

## Safety State

Code default is **shadow**; current demo deployment is intentionally armed via `.env` with `ATA_TELEGRAM_SIGNAL_MODE=auto_live` and `ATA_TELEGRAM_SIGNAL_LIVE=true`.

Shadow mode:

- reads Telegram messages
- parses into `ExternalTradePlan`
- appends JSONL parser audit rows
- appends JSONL execution-decision audit rows
- does not send broker orders

Live mode requires both:

1. CLI/env mode: `auto_live`
2. Environment flag: `$env:ATA_TELEGRAM_SIGNAL_LIVE="true"`

If either is missing, orders are blocked. Live external-signal orders use MT5 comments beginning with `TELEGRAM` so they are visually distinct from native ATA strategy orders.

## One-time Telegram Setup

Install Telethon if needed:

```powershell
cd C:\laragon\www
python -m pip install telethon
```

Create Telegram API credentials:

1. Open <https://my.telegram.org/apps>
2. Login with Afu's Telegram number.
3. Create an app.
4. Copy `api_id` and `api_hash`.

Set env vars in the PowerShell session that will run the listener, or put them in `C:\\laragon\\www\\autonomous_trading_ai\\.env`:

```powershell
$env:TELEGRAM_API_ID="YOUR_API_ID"
$env:TELEGRAM_API_HASH="YOUR_API_HASH"
$env:TELEGRAM_SIGNAL_SESSION="ata_telegram_signals"
```

Optional `.env` knobs for scheduler autostart:

```text
ATA_TELEGRAM_SIGNAL_AUTOSTART=true
ATA_TELEGRAM_SIGNAL_CHANNEL=japsku
ATA_TELEGRAM_SIGNAL_MODE=auto_live
ATA_TELEGRAM_SIGNAL_HISTORY=0
# Only for live orders:
ATA_TELEGRAM_SIGNAL_LIVE=true
```

First run will ask for Telegram login code / 2FA password if needed. Telethon stores a local session file so later runs can reconnect.

## Start with scheduler.main

Because `scheduler.main` now autostarts the Telegram listener when Telegram credentials exist, this is enough:

```powershell
cd C:\\laragon\\www
python -m autonomous_trading_ai.scheduler.main
```

Defaults:

- autostart enabled if `TELEGRAM_API_ID` and `TELEGRAM_API_HASH` are present
- channel `japsku`
- mode follows `.env`; current demo setup uses `auto_live`
- no history replay unless `ATA_TELEGRAM_SIGNAL_HISTORY` is set

To disable autostart:

```text
ATA_TELEGRAM_SIGNAL_AUTOSTART=false
```

## Start Standalone Shadow Mode

From package parent directory:

```powershell
cd C:\laragon\www
python -m autonomous_trading_ai.scripts.telegram_signal_listener --channel japsku --history 20 --mode shadow
```

What this does:

- Parses the last 20 messages first.
- Then keeps listening realtime.
- No live orders are sent.

Audit files:

```text
C:\laragon\www\autonomous_trading_ai\execution\external_signal_audit.jsonl
C:\laragon\www\autonomous_trading_ai\execution\external_signal_execution.jsonl
C:\laragon\www\autonomous_trading_ai\execution\external_signal_seen.json
```

## Arm Auto-live Mode

Only after shadow output looks correct:

```powershell
cd C:\laragon\www
$env:TELEGRAM_API_ID="YOUR_API_ID"
$env:TELEGRAM_API_HASH="YOUR_API_HASH"
$env:TELEGRAM_SIGNAL_SESSION="ata_telegram_signals"
$env:ATA_TELEGRAM_SIGNAL_LIVE="true"
python -m autonomous_trading_ai.scripts.telegram_signal_listener --channel japsku --mode auto_live
```

To disarm immediately, stop the process or unset the flag in the next shell:

```powershell
Remove-Item Env:\ATA_TELEGRAM_SIGNAL_LIVE
```

## Known Remaining Gap

Trailing-stop management for no-TP signals is planned in the trade plan and recorded in order metadata, but a background SL modification loop is not implemented yet. Until that loop exists, auto-live no-TP signals can open with SL but will not automatically trail unless the broker/terminal manages it separately.
