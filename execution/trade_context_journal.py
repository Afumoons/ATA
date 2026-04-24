from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import pandas as pd

from ..config import canonical_symbol, execution_variants_for
from ..research.regime import add_regime_column

BASE_DIR = Path(__file__).resolve().parent
JOURNAL_PATH = BASE_DIR / "trade_context_journal.json"
FEATURES_DIR = BASE_DIR.parents[0] / "data" / "features"


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


def _load_journal() -> dict[str, Any]:
    if not JOURNAL_PATH.exists():
        return {"trades": {}, "generated_at": None}
    try:
        return json.loads(JOURNAL_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"trades": {}, "generated_at": None}


def _resolve_feature_path(symbol: str) -> Optional[Path]:
    canon = canonical_symbol(symbol)
    candidates: list[str] = []
    for candidate in [canon, *execution_variants_for(canon), symbol]:
        if candidate and candidate not in candidates:
            candidates.append(candidate)
    for candidate in candidates:
        path = FEATURES_DIR / f"{candidate}_M15_features.parquet"
        if path.exists():
            return path
    return None


def _feature_context(symbol: str, ts_iso: str) -> dict[str, Any]:
    path = _resolve_feature_path(symbol)
    if path is None:
        return {"bar_time": None, "regime": None, "regime_class": None, "regime_type": None, "vol_regime": None, "session": None}
    df = pd.read_parquet(path)
    df = add_regime_column(df)
    df["time"] = pd.to_datetime(df["time"], utc=True)
    df = df.sort_values("time").reset_index(drop=True)
    ts = pd.to_datetime(datetime.fromisoformat(ts_iso.replace("Z", "+00:00")).astimezone(timezone.utc), utc=True).to_datetime64()
    haystack = df["time"].to_numpy(dtype="datetime64[ns]")
    idx = haystack.searchsorted(ts, side="right") - 1
    if idx < 0 or idx >= len(df):
        return {"bar_time": None, "regime": None, "regime_class": None, "regime_type": None, "vol_regime": None, "session": None}
    row = df.iloc[int(idx)]
    session = None
    if int(row.get("session_asia", 0) or 0) == 1:
        session = "asia"
    elif int(row.get("session_london", 0) or 0) == 1:
        session = "london"
    elif int(row.get("session_new_york", 0) or 0) == 1:
        session = "new_york"
    return {
        "bar_time": pd.Timestamp(row["time"]).isoformat(),
        "regime": row.get("regime"),
        "regime_class": row.get("regime_class"),
        "regime_type": row.get("regime_type"),
        "vol_regime": row.get("vol_regime"),
        "session": session,
    }


def register_trade_entry_context(*, ticket: int | str, strategy_name: str, symbol: str, timeframe: str, entry_time: Optional[str] = None) -> None:
    trade_id = str(ticket)
    ts_iso = entry_time or datetime.now(timezone.utc).isoformat()
    data = _load_journal()
    trades = data.setdefault("trades", {})
    rec = trades.get(trade_id) or {}
    rec.update({
        "ticket": trade_id,
        "strategy_name": strategy_name,
        "symbol": symbol,
        "symbol_canonical": canonical_symbol(symbol),
        "timeframe": timeframe,
        "entry_time": ts_iso,
        "entry_context": _feature_context(symbol, ts_iso),
    })
    trades[trade_id] = rec
    data["generated_at"] = datetime.now(timezone.utc).isoformat()
    _safe_write_json(JOURNAL_PATH, data)


def register_trade_exit_context(*, ticket: int | str, symbol: str, exit_time: Optional[str] = None, pnl: Optional[float] = None) -> None:
    trade_id = str(ticket)
    ts_iso = exit_time or datetime.now(timezone.utc).isoformat()
    data = _load_journal()
    trades = data.setdefault("trades", {})
    rec = trades.get(trade_id) or {"ticket": trade_id, "symbol": symbol, "symbol_canonical": canonical_symbol(symbol)}
    rec.update({
        "exit_time": ts_iso,
        "exit_context": _feature_context(symbol, ts_iso),
    })
    if pnl is not None:
        rec["pnl"] = float(pnl)
    trades[trade_id] = rec
    data["generated_at"] = datetime.now(timezone.utc).isoformat()
    _safe_write_json(JOURNAL_PATH, data)
