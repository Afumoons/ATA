# Setup Guide: Autonomous AI Trading Environment (For Future Clio / New Machines)

This document is for **future me** (Clio) and for migrations to new hardware or a VPS.
It explains how to recreate the full autonomous trading stack from scratch and
what behavioral guarantees the system provides.

Assumptions:
- Host OS: Windows (adjust paths/commands for Linux if needed).
- Workspace root: `C:\Users\afusi\.openclaw\workspace` (or equivalent on new host).
- MetaTrader 5 is supported on the host.

---

## 1. System Prerequisites

### 1.1. Install MetaTrader 5

1. Download MetaTrader 5 from your broker or from MetaQuotes.
2. Install it on the new machine.
3. Log into the **demo** account to use for the autonomous agent.
4. In **Market Watch**:
   - Enable the symbols you want to trade.
   - Current code expects:
     - `XAUUSDm`
     - `BTCUSDm`
   - If the broker uses different names, you’ll update `MANAGED_SYMBOLS` later.

### 1.2. Install Python + Git

1. Install **Python 3.13** (or a compatible 3.x version):
   - Ensure “Add Python to PATH” is enabled.
2. Install **Git** if this workspace will be cloned from a repo.

### 1.3. Install Docker (for Chroma)

1. Install Docker Desktop (Windows) or Docker on Linux.
2. Ensure `docker` CLI works from a terminal.

---

## 2. Workspace & Code

### 2.1. Create/Open workspace root

On the new machine, create (or clone) the workspace:

```powershell
cd C:\Users\<your-user>\
mkdir .openclaw\workspace
cd .openclaw\workspace
```

If migrating from Git, clone into this directory:

```powershell
git clone <your-repo-url> .
```

Ensure the `autonomous_trading_ai/` folder is present with all submodules.

### 2.2. Verify project structure

The `autonomous_trading_ai` directory should contain (non-exhaustive):

- `data/` (with `raw/`, `features/`)
- `strategies/` (with `generated/`, `pool_state.json`)
- `research/`
- `execution/`
- `risk/`
- `backtests/` (with `results/`)
- `vector_memory/`
- `scheduler/`
- `scripts/`
- `user_instructions/`
- `agent_instruction/` (this file)
- `config.py`, `logging_utils.py`, etc.

If any of these are missing, migration was incomplete.

---

## 3. Python Environment for autonomous_trading_ai

### 3.1. Create virtualenv

From the workspace root:

```powershell
cd C:\Users\<your-user>\.openclaw\workspace
cd autonomous_trading_ai
python -m venv .venv
```

### 3.2. Activate venv

PowerShell:

```powershell
cd C:\Users\<your-user>\.openclaw\workspace
.\autonomous_trading_ai\.venv\Scripts\Activate.ps1
```

You should see `(.venv)` in the prompt.

### 3.3. Install Python dependencies

Inside the activated venv:

```powershell
pip install --upgrade pip
pip install MetaTrader5 ccxt pandas numpy scikit-learn torch chromadb fastapi uvicorn apscheduler pyarrow
```

Notes:
- `pyarrow` is required for pandas parquet support.
- If torch wheel for your Python version isn’t available, use an appropriate version or install via `pip install torch --index-url https://download.pytorch.org/whl/cpu`.

---

## 4. Chroma Vector Database Setup

Chroma stores strategy research/performance summaries.

### 4.1. Choose data directory

Example:

- Host path: `C:\Users\<your-user>\.openclaw\workspace\chroma_data`

Create it if needed:

```powershell
mkdir C:\Users\<your-user>\.openclaw\workspace\chroma_data
```

### 4.2. Run Chroma via Docker

First-time run:

```powershell
cd C:\Users\<your-user>\.openclaw\workspace

docker run -d ^
  --name chroma ^
  -p 8000:8000 ^
  -v C:\Users\<your-user>\.openclaw\workspace\chroma_data:/chroma/chroma ^
  chromadb/chroma:latest ^
  chroma run --path /chroma/chroma --host 0.0.0.0 --port 8000
```

Subsequent starts:

```powershell
docker start chroma
```

No code change needed; `vector_memory/research_memory.py` uses a local on-disk
client, but this Docker setup is useful if you later switch to HTTP mode.

---

## 5. MT5 Bridge Setup (Optional)

The autonomous system uses `MetaTrader5` Python API directly, but the
`trading-bridge/bridge.py` service is useful for manual checks.

### 5.1. Install dependencies for trading-bridge

From workspace root:

```powershell
cd C:\Users\<your-user>\.openclaw\workspace\trading-bridge
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Typical requirements include `MetaTrader5`, `fastapi`, `uvicorn`, etc.

### 5.2. Run the bridge (optional)

```powershell
cd C:\Users\<your-user>\.openclaw\workspace\trading-bridge
.\.venv\Scripts\Activate.ps1
python bridge.py
```

This exposes a local FastAPI service talking to MT5; not mandatory for
the autonomous agent, but useful.

---

## 6. Wiring MT5 on a New Machine

**Important:** The Python `MetaTrader5` module talks to whatever MT5 terminal is
installed and logged in on that machine.

For `autonomous_trading_ai` to see MT5 data:

1. Launch **MetaTrader 5**.
2. Log into the desired demo account.
3. Confirm Market Watch shows your target symbols and they have ticks.
4. The `initialize_mt5()` function in `data/collector_mt5.py` will then connect to this terminal.

If multiple MT5 installations exist, ensure the default terminal used by
`MetaTrader5` Python module is the one you want.

---

## 7. Running the Autonomous Agent

### 7.1. Activate venv

```powershell
cd C:\Users\<your-user>\.openclaw\workspace
.\autonomous_trading_ai\.venv\Scripts\Activate.ps1
```

### 7.2. (Optional) One-shot research cycle

This is optional because the scheduler will run these jobs, but useful after a migration.

**Update data + features + regimes:**

```powershell
python -c "from autonomous_trading_ai.data.collector_mt5 import initialize_mt5, shutdown_mt5; from autonomous_trading_ai.scheduler.main import job_update_data; initialize_mt5(); job_update_data(); shutdown_mt5()"
```

**Research/evaluate/evolve strategies:**

```powershell
python -c "from autonomous_trading_ai.data.collector_mt5 import initialize_mt5, shutdown_mt5; from autonomous_trading_ai.scheduler.main import job_research_strategies; initialize_mt5(); job_research_strategies(); shutdown_mt5()"
```

### 7.3. Strategy selection, live-aware degradation & self-improvement

**Key behavior guarantee for future Clio:**

- Tidak ada lagi langkah manual wajib untuk "promote strategi" dalam operasi normal.
- Promosi dan degradasi dilakukan otomatis berdasarkan kombinasi:
  - backtest + explainability (`strategy_explain`), dan
  - performa live (rolling window per-strategy).

Secara garis besar:

1. Di setiap `job_research_strategies`:
   - Sistem:
     - Load features.
     - Evolusi populasi strategi.
     - Backtest + evaluate + walk-forward + Monte Carlo.
     - Bangun `strategy_explain` (regime/session/risk/stability/news).
     - Hitung skor dan tetapkan status awal pool:
       - `active`, `candidate`, atau `disabled`.

2. Setelah pool di-update dari sisi riset:
   - `_apply_live_degradation(pool)` dipanggil:
     - Load `execution/strategy_live_stats.json`:
       - per-strategy `total_pnl`, `num_trades`, dan `recent_pnls` (window ±30 trade).
     - Untuk setiap strategi `active` yang:
       - punya backtest decent (return > 0, Sharpe > threshold), dan
       - punya cukup banyak trade live,
       - hitung:
         - `live_ret_total_pct` vs `bt_ret`.
         - `live_ret_recent_pct` dari rolling window.
     - Jika `live_ret_recent_pct` jelas jelek (negatif/toxic vs backtest),
       → status otomatis di-demote ke `candidate`.

3. `job_live_monitor` memastikan `strategy_live_stats` terus di-update
   dari closed MT5 deals dengan membaca `deal.comment` (`clio-auto-{strategy_name}`).

Sebagai Clio di masa depan:
- Anggap pool sebagai entitas yang **auto-bersih**:
  - Backtest + explain → memasukkan kandidat bagus ke `active`.
  - Live degradation → menarik kembali strategi yang performanya drop.
- Tugas kita lebih ke:
  - men-tune threshold via config (kalau diperlukan nanti),
  - dan mendesain proses R&D (AI Level 2/3) untuk strategi yang
    menunjukkan anomali (mis. live jauh outperform backtest).

### 7.4. Start the scheduler loop

```powershell
python -m autonomous_trading_ai.scheduler.main
```

This will:

- Initialize MT5 connection once.
- Every 5 minutes:
  - Fetch OHLC → compute features → add `regime` → save features.
  - Generate + execute signals for **active** strategies.
  - Update live equity/drawdown and enforce basic safety.
- Every 30 minutes:
  - Evolve strategies.
  - Backtest + evaluate + walk-forward + Monte Carlo.
  - Update pool and store research in Chroma.
  - Apply live-performance degradation based on `strategy_live_stats`.

Leave this running while you want autonomous trading active.

---

## 8. Configuration Touchpoints

When migrating or changing brokers/markets, you may need to tweak:

- `scheduler/main.py`:
  - `MANAGED_SYMBOLS = [...]`
  - `TIMEFRAME = "M15"` (change timeframe if needed).
- `config.py`:
  - `RiskConfig` (risk per trade, max drawdown, max open positions).
  - `DataConfig` (default timeframe, history bars).
- `vector_memory/research_memory.py`:
  - `ResearchMemoryConfig` if you want a different Chroma path/collection or switch to HTTP client.

Remember to keep risk conservative when moving to real money.

---

## 9. Sanity Checks After Migration

Once everything is set up on a new host:

1. Run a **single test trade** using the manual script:

   ```powershell
   python -m autonomous_trading_ai.scripts.manual_execute_trade
   ```

   - Confirm MT5 shows the order.
   - Confirm `execution/trades.log` logs the trade.

2. Run `job_update_data` once via the wrapped command:

   ```powershell
   python -c "from autonomous_trading_ai.data.collector_mt5 import initialize_mt5, shutdown_mt5; from autonomous_trading_ai.scheduler.main import job_update_data; initialize_mt5(); job_update_data(); shutdown_mt5()"
   ```

   - Confirm `data/raw/` and `data/features/` contain new files for your symbols.

3. Start the scheduler and watch `logs/system.log` for 10–15 minutes:
   - You should see periodic `job_update_data`, `job_execute_signals`, and `job_live_monitor` entries.
   - Once strategies are active, you should see signals and trades flowing.

If any step fails, check:
- MT5 is running and logged in.
- venv is activated.
- Required Python packages are installed (`pip list`).
- Paths in commands match the actual locations on the new machine.
