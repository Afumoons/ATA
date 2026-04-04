# Setup Guide: Autonomous Trading Environment

This guide is for future Clio, a new machine, or a migration/rebuild of the
`autonomous_trading_ai` stack.

It explains how to recreate the environment safely and what to verify before
trusting the system.

## Assumptions

- Host OS: Windows
- Workspace root: `C:\Users\afusi\.openclaw\workspace`
- Project path: `C:\Users\afusi\.openclaw\workspace\autonomous_trading_ai`
- MT5 is the live data/execution backend

## 1. System Prerequisites

### 1.1 MetaTrader 5

1. Install MT5.
2. Log into the intended account.
3. Ensure target symbols are visible in Market Watch.
4. Confirm symbols are ticking before testing Python connectivity.

Current expected symbols may include:

- `XAUUSDm`
- `BTCUSDm`
- broker variants / canonical aliases such as `XAUUSD`, `XAUUSDc`, `XAGUSD`, `XAGUSDc`

Actual live configuration should be verified in `scheduler/main.py` and symbol canonicalization in `config.py`.

### 1.2 Python + Git

Install:

- Python 3.x compatible with the project environment
- Git

### 1.3 Optional Docker for Chroma workflows

Install Docker Desktop if you want a Docker-managed Chroma service or related tooling.

## 2. Workspace / Code Layout

Ensure the project exists under the workspace and includes at least:

- `data/`
- `research/`
- `strategies/`
- `backtests/`
- `execution/`
- `risk/`
- `scheduler/`
- `scripts/`
- `vector_memory/`
- `notifications/`
- `docs/`
- `user_instructions/`
- `agent_instructions/`
- `config.py`
- `README.md`
- `webhook_server.py`

## 3. Python Environment

From workspace root:

```powershell
cd C:\Users\afusi\.openclaw\workspace\autonomous_trading_ai
python -m venv .venv
```

Activate:

```powershell
cd C:\Users\afusi\.openclaw\workspace
.\autonomous_trading_ai\.venv\Scripts\Activate.ps1
```

Install required packages appropriate for the current project state, for example:

```powershell
pip install --upgrade pip
pip install MetaTrader5 ccxt pandas numpy scikit-learn torch chromadb fastapi uvicorn apscheduler pyarrow requests beautifulsoup4 pytest
```

Adjust only if the actual project dependencies have changed.

## 4. Chroma / Research Memory

The project uses Chroma-backed research memory, typically with local persistent
storage under the workspace.

Common path:

- `C:\Users\afusi\.openclaw\workspace\chroma_data`

You may use local persistent mode directly or optional Docker-based workflows.

If using Docker, start/maintain a Chroma container as needed, but remember:

- `vector_memory/research_memory.py` is the real source of truth for how the
  code currently connects to research memory

## 5. Optional Webhook Receiver

If you want best-effort outbound alert logging / webhook handoff:

```powershell
cd C:\Users\afusi\.openclaw\workspace\autonomous_trading_ai
uvicorn webhook_server:app --host 0.0.0.0 --port 8001
```

Then set environment variables as needed, for example:

```powershell
$env:OPENCLAW_WHATSAPP_WEBHOOK = "http://localhost:8001/hooks/whatsapp_outbound"
$env:WEBHOOK_TOKEN = "clio-autotrading-hooks"
$env:OPENCLAW_WHATSAPP_RECIPIENT = "628170090022"
```

Remember: this path is **best-effort**, not a critical dependency for the core loop.

## 6. MT5 Connectivity Sanity Check

Before trusting the system:

1. open MT5
2. log in
3. confirm target symbols are visible and updating
4. only then test Python-side MT5 access

The `MetaTrader5` Python package talks to the local installed/logged-in terminal.

## 7. One-Shot Validation Steps

### 7.1 Update data

From workspace root with venv active:

```powershell
python -c "from autonomous_trading_ai.scheduler.main import job_update_data; job_update_data()"
```

Verify:

- raw parquet files appear in `data/raw/`
- feature parquet files appear in `data/features/`

### 7.2 Run research once

```powershell
python -c "from autonomous_trading_ai.scheduler.main import job_research_strategies; job_research_strategies()"
```

Verify:

- pool updates occur
- `strategies/pool_state.json` exists and looks sane
- research results can be persisted to memory if configured

### 7.3 Inspect live summary

```powershell
python -m autonomous_trading_ai.scripts.print_live_summary
```

This helps confirm the project can read its core state surfaces.

## 8. Start the Scheduler

Main runtime command:

```powershell
python -m autonomous_trading_ai.scheduler.main
```

This drives:

- data refresh
- research loop
- live execution
- live monitoring
- news refresh and alerts

## 9. Pass 3 Behavioral Expectations

After pass 3 and the latest post-audit hardening, expect the system to behave more selectively.

That means:

- fewer trades can be normal
- “no eligible specialist” can be a healthy outcome
- session/regime/confidence gating may block many otherwise plausible trades
- negative-edge exploratory fallback is intentionally blocked rather than force-kept
- concentration-aware manifest/runtime selection may reduce clustered picks
- `active` and `exploratory` are both live tiers, but with different trust/risk levels
- circuit-breaker, degradation, and live-decay behavior are intentional governance features

Do not assume low activity automatically means misconfiguration.

## 10. Important Files To Inspect During Setup

Useful runtime/state files include:

- `strategies/pool_state.json`
- `execution/live_state.json`
- `execution/equity_history.json`
- `execution/strategy_live_stats.json`
- `execution/open_trades.json`
- `execution/ticket_strategy_map.json`
- `data/raw/news_events.parquet`

## 11. Migration Safety Notes

On a new machine:

- keep risk conservative
- verify MT5 symbol names
- verify the project venv is the one actually being used
- confirm file paths are valid
- do not assume Docker/Chroma/webhook pieces are required for the core loop to function

## Changelog (Docs)

- 2026-04-04: Updated setup guidance for current dependency reality (`pytest`) and newer live-routing/live-decay behavior.
- 2026-04-03: Updated setup notes to reflect canonical symbol aliasing expectations (including XAG variants).

- 2026-03-27: Rewrote the setup guide for the current pass 3 architecture, added environment/webhook notes, and updated validation steps around routing-aware behavior.