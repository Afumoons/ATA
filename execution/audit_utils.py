from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, List

from ..logging_utils import get_logger

logger = get_logger(__name__)
BASE_DIR = Path(__file__).resolve().parent
UNMATCHED_CLOSED_DEALS_PATH = BASE_DIR / "unmatched_closed_deals.json"
POOL_AUDIT_TRAIL_PATH = BASE_DIR / "pool_audit_trail.json"


def _safe_write_json(path: Path, data: Any) -> None:
    payload = json.dumps(data, indent=2, ensure_ascii=False)
    fd, tmp_path = tempfile.mkstemp(dir=path.parent, prefix=f".{path.stem}_", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(payload)
        os.replace(tmp_path, path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def _load_json_list(path: Path) -> List[dict]:
    if not path.exists():
        return []
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            return data
    except Exception:
        logger.exception("Failed to load audit list from %s", path)
    return []


def append_unmatched_closed_deal(item: dict, keep: int = 300) -> None:
    rows = _load_json_list(UNMATCHED_CLOSED_DEALS_PATH)
    enriched = {
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        **item,
    }
    rows.append(enriched)
    rows = rows[-keep:]
    try:
        _safe_write_json(UNMATCHED_CLOSED_DEALS_PATH, rows)
    except Exception:
        logger.exception("Failed to append unmatched closed deal audit row")


def append_pool_audit(item: dict, keep: int = 500) -> None:
    rows = _load_json_list(POOL_AUDIT_TRAIL_PATH)
    enriched = {
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        **item,
    }
    rows.append(enriched)
    rows = rows[-keep:]
    try:
        _safe_write_json(POOL_AUDIT_TRAIL_PATH, rows)
    except Exception:
        logger.exception("Failed to append pool audit row")
