# How to Restart the Autonomous Trading Agent

Use this runbook to bring `autonomous_trading_ai` back online after a stop,
restart, or session loss.

## 0. Before You Start

Make sure:

1. **MT5 is open**
2. **MT5 is logged into the intended account**
3. target symbols are visible and ticking

Current symbols/timeframes should be verified in:

- `autonomous_trading_ai/scheduler/main.py`

## 1. Optional: Start Chroma / Research Memory Support

If your setup uses Docker-managed Chroma:

```powershell
cd C:\Users\afusi\.openclaw\workspace
docker start chroma
```

This supports research-memory workflows, but the live stack should not depend on
it for basic routing/execution from existing pool state.

## 2. Optional: Start Webhook Receiver For Alerts

If you want best-effort outbound alert logging:

```powershell
cd C:\Users\afusi\.openclaw\workspace\autonomous_trading_ai
uvicorn webhook_server:app --host 0.0.0.0 --port 8001
```

Optional environment variables:

```powershell
$env:OPENCLAW_WHATSAPP_WEBHOOK = "http://localhost:8001/hooks/whatsapp_outbound"
$env:WEBHOOK_TOKEN = "clio-autotrading-hooks"
$env:OPENCLAW_WHATSAPP_RECIPIENT = "628170090022"
```

This alert path is useful, but not required for the core trading loop.

## 3. Activate The Project Environment

From workspace root:

```powershell
cd C:\Users\afusi\.openclaw\workspace
.\autonomous_trading_ai\.venv\Scripts\activate
```

## 4. Recommended One-Time Refresh Before Full Start

### 4.1 Update data/features/regimes

```powershell
python -c "from autonomous_trading_ai.scheduler.main import job_update_data; job_update_data()"
```

### 4.2 Run one research cycle

```powershell
python -c "from autonomous_trading_ai.scheduler.main import job_research_strategies; job_research_strategies()"
```

This helps ensure the system starts from fresh feature data and current pool state.

If the pool was recently cleaned or metadata was repaired, this step is even
more important because it allows the upgraded research loop to start from a
consistent baseline.

## 5. Start The Main Scheduler

```powershell
python -m autonomous_trading_ai.scheduler.main
```

This starts the recurring loop for:

- market data refresh
- feature/regime updates
- research/evolution
- live routing and execution
- live monitoring
- news refresh and best-effort alerts

## 6. What To Expect After Pass 3

The system is now more selective than earlier versions.

That means it is normal for the system to skip trades because of:

- daily lockout
- news lockout
- blocked session
- blocked regime
- volatility mismatch
- low routing confidence
- no eligible specialist
- negative-edge exploratory fallback being blocked instead of force-kept
- concentration-aware selection reducing clustered runtime picks
- motif-aware selection reducing clustered runtime picks
- no entry trigger on eligible specialists

So:

- **low trade count does not automatically mean something is broken**
- the correct question is whether the skip reason is sensible

## 7. Optional Operator UI

If the operator UI stack is present, the current intended split is:

- backend UI API: `ui_api/`
- active frontend: `ui-front/` (Next.js)

Use the UI for observability and diagnosis, not for uncontrolled live execution.
The older `ui/` frontend should be treated as legacy/reference unless explicitly revived.

## 8. Quick Inspection Commands

### Show current system summary

```powershell
python -m autonomous_trading_ai.scripts.print_live_summary
```

### Show top active strategies

```powershell
python -m autonomous_trading_ai.scripts.print_top_strategies --symbol XAUUSDm --timeframe M15 --status active --limit 5
```

### Debug latest-bar routing/execution behavior

```powershell
python -m autonomous_trading_ai.scripts.debug_signals_for_latest_bar
```

Warning: that debug script can interact with real execution code.

## 9. Emergency Stop

To stop automated trading:

1. stop the scheduler terminal with `Ctrl + C`
2. disable MT5 AutoTrading or close MT5

## 10. If Something Looks Wrong

Check these files first:

- `autonomous_trading_ai/execution/live_state.json`
- `autonomous_trading_ai/execution/equity_history.json`
- `autonomous_trading_ai/execution/strategy_live_stats.json`
- `autonomous_trading_ai/execution/unmatched_closed_deals.json`
- `autonomous_trading_ai/execution/pool_audit_trail.json`
- scheduler logs for live decay warning/degrade decisions when strategies underperform recently
- `autonomous_trading_ai/strategies/pool_state.json`
- logs under `autonomous_trading_ai/logs/`

If in doubt, stop the scheduler first and inspect before restarting.

## 7.1 How To Run The Active Operator UI So It Actually Works

The active operator UI is split into two processes:

1. backend UI API (`ui_api/` via FastAPI)
2. frontend UI (`ui-front/` via Next.js)

The frontend expects `/api/*` to resolve to the backend UI API.
`ui-front/next.config.ts` now rewrites `/api/:path*` to `http://127.0.0.1:8000/api/:path*` by default.

### Start the backend UI API

From the `autonomous_trading_ai` repo root:

```powershell
cd C:\Users\afusi\.openclaw\workspace\autonomous_trading_ai
.\.venv\Scripts\activate
uvicorn ui_api.app:app --host 127.0.0.1 --port 8000
```

Quick check:

```powershell
Invoke-WebRequest http://127.0.0.1:8000/api/health
```

### Start the frontend UI

In a second terminal:

```powershell
cd C:\Users\afusi\.openclaw\workspace\autonomous_trading_ai\ui-front
npm run dev
```

Then open the frontend URL shown by Next.js.

### If the backend runs on a different host/port

Set `UI_API_ORIGIN` before starting the frontend:

```powershell
$env:UI_API_ORIGIN = "http://127.0.0.1:9000"
npm run dev
```

### If you still see API errors

Check in this order:

1. `http://127.0.0.1:8000/api/health` responds
2. the backend terminal has no FastAPI import/runtime errors
3. the frontend dev server was restarted after config changes
4. the frontend request path is `/api/...`, not a hardcoded old URL

## Changelog (Docs)

- 2026-04-09: Added explicit runbook for starting `ui_api` + `ui-front` together so the active operator UI works correctly.
- 2026-04-09: Added operator UI note and clarified that `ui-front` is the active frontend target.
- 2026-04-08: Updated start runbook for novelty/motif-aware runtime behavior and post-cleanup pool consistency.
- 2026-04-04: Updated start runbook for concentration-aware runtime selection and live decay review signals.
- 2026-04-03: Expanded troubleshooting file references to include unmatched closed-deal and pool-audit artifacts.

- 2026-03-27: Rewrote the user start runbook for the pass 3 system, including routing-aware expectations, optional alert startup, and updated quick-check commands.