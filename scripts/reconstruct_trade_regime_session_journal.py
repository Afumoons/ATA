from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

import pandas as pd

from autonomous_trading_ai.config import canonical_symbol, execution_variants_for
from autonomous_trading_ai.execution.strategy_live_stats import load_all_strategy_stats
from autonomous_trading_ai.research.regime import add_regime_column

ROOT = Path(__file__).resolve().parents[1]
EXEC_DIR = ROOT / "execution"
DATA_FEATURES_DIR = ROOT / "data" / "features"
OUTPUT_PATH = EXEC_DIR / "strategy_trade_journal.json"
TRADES_LOG_PATH = EXEC_DIR / "trades.log"
TICKET_MAP_PATH = EXEC_DIR / "ticket_strategy_map.json"

TRADE_RE = re.compile(
    r"ts=(?P<ts>\S+)\s+strategy=(?P<strategy>\S+)\s+symbol=(?P<symbol>\S+)\s+dir=(?P<direction>\S+)\s+vol=(?P<volume>\S+)\s+price=(?P<price>\S+)\s+sl=(?P<sl>\S+)\s+tp=(?P<tp>\S+)\s+ticket=(?P<ticket>\S+)\s+reason=(?P<reason>\S+)"
)


def _parse_iso_utc(text: str) -> datetime:
    dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _load_ticket_map() -> Dict[str, str]:
    if not TICKET_MAP_PATH.exists():
        return {}
    return json.loads(TICKET_MAP_PATH.read_text(encoding="utf-8"))


def _load_trade_log_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not TRADES_LOG_PATH.exists():
        return rows
    for line in TRADES_LOG_PATH.read_text(encoding="utf-8", errors="ignore").splitlines():
        m = TRADE_RE.search(line.strip())
        if not m:
            continue
        gd = m.groupdict()
        try:
            rows.append(
                {
                    "entry_time": _parse_iso_utc(gd["ts"]),
                    "strategy_name": gd["strategy"],
                    "symbol": gd["symbol"],
                    "direction": gd["direction"],
                    "ticket": str(int(gd["ticket"])),
                    "entry_price": float(gd["price"]),
                    "sl": float(gd["sl"]),
                    "tp": float(gd["tp"]),
                    "volume": float(gd["volume"]),
                    "reason": gd["reason"],
                }
            )
        except Exception:
            continue
    return rows


def _resolve_feature_symbol(symbol: str) -> str:
    canon = canonical_symbol(symbol)
    candidates = []
    for candidate in [canon, *execution_variants_for(canon), symbol]:
        if candidate and candidate not in candidates:
            candidates.append(candidate)
    for candidate in candidates:
        path = DATA_FEATURES_DIR / f"{candidate}_M15_features.parquet"
        if path.exists():
            return candidate
    raise FileNotFoundError(
        f"Missing features parquet for symbol={symbol}, canonical={canon}, candidates={candidates}"
    )


def _load_feature_frame(symbol: str) -> pd.DataFrame:
    resolved_symbol = _resolve_feature_symbol(symbol)
    path = DATA_FEATURES_DIR / f"{resolved_symbol}_M15_features.parquet"
    df = pd.read_parquet(path)
    if "time" not in df.columns:
        raise ValueError(f"Features file missing time column: {path}")
    df = add_regime_column(df)
    df["time"] = pd.to_datetime(df["time"], utc=True)
    df = df.sort_values("time").reset_index(drop=True)
    return df


def _nearest_feature_row(df: pd.DataFrame, ts: datetime) -> Optional[pd.Series]:
    needle = pd.to_datetime(ts, utc=True).to_datetime64()
    haystack = df["time"].to_numpy(dtype="datetime64[ns]")
    idx = haystack.searchsorted(needle, side="right") - 1
    if idx < 0 or idx >= len(df):
        return None
    return df.iloc[int(idx)]


def _extract_context(row: Optional[pd.Series]) -> dict[str, Any]:
    if row is None:
        return {
            "bar_time": None,
            "regime": None,
            "regime_class": None,
            "regime_type": None,
            "vol_regime": None,
            "session": None,
            "trend_strength": None,
            "volatility": None,
        }
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
        "trend_strength": float(row.get("trend_strength")) if pd.notna(row.get("trend_strength")) else None,
        "volatility": float(row.get("volatility")) if pd.notna(row.get("volatility")) else None,
    }


def main() -> None:
    ticket_map = _load_ticket_map()
    trade_rows = _load_trade_log_rows()
    stats = load_all_strategy_stats()

    if not trade_rows:
        raise RuntimeError("No parsed trade rows found in execution/trades.log")

    feature_cache: Dict[str, pd.DataFrame] = {}
    for symbol in sorted({r["symbol"] for r in trade_rows}):
        try:
            feature_cache[symbol] = _load_feature_frame(symbol)
        except Exception as exc:
            print(f"WARN missing feature context for {symbol}: {exc}")

    journal: Dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": {
            "trades_log": str(TRADES_LOG_PATH),
            "ticket_strategy_map": str(TICKET_MAP_PATH),
            "note": "Entry reconstructed from trades.log, exit inferred heuristically from later bars because closed-deal journal lacks per-trade timestamps in local files.",
        },
        "strategies": {},
        "coverage": {
            "strategies_in_live_stats": len(stats),
            "trade_log_rows": len(trade_rows),
            "reconstructed_trades": 0,
            "with_entry_context": 0,
            "with_exit_context_estimate": 0,
        },
    }

    by_strategy: Dict[str, list[dict[str, Any]]] = {}
    for row in trade_rows:
        strat = row["strategy_name"]
        if strat not in stats and row["ticket"] in ticket_map:
            strat = ticket_map[row["ticket"]]
            row["strategy_name"] = strat
        by_strategy.setdefault(strat, []).append(row)

    for strat, rows in by_strategy.items():
        rows = sorted(rows, key=lambda x: x["entry_time"])
        strat_journal = []
        feature_df = feature_cache.get(rows[0]["symbol"])
        canonical_sym = canonical_symbol(rows[0]["symbol"])
        recent_pnls = list((stats.get(strat).recent_pnls if stats.get(strat) else []) or [])

        pnl_offset = max(0, len(rows) - len(recent_pnls))
        for idx, row in enumerate(rows):
            entry_ctx = _extract_context(_nearest_feature_row(feature_df, row["entry_time"])) if feature_df is not None else _extract_context(None)
            if entry_ctx["regime"] is not None:
                journal["coverage"]["with_entry_context"] += 1

            exit_time_est = None
            if idx + 1 < len(rows):
                exit_time_est = rows[idx + 1]["entry_time"]
            exit_ctx = _extract_context(_nearest_feature_row(feature_df, exit_time_est)) if (feature_df is not None and exit_time_est is not None) else _extract_context(None)
            if exit_ctx["regime"] is not None:
                journal["coverage"]["with_exit_context_estimate"] += 1

            pnl = None
            pnl_source = "unknown"
            recent_idx = idx - pnl_offset
            if 0 <= recent_idx < len(recent_pnls):
                pnl = float(recent_pnls[recent_idx])
                pnl_source = "recent_pnls_aligned_suffix"

            strat_journal.append(
                {
                    "ticket": row["ticket"],
                    "symbol": row["symbol"],
                    "symbol_canonical": canonical_sym,
                    "direction": row["direction"],
                    "entry_time": row["entry_time"].isoformat(),
                    "entry_price": row["entry_price"],
                    "pnl": pnl,
                    "pnl_source": pnl_source,
                    "entry_context": entry_ctx,
                    "exit_time_estimate": exit_time_est.isoformat() if exit_time_est else None,
                    "exit_context_estimate": exit_ctx,
                    "reconstruction_quality": {
                        "entry": "exact_from_trades_log_plus_feature_lookup" if entry_ctx["regime"] is not None else "missing_feature_context",
                        "symbol_mapping": canonical_sym,
                        "exit": "estimated_from_next_entry_bar" if exit_time_est else "unavailable",
                    },
                }
            )
            journal["coverage"]["reconstructed_trades"] += 1

        live_stats = stats.get(strat)
        journal["strategies"][strat] = {
            "live_stats": {
                "total_pnl": getattr(live_stats, "total_pnl", None),
                "num_trades": getattr(live_stats, "num_trades", None),
                "last_update": getattr(live_stats, "last_update", None),
                "recent_pnls": getattr(live_stats, "recent_pnls", None),
            },
            "trades": strat_journal,
        }

    OUTPUT_PATH.write_text(json.dumps(journal, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote trade journal: {OUTPUT_PATH}")
    print(json.dumps(journal["coverage"], indent=2))


if __name__ == "__main__":
    main()
