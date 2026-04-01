import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

BASE_LOG_DIR = Path(__file__).resolve().parent / "logs"
BASE_LOG_DIR.mkdir(exist_ok=True)

MAX_LOG_BYTES = 5 * 1024 * 1024  # 5 MB per file
BACKUP_COUNT = 5                 # keep system.log + 5 rotated files


def get_logger(name: str) -> logging.Logger:
    """Return a module-specific logger writing to logs/system.log.

    Uses size-based rotation so the main log file does not grow forever.
    """
    log_file = BASE_LOG_DIR / "system.log"
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)
    logger.propagate = False

    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")

    # Rotating file handler
    fh = RotatingFileHandler(
        log_file,
        maxBytes=MAX_LOG_BYTES,
        backupCount=BACKUP_COUNT,
        encoding="utf-8",
    )
    fh.setLevel(logging.INFO)
    fh.setFormatter(fmt)

    # Console handler (optional)
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch.setFormatter(fmt)

    logger.addHandler(fh)
    logger.addHandler(ch)

    return logger
