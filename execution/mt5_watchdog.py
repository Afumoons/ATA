from __future__ import annotations
 
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional
 
try:
    from ..logging_utils import get_logger
except ImportError:
    from logging_utils import get_logger
 
logger = get_logger(__name__)
 
# ── Thresholds ──────────────────────────────────────────────────────────────
_FAILURES_BEFORE_ALERT = 3       # consecutive failures sebelum WhatsApp dikirim
_ALERT_COOLDOWN_SEC = 300        # 5 menit antara alert agar tidak spam
_MAX_SILENCE_SEC = 600           # 10 menit tanpa success = anggap unhealthy
_RECOVERY_ALERT_MIN_DOWN_SEC = 60  # minimal down berapa detik sebelum kirim recovery alert
 
 
@dataclass
class _MT5HealthState:
    """Internal state — jangan akses langsung, gunakan MT5Watchdog methods."""
    consecutive_failures: int = 0
    last_success_ts: Optional[float] = None
    last_failure_ts: Optional[float] = None
    last_alert_ts: Optional[float] = None
    last_recovery_alert_ts: Optional[float] = None
    is_connected: bool = False
    failure_reason: str = ""
    total_reconnect_attempts: int = 0
    total_reconnect_success: int = 0
    # Track kapan koneksi pertama kali hilang untuk hitung downtime
    connection_lost_ts: Optional[float] = None
 
 
class MT5Watchdog:
    """Thread-safe singleton untuk monitor MT5 connection health.
 
    Usage pattern di setiap scheduler job:
 
        def job_execute_signals():
            if not mt5_watchdog.check_and_record():
                logger.warning("Skipping: MT5 unhealthy")
                return
            # ... rest of job
    """
 
    def __init__(self) -> None:
        self._state = _MT5HealthState()
        self._lock = threading.Lock()
 
    # ── Public API ──────────────────────────────────────────────────────────
 
    def check_and_record(self) -> bool:
        """Lakukan health check MT5, record hasilnya, return True jika healthy.
 
        Ini adalah satu-satunya method yang perlu dipanggil di job functions.
        Di dalamnya sudah handle: record result, reconnect, dan alert.
 
        Returns:
            True  → MT5 healthy, aman untuk lanjut
            False → MT5 tidak healthy, job harus skip
        """
        try:
            import MetaTrader5 as mt5
 
            # Quick check: account_info() adalah cara paling reliable
            # untuk verifikasi koneksi dan login status sekaligus
            info = mt5.account_info()
 
            if info is None:
                err = mt5.last_error()
                reason = f"account_info=None last_error={err}"
                self._record_failure(reason)
                return False
 
            # Tambahan check: pastikan terminal connected (bukan hanya initialized)
            terminal = mt5.terminal_info()
            if terminal is not None and not bool(getattr(terminal, "connected", True)):
                reason = "terminal.connected=False (internet/broker disconnected)"
                self._record_failure(reason)
                return False
 
            self._record_success()
            return True
 
        except ImportError:
            logger.error("MT5Watchdog: MetaTrader5 module not available")
            self._record_failure("MetaTrader5 not importable")
            return False
        except Exception as e:
            self._record_failure(f"exception:{type(e).__name__}:{e}")
            return False
 
    def is_healthy(self) -> bool:
        """Non-blocking query apakah MT5 dianggap healthy.
 
        Tidak melakukan actual check — hanya baca state terakhir.
        Gunakan check_and_record() untuk melakukan check aktif.
        """
        with self._lock:
            s = self._state
            if not s.is_connected:
                return False
            if s.consecutive_failures >= _FAILURES_BEFORE_ALERT:
                return False
            if s.last_success_ts is not None:
                silence_sec = time.time() - s.last_success_ts
                if silence_sec > _MAX_SILENCE_SEC:
                    return False
            return True
 
    def get_status_summary(self) -> dict:
        """Return dict berisi status untuk logging dan diagnostics."""
        with self._lock:
            s = self._state
            now = time.time()
            last_success_min_ago = None
            if s.last_success_ts:
                last_success_min_ago = round((now - s.last_success_ts) / 60.0, 1)
            downtime_sec = None
            if s.connection_lost_ts and not s.is_connected:
                downtime_sec = round(now - s.connection_lost_ts, 0)
            return {
                "is_connected": s.is_connected,
                "is_healthy": self.is_healthy(),
                "consecutive_failures": s.consecutive_failures,
                "last_success_min_ago": last_success_min_ago,
                "downtime_sec": downtime_sec,
                "failure_reason": s.failure_reason,
                "total_reconnect_attempts": s.total_reconnect_attempts,
                "total_reconnect_success": s.total_reconnect_success,
            }
 
    # ── Internal helpers ────────────────────────────────────────────────────
 
    def _record_success(self) -> None:
        now = time.time()
        was_down = False
        downtime_sec = 0.0
 
        with self._lock:
            s = self._state
            # Deteksi recovery dari downtime
            if not s.is_connected and s.connection_lost_ts is not None:
                was_down = True
                downtime_sec = now - s.connection_lost_ts
 
            s.consecutive_failures = 0
            s.last_success_ts = now
            s.is_connected = True
            s.failure_reason = ""
            s.connection_lost_ts = None  # reset downtime tracker
 
        if was_down and downtime_sec >= _RECOVERY_ALERT_MIN_DOWN_SEC:
            self._send_recovery_alert(downtime_sec)
 
    def _record_failure(self, reason: str) -> None:
        now = time.time()
        should_reconnect = False
        should_alert = False
        current_failures = 0
 
        with self._lock:
            s = self._state
            s.consecutive_failures += 1
            s.last_failure_ts = now
            s.failure_reason = reason
 
            # Track kapan koneksi pertama kali hilang
            if s.is_connected:
                s.connection_lost_ts = now
            s.is_connected = False
 
            current_failures = s.consecutive_failures
 
            # Trigger reconnect setiap kali ada failure
            should_reconnect = True
 
            # Alert dengan cooldown agar tidak spam
            alert_cooldown_ok = (
                s.last_alert_ts is None
                or (now - s.last_alert_ts) > _ALERT_COOLDOWN_SEC
            )
            should_alert = (
                current_failures >= _FAILURES_BEFORE_ALERT
                and alert_cooldown_ok
            )
            if should_alert:
                s.last_alert_ts = now
 
        logger.warning(
            "MT5Watchdog: failure recorded (consecutive=%d reason=%s)",
            current_failures,
            reason,
        )
 
        # Lakukan reconnect dan alert di luar lock agar tidak block caller
        if should_reconnect:
            self._attempt_reconnect()
 
        if should_alert:
            self._send_connection_lost_alert(reason, current_failures)
 
    def _attempt_reconnect(self) -> None:
        """Coba reinitialize MT5. Dipanggil setelah setiap failure."""
        try:
            import MetaTrader5 as mt5
 
            with self._lock:
                self._state.total_reconnect_attempts += 1
 
            logger.info("MT5Watchdog: attempting reconnect (mt5.initialize)...")
            result = mt5.initialize()
 
            if result:
                with self._lock:
                    s = self._state
                    s.total_reconnect_success += 1
                    # Jangan langsung set is_connected=True di sini —
                    # biarkan check_and_record() yang verifikasi.
                logger.info("MT5Watchdog: mt5.initialize() returned True — will verify on next check")
            else:
                err = mt5.last_error()
                logger.warning(
                    "MT5Watchdog: reconnect failed — mt5.initialize()=False last_error=%s",
                    err,
                )
        except Exception as e:
            logger.exception("MT5Watchdog: reconnect exception: %s", e)
 
    def _send_connection_lost_alert(self, reason: str, failures: int) -> None:
        """Kirim WhatsApp alert untuk MT5 connection loss."""
        try:
            from ..notifications.whatsapp_notifier import send_whatsapp_alert
            now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
 
            message = (
                "🚨 *MT5 CONNECTION LOST*\n\n"
                f"🕐 {now_str}\n"
                f"❌ Consecutive failures: {failures}\n"
                f"📋 Reason: {reason or 'unknown'}\n\n"
                "⚠️ *Dampak:*\n"
                "• Trading DIHENTIKAN otomatis\n"
                "• Open positions TIDAK dimonitor\n"
                "• Circuit breaker TIDAK aktif\n"
                "• Exit rules TIDAK dievaluasi\n\n"
                "🔄 Auto-reconnect sedang dicoba setiap cycle.\n\n"
                "✅ *Action:*\n"
                "1. Cek MT5 terminal (masih running?)\n"
                "2. Cek koneksi internet\n"
                "3. Cek login broker (session expired?)\n"
                "4. Restart MT5 jika perlu\n\n"
                "Alert berikutnya dikirim jika masih down dalam 5 menit."
            )
 
            send_whatsapp_alert(message)
            logger.warning(
                "MT5Watchdog: connection-lost alert sent (failures=%d reason=%s)",
                failures,
                reason,
            )
        except Exception as e:
            # Jangan raise — alert failure tidak boleh crash watchdog
            logger.exception("MT5Watchdog: failed to send connection-lost alert: %s", e)
 
    def _send_recovery_alert(self, downtime_sec: float) -> None:
        """Kirim WhatsApp alert ketika MT5 kembali connected setelah downtime."""
        with self._lock:
            now = time.time()
            last_recovery = self._state.last_recovery_alert_ts
            if last_recovery and (now - last_recovery) < _ALERT_COOLDOWN_SEC:
                return
            self._state.last_recovery_alert_ts = now
 
        try:
            from ..notifications.whatsapp_notifier import send_whatsapp_alert
            now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
            downtime_min = round(downtime_sec / 60.0, 1)
 
            message = (
                "✅ *MT5 CONNECTION RESTORED*\n\n"
                f"🕐 {now_str}\n"
                f"⏱️ Downtime: {downtime_min} menit\n\n"
                "Trading dan monitoring kembali normal.\n\n"
                "⚠️ *Perlu cek manual:*\n"
                "• Open positions selama downtime\n"
                "• Exit rules yang mungkin terlewat\n"
                "• PnL impact selama gap"
            )
 
            send_whatsapp_alert(message)
            logger.info(
                "MT5Watchdog: recovery alert sent (downtime=%.1f min)",
                downtime_min,
            )
        except Exception as e:
            logger.exception("MT5Watchdog: failed to send recovery alert: %s", e)
 
