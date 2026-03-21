# How to Restart the Autonomous AI Trading Agent

If I’m not around (tokens depleted, session reset, etc.), you can follow this runbook to bring the system back online and let it trade autonomously again.

---

## 0. MetaTrader 5 Prerequisites

1. Open **MetaTrader 5**.
2. Log into your **demo** account.
3. In **Market Watch**:
   - Make sure the symbols you want to trade are visible.
   - Current config expects (can be changed in code):
     - `XAUUSDm`  (default MANAGED_SYMBOLS)
     - (Optional) `BTCUSDm` if you add it back into `MANAGED_SYMBOLS`.

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

## 3. (Optional) Start the WhatsApp Webhook Receiver

The notifications module sends WhatsApp-style alerts (news, strategy
.degradation, circuit breaker) via an HTTP webhook. A small FastAPI app
`webhook_server.py` is included as the receiver.

1. Open a new terminal.
2. Activate the same Python environment used for `autonomous_trading_ai` (or
   another env with FastAPI/Uvicorn installed).
3. Run:

```powershell
cd C:\Users\afusi\.openclaw\workspace\autonomous_trading_ai
uvicorn webhook_server:app --host 0.0.0.0 --port 8001
```

4. In your shell / OpenClaw environment, set:

```powershell
$env:OPENCLAW_WHATSAPP_WEBHOOK = "http://localhost:8001/hooks/whatsapp_outbound"
# Token defaults to "clio-autotrading-hooks"; override if you change it in webhook_server.py
# $env:WEBHOOK_TOKEN = "clio-autotrading-hooks"
# Recipient defaults to Afu's number; override if needed:
# $env:OPENCLAW_WHATSAPP_RECIPIENT = "62817xxxxxxx"
```

This path is **experimental** — messages are delivered to the FastAPI app and
logged; wiring into the OpenClaw gateway/WhatsApp is a separate step.

---

## 4. Activate the autonomous_trading_ai Environment

> **Important:** Run commands that import `autonomous_trading_ai.*` from the
> **workspace root** so Python can see `autonomous_trading_ai` as a package.

```powershell
cd C:\Users\afusi\.openclaw\workspace
.\autonomous_trading_ai\.venv\Scripts\activate
```

You should see the venv name in your prompt.

---

## 5. Run One Research Cycle Manually (Recommended)

This primes the system with fresh data, features, regimes, candidate
strategies, and news context.

### 5.1 – Update data + features + regimes

```powershell
python -c "from autonomous_trading_ai.scheduler.main import job_update_data; job_update_data()"
```

### 5.2 – Research/evaluate/evolve strategies

```powershell
python -c "from autonomous_trading_ai.scheduler.main import job_research_strategies; job_research_strategies()"
```

This will:

- Fetch OHLC from MT5 for `MANAGED_SYMBOLS` at `TIMEFRAME`.
- Save raw data in `data/raw/`.
- Compute features + regimes and save in `data/features/`.
- Join macro news context (if `data/raw/news_events.parquet` is available).
- Evolve / generate strategy population.
- Backtest + evaluate + walk-forward + Monte Carlo.
- Update `strategies/pool_state.json`.
- Store research results in Chroma.

(News calendar data itself is fetched by the scheduler jobs described later
— you don’t need to run `news_collector` manually.)

---

## 6. Strategy Selection & Self-Improvement (No Manual Promotion Needed)

The system now promotes strategies automatically based on:

- rich explanations of behaviour (`strategy_explain`),
- a **Chroma-backed research memory** of past strategies,
- and **live performance** (rolling per-strategy PnL).

Kamu **tidak perlu** lagi menjalankan script promosi manual di workflow normal.

Pada setiap `job_research_strategies`:

- Agent akan:
  - Backtest dan evaluate strategi seperti biasa.
  - Membangun `strategy_explain` per strategi (regime/session/risk/stability/news).
  - Menghitung skor dasar lalu memberi **bonus/penalty kecil** berdasarkan
    kemiripan dengan strategi-strategi yang sudah pernah diteliti sebelumnya
    di `vector_memory/ResearchMemory` untuk simbol/timeframe yang sama.
  - Menetapkan status pool:
    - `active`      → lolos kriteria ketat (PnL > 0, DD <= ~20%, PF >= ~1.1,
                      performa di tren oke, tidak hancur di range, WF & MC
                      sehat).
    - `exploratory` → strategi yang diterima tapi masih tier percobaan (risk
                      lebih kecil, dipakai untuk kumpulkan data live).
    - `candidate`   → lolos threshold dasar tapi belum layak `exploratory`/`active`.
    - `disabled`    → sisanya.
  - Menyimpan hasil evaluasi ke Chroma sebagai memori riset.

- Setelah itu, sistem juga melihat **performa live**:
  - Membaca `execution/strategy_live_stats.json`, yang berisi:
    - total PnL live per strategi,
    - jumlah trade live,
    - dan **rolling window ~N trade terakhir**.
  - Untuk strategi yang sudah `active` dan punya trade live cukup banyak:
    - kalau return live recent jelas jelek vs ekspektasi backtest,
    - status otomatis diturunkan dari `active` → `candidate`.
  - Setiap degradasi ini memicu WhatsApp alert via
    `send_strategy_degradation_alert(...)` (lewat webhook).

Di sisi eksekusi signal:

- Hanya strategi dengan status `active` dan `exploratory` yang dipertimbangkan.
- Untuk setiap simbol/timeframe, sistem melihat **regime sekarang** dari fitur,
  lalu membaca `strategy_explain.regime_pnl`:
  - `active` hanya trade di regime yang historically **profit** (edge > 0).
  - `exploratory` boleh trade di regime yang sedikit negatif untuk kumpulkan
    data, tapi dengan **risk per trade jauh lebih kecil**.
- Sebelum membuka trade baru, sistem cek **batas harian** via
  `risk_config.max_daily_drawdown_pct` dan `risk_config.max_trades_per_day`:
  - Jika drawdown hari ini melebihi ~3% atau jumlah trade harian lewat batas,
    maka `can_open_new_trade(...)` akan blokir entry baru sampai hari berganti.

Artinya:
- Promosi ke `active` berbasis kombinasi riset (backtest + explain + memory).
- Strategi yang mulai busuk di live akan otomatis “ditarik ke bangku cadangan”.
- Exploratory dipakai sebagai lapisan eksperimen ber-risk kecil untuk mengenal
  behaviour di regime yang lebih luas tanpa membahayakan akun.

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

## 7. News, Lockout & WhatsApp Alerts (Optional but Recommended)

Dengan modul news & notifications, sistem bisa:

- Tarik kalender macro dari **Forex Factory**.
- Tandai bar fitur yang dekat event high-impact (lockout window).
- Kirim WhatsApp alert kalau ada event penting yang akan datang.

Scheduler otomatis mengurus hal ini:

- `job_update_news` (harian, 06:00 UTC)
  - Mengambil kalender FF minggu ini & depan.
  - Menyimpan ke `data/raw/news_events.parquet`.
  - Mengirim rangkuman event high-impact yang gold-relevant (via WhatsApp) kalau ada.

- `job_news_alert` (tiap 5 menit)
  - Cek apakah ada event high-impact dalam ~60 menit ke depan.
  - Kalau ada dan belum pernah di-alert dalam 60 menit terakhir, kirim alert pendek.

Di jalur eksekusi live:

- `job_execute_signals` akan skip totally eksekusi kalau feature terakhir punya
  `in_news_lockout = True` (±15 menit sekitar event high-impact). Jadi sistem
  **tidak buka posisi baru** pas news besar.

Kalau webhook FastAPI sedang jalan dan env var sudah di-set, kamu akan lihat
pesan seperti:

- “Upcoming High-Impact Events (Gold-Relevant)”
- “Strategy Degraded: <nama>”

Kalau belum siap menghubungkan ke WhatsApp, kamu masih bisa pakai
`webhook_server.py` sebagai **logger** saja.

---

## 8. Start the Autonomous Scheduler (24/7 Loop)

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
      - Save raw data → compute features (termasuk news) → add `regime` → save features.
    - `job_execute_signals`
      - Load latest features.
      - Apply news lockout (`in_news_lockout`).
      - Load `active` & `exploratory` strategies from the pool.
      - Generate entry signals (based on long/short rules + regime edge).
      - Check daily limits (DD & trade count) via `can_open_new_trade(...)`.
      - Call `execute_trade(...)` untuk setiap signal yang lolos
        (risk manager + MT5 execution).
    - `job_live_monitor`
      - Update equity history & peak di `execution/equity_history.json`.
      - Wire closed MT5 deals into `DailyState` dan `strategy_live_stats`.
      - Kalau drawdown dari peak lewat limit (`risk_config.max_portfolio_drawdown_pct`, default ~20%),
        disable semua strategi `active` (circuit breaker).

  - **Every 30 minutes:**
    - `job_research_strategies`
      - Load features.
      - Load existing population + scores from pool.
      - Evolve the population.
      - Backtest + evaluate + walk-forward + Monte Carlo.
      - Update pool (scores, status, stats).
      - Store research result in Chroma.
      - Terapkan degradasi berdasarkan performa live (demote `active`
        yang recent live-nya buruk, kirim WhatsApp alert).

  - **News jobs:**
    - `job_update_news` (daily 06:00 UTC) → refresh FF calendar + kirim summary.
    - `job_news_alert` (tiap 5 menit) → alert kalau ada event besar sebentar lagi.

Leave this running while you want the autonomous system active.
Stopping this process stops automatic trading.

---

## 9. Restarting After a Full Stop or Token Depletion

If I disappear and you want to get things running again:

1. **MT5:**
   - Launch MetaTrader 5.
   - Log into the demo account.
   - Confirm your symbols (e.g. `XAUUSDm`) show ticks.

2. **Chroma:**
   - If using Docker: `docker start chroma`.

3. **Webhook (optional):**
   - `cd C:\Users\afusi\.openclaw\workspace\autonomous_trading_ai`
   - `uvicorn webhook_server:app --host 0.0.0.0 --port 8001`

4. **Bridge (optional):**
   - `cd C:\Users\afusi\.openclaw\workspace\trading-bridge`
   - `python bridge.py`

5. **Autonomous Trading Agent:**

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

- Data ingestion & feature engineering (plus news context)
- Strategy evolution + evaluation + memory-aware guidance
- Strategy pool management (termasuk degradasi berbasis live)
- Risk-checked MT5 execution + daily guardrails
- Live monitoring, circuit breaker & basic safety
- (Optional) News & degradation alerts via the WhatsApp webhook

You can always adjust parameters (symbols, timeframes, risk thresholds)
via the config files and modules in this project if you want to evolve
it further.

---

## Changelog (Docs)

- 2026-03-21: Updated for single-symbol default (`XAUUSDm`), news calendar &
  lockout integration, daily risk guardrails now enabled by default, WhatsApp
  webhook path via `webhook_server.py`, and circuit-breaker behaviour.
