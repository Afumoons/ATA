# RUNBOOK_TROUBLESHOOTING – autonomous_trading_ai

Quick troubleshooting notes when something feels off. This is meant for
Afu (user) and Clio (agent) as a fast checklist.

---

## 1. Tidak ada trade sama sekali

**Gejala:** Scheduler jalan, tapi tidak ada posisi baru di MT5.

Cek cepat:

1. MT5 benar-benar jalan dan login?
   - Buka MT5, pastikan:
     - koneksi hijau (bukan merah),
     - symbol `XAUUSDm` kelihatan dan bergerak.

2. Scheduler benar-benar running?
   - Di terminal, harus ada proses:
     - `python -m autonomous_trading_ai.scheduler.main`
   - Jika tidak, jalankan lagi dari workspace root (venv aktif).

3. Features tersedia?
   - Cek file di `autonomous_trading_ai/data/features/` untuk symbol/timeframe.
   - Kalau kosong:
     - jalankan manual: `job_update_data()` dari `scheduler.main`.

4. Pool punya strategi `active`?
   - Jalankan:
     ```powershell
     python -m autonomous_trading_ai.scripts.print_top_strategies --symbol XAUUSDm --timeframe M15 --status active --limit 5
     ```
   - Kalau tidak ada strategi `active`, wajar kalau tidak ada trade.
   - Jalankan `job_research_strategies()` dan lihat apakah ada strategi yang dipromote.

5. Daily lockout aktif?
   - Lihat `execution/live_state.json`:
     - `locked_for_day` bisa `true` kalau DD/trade cap tercapai.
   - Kalau `true`, sistem memang tidak akan buka trade baru sampai hari reset.

---

## 2. Strategi terasa "mati" padahal dulu aktif

Kemungkinan besar kena **degradasi berbasis live**:

1. Cek status di pool:
   ```powershell
   python -m autonomous_trading_ai.scripts.print_top_strategies --symbol XAUUSDm --timeframe M15 --status candidate --limit 10
   ```

2. Cek live stats:
   ```powershell
   python -m autonomous_trading_ai.scripts.print_live_summary
   ```

3. Lihat di output bagian:
   - "Worst 5 strategies by total live PnL"
   - Kalau strategi kamu ada di daftar ini dengan PnL recent yang buruk,
     itu artinya degradasi bekerja (di-demote ke `candidate`).

Kalau menurutmu strategi tersebut masih layak, kamu bisa:
- sementara set status manual via script custom,
- atau sesuaikan threshold degradasi di masa depan (via config khusus).

---

## 3. Job sering error di log

**Gejala:** Di `logs/system.log` banyak baris `ERROR` untuk job tertentu.

Langkah:

1. Buka `autonomous_trading_ai/logs/system.log`.
2. Cari kata kunci:
   - `job_update_data`, `job_research_strategies`, `job_execute_signals`, `job_live_monitor`.
3. Lihat trace pertama untuk setiap job:
   - Kalau error di MT5 (misal `account_info() returned None`):
     - MT5 belum login atau connection drop.
   - Kalau error di file I/O (FileNotFoundError):
     - biasanya fitur belum ada → jalankan `job_update_data()` dulu.

Jika error konsisten dan bukan masalah koneksi, catat:
- pesan error utama,
- dan konteks (job apa, symbol apa),
 lalu kita bisa bikin patch khusus.

---

## 4. Cara emergency stop

Kalau kamu ingin **langsung berhenti trading**:

1. Di terminal scheduler:
   - Tekan `Ctrl + C` untuk menghentikan `python -m ...scheduler.main`.
2. Di MT5:
   - Bisa matikan tombol AutoTrading (ikon hijau di toolbar), atau
   - Tutup MT5 sepenuhnya.

Sistem tidak akan mengirim order baru tanpa scheduler + MT5 aktif.

---

## 5. Cek cepat status sistem (script baru)

Gunakan:

```powershell
python -m autonomous_trading_ai.scripts.print_live_summary
```

Yang akan menampilkan:
- **Daily Account State**: equity start, equity current, daily PnL, trades_today, locked_for_day.
- **Strategy Pool**: jumlah strategi per status + top 5 `active` by score.
- **Per-Strategy Live PnL**: 5 strategi terburuk berdasarkan total live PnL
  (plus average PnL di rolling window terbaru).

Ini bisa dipakai Afu untuk "sekali lihat" sebelum sesi, dan dipakai Clio
sebagai sumber kebenaran ketika menjawab pertanyaan tentang kondisi sistem.

---

## 6. Kalau semuanya kacau

Kalau:
- banyak error di log,
- data/error sulit dimengerti,
- atau perilaku bot terasa tidak masuk akal,

langkah minimal:

1. Emergency stop (lihat bagian 4).
2. Catat:
   - waktu kejadian,
   - cuplikan `logs/system.log` sekitar error,
   - status file penting:
     - `execution/live_state.json`
     - `execution/strategy_live_stats.json`
     - `strategies/pool_state.json`
3. Simpan sebagai bahan analisis; kita bisa:
   - rollback ke commit sebelumnya,
   - atau bikin branch eksperimen untuk memperbaiki tanpa menyentuh main.

Ingat: **keselamatan akun dan kejelasan perilaku > aktivitas trading**.
Kalau ragu, lebih baik sistem berhenti dan kita bedah pelan-pelan.
