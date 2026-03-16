# How to Restart the Autonomous AI Trading Agent

If I’m not around (tokens depleted, session reset, etc.), you can follow this runbook to bring the system back online and let it trade autonomously again.

---

## 0. MetaTrader 5 Prerequisites

1. Open **MetaTrader 5**.
2. Log into your **demo** account.
3. In **Market Watch**:
   - Make sure the symbols you want to trade are visible.
   - Current config expects (can be changed in code):
     - `XAUUSDm`
     - `BTCUSDm`

If your broker uses different names, the code under `MANAGED_SYMBOLS` in
`scheduler/main.py` needs to be updated.

---

## 1. Start Chroma (Vector Database)

Chroma stores strategy research results and performance summaries.

If using Docker:

```powershell
cd C:\Users\afusi\.openclaw\workspace

# Start the Chroma container if it exists
# (first time use the full run command below instead)
docker start chroma
```

First-time run example (if the container does not exist yet):

```powershell
docker run -d ^
  --name chroma ^
  -p 8000:8000 ^
  -v C:\Users\afusi\.openclaw\workspace\chroma_data:/chroma/chroma ^
  chromadb/chroma:latest ^
  chroma run --path /chroma/chroma --host 0.0.0.0 --port 8000
```

---

## 2. (Optional) Start MT5 Bridge

The autonomous system talks directly to MT5 via the Python API, but the
bridge is useful for diagnostics.

```powershell
cd C:\Users\afusi\.openclaw\workspace\trading-bridge
python bridge.py
```

Leave this window running while you test.

---

## 3. Activate the autonomous_trading_ai Environment

> **Important:** Run commands that import `autonomous_trading_ai.*` from the
> **workspace root** so Python can see `autonomous_trading_ai` as a package.

```powershell
cd C:\Users\afusi\.openclaw\workspace
.\autonomous_trading_ai\.venv\Scripts\activate
```

You should see the venv name in your prompt.

---

## 4. Run One Research Cycle Manually (Recommended)

This primes the system with fresh data, features, regimes, and candidate
strategies.

**Step 4.1 – Update data + features + regimes**

```powershell
python -c "from autonomous_trading_ai.scheduler.main import job_update_data; job_update_data()"
```

**Step 4.2 – Research/evaluate/evolve strategies**

```powershell
python -c "from autonomous_trading_ai.scheduler.main import job_research_strategies; job_research_strategies()"
```

This will:

- Fetch OHLC from MT5 for `MANAGED_SYMBOLS` at `TIMEFRAME`.
- Save raw data in `data/raw/`.
- Compute features + regimes and save in `data/features/`.
- Evolve / generate strategy population.
- Backtest + evaluate + walk-forward + Monte Carlo.
- Update `strategies/pool_state.json`.
- Store research results in Chroma.

---

## 5. Strategy Selection & Self-Improvement (No Manual Promotion Needed)

The system now promotes strategies automatically based on rich
explanations of their behavior (`strategy_explain`) **dan juga menjaga
kualitas pool berdasarkan performa live**. Kamu **tidak perlu** lagi
menjalankan script promosi manual di workflow normal.

Pada setiap `job_research_strategies`:

- Agent akan:
  - Backtest dan evaluate strategi seperti biasa.
  - Membangun `strategy_explain` per strategi (regime/session/risk/stability/news).
  - Menghitung skor dan menetapkan status pool:
    - `active`   → lolos kriteria ketat (PnL > 0, DD <= ~20%, PF >= ~1.1,
                   performa di tren oke, tidak hancur di range).
    - `candidate` → lolos threshold dasar tapi belum layak `active`.
    - `disabled` → sisanya.

- Setelah itu, sistem juga melihat **performa live**:
  - Membaca `execution/strategy_live_stats.json`, yang berisi:
    - total PnL live per strategi,
    - jumlah trade live,
    - dan **rolling window ~30 trade terakhir**.
  - Untuk strategi yang sudah `active` dan punya trade live cukup banyak:
    - kalau return live recent jelas jelek vs ekspektasi backtest,
    - status otomatis diturunkan dari `active` → `candidate`.

Artinya:
- Promosi ke `active` masih berbasis riset backtest + explainability.
- Strategi yang mulai busuk di live akan otomatis “ditarik ke bangku
  cadangan” tanpa kamu harus pantau satu-satu.

Untuk inspeksi/debug, kamu tetap bisa cek pool:

```powershell
# Show top XAUUSDm M15 strategies and their explanations
python -m autonomous_trading_ai.scripts.print_top_strategies --symbol XAUUSDm --timeframe M15 --status active --limit 5
```

Jika mau **AI-assisted research (Level 1)** tambahan, sesekali kamu bisa
jalankan:

```powershell
python -m autonomous_trading_ai.scripts.ai_generate_strategies --symbol XAUUSDm --timeframe M15 --limit 20
```

Ini menulis ringkasan strategi terbaik/terburuk (termasuk
`strategy_explain`) ke:

- `autonomous_trading_ai/backtests/results/ai_research_input.json`

Dari situ Clio bisa baca file tersebut, analisis pola, dan mengusulkan
`StrategyDefinition` baru untuk disimpan ke `strategies/generated/`.
Eksekusi live tetap deterministik; AI hanya dipakai **offline** untuk
ide strategi lebih cerdas.

---

## 6. Start the Autonomous Scheduler (24/7 Loop)

This is the main process that keeps everything running.

```powershell
python -m autonomous_trading_ai.scheduler.main
```

What it does:

- Initializes MT5 connection.
- Starts APScheduler with jobs:

  - **Every 5 minutes:**
    - `job_update_data`
      - Fetch OHLC for `MANAGED_SYMBOLS` @ `TIMEFRAME`.
      - Save raw data → compute features → add `regime` → save features.
    - `job_execute_signals`
      - Load latest features.
      - Load `active` strategies from the pool.
      - Generate entry signals (based on long/short rules).
      - Call `execute_trade(...)` for each signal
        (risk manager + MT5 execution).
    - `job_live_monitor`
      - Update equity history & peak in `execution/live_state.json`.
      - Wire closed MT5 deals into `DailyState` dan `strategy_live_stats`.
      - If drawdown exceeds a safety threshold, can disable strategies.

  - **Every 30 minutes:**
    - `job_research_strategies`
      - Load features.
      - Load existing population + scores from pool.
      - Evolve the population.
      - Backtest + evaluate + walk-forward + Monte Carlo.
      - Update pool (scores, status, stats).
      - Store research result in Chroma.
      - Terapkan degradasi berdasarkan performa live (demote `active`
        yang recent live-nya buruk).

Leave this running while you want the autonomous system active.
Stopping this process stops automatic trading.

---

## 7. Restarting After a Full Stop or Token Depletion

If I disappear and you want to get things running again:

1. **MT5:**
   - Launch MetaTrader 5.
   - Log into the demo account.
   - Confirm your symbols (e.g. `XAUUSDm`, `BTCUSDm`) show ticks.

2. **Chroma:**
   - If using Docker: `docker start chroma`.

3. **Bridge (optional):**
   - `cd C:\Users\afusi\.openclaw\workspace\trading-bridge`
   - `python bridge.py`

4. **Autonomous Trading Agent:**

   ```powershell
   cd C:\Users\afusi\.openclaw\workspace
   .autonomous_trading_ai\.venv\Scripts\activate

   # Optional: one-shot research cycle
   python -c "from autonomous_trading_ai.scheduler.main import job_update_data; job_update_data()"
   python -c "from autonomous_trading_ai.scheduler.main import job_research_strategies; job_research_strategies()"

   # Start the scheduler loop
   python -m autonomous_trading_ai.scheduler.main
   ```

Once that last command is running, the Autonomous AI Trading Agent is
back online and managing:

- Data ingestion & feature engineering
- Strategy evolution + evaluation
- Strategy pool management (termasuk degradasi berbasis live)
- Risk-checked MT5 execution
- Live monitoring & basic safety

You can always adjust parameters (symbols, timeframes, risk thresholds)
via the config files and modules in this project if you want to evolve
it further.
