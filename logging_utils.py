import logging
from pathlib import Path

BASE_LOG_DIR = Path(__file__).resolve().parent / "logs"
BASE_LOG_DIR.mkdir(exist_ok=True)


def get_logger(name: str) -> logging.Logger:
    """Return a module-specific logger writing to logs/system.log.

    Use this everywhere instead of configuring logging in each module.
    """
    log_file = BASE_LOG_DIR / "system.log"
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)

    # File handler
    fh = logging.FileHandler(log_file, encoding="utf-8")
    fh.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    fh.setFormatter(fmt)

    # Console handler (optional)
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch.setFormatter(fmt)

    logger.addHandler(fh)
    logger.addHandler(ch)

    return logger
