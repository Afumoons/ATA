from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import List, Tuple, Any, Dict, Optional

import pandas as pd

from ..logging_utils import get_logger
from ..strategies.base import StrategyDefinition
from ..strategies.pool import StrategyPool
from ..execution.engine import execute_trade
from ..execution.live_state_utils import can_open_new_trade

logger = get_logger(__name__)

ACTIVE_REGIME_EDGE_THRESHOLD = 0.0
EXPLORATORY_REGIME_EDGE_THRESHOLD = -10.0

# ---------------------------------------------------------------------------
# Ticket → strategy name mapping
#
# Exness MT5 strips special characters (-, _) from order comments, so the
# comment field cannot be used for strategy attribution. Instead we persist
# a side-channel mapping: ticket_id → full_strategy_name, written here
# immediately after a successful order_send(), and read by live_monitor.py
# when processing closed deals via history_deals_get().
# ---------------------------------------------------------------------------
_TICKET_MAP_PATH = Path(__file__).resolve().parent / "ticket_strategy_map.json"
_MAX_TICKET_MAP_SIZE = 2000  # keep last N entries; at ~10 trades/day = ~6 months


def _load_ticket_map() -> Dict[str, str]:
    if _TICKET_MAP_PATH.exists():
        try:
            with _TICKET_MAP_PATH.open("r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                return data
        except Exception:
            logger.exception("Failed to load ticket_strategy_map")
    return {}


def _save_ticket_map(mapping: Dict[str, str]) -> None:
    try:
        if len(mapping) > _MAX_TICKET_MAP_SIZE:
            # Keep most recent by ticket number
            keys = sorted(mapping.keys(), key=lambda k: int(k) if k.isdigit() else 0)
            mapping = {k: mapping[k] for k in keys[-_MAX_TICKET_MAP_SIZE:]}
        data = json.dumps(mapping, indent=2)
        fd, tmp = tempfile.mkstemp(
            dir=_TICKET_MAP_PATH.parent, prefix=".ticket_map_", suffix=".tmp"
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(data)
            os.replace(tmp, _TICKET_MAP_PATH)
        except Exception:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise
    except Exception:
        logger.exception("Failed to save ticket_strategy_map")


def register_ticket(ticket: int, strategy_name: str) -> None:
    """Persist ticket → full strategy name for later PnL attribution."""
    mapping = _load_ticket_map()
    mapping[str(ticket)] = strategy_name
    _save_ticket_map(mapping)
    logger.debug("Registered ticket %s → %s", ticket, strategy_name)


def get_strategy_for_ticket(ticket: int) -> Optional[str]:
    """Look up full strategy name for an MT5 ticket. Returns None if not found."""
    return _load_ticket_map().get(str(ticket))


# ---------------------------------------------------------------------------
# Pip params per instrument
# ---------------------------------------------------------------------------

def _pip_params(symbol: str) -> tuple[float, float]:
    """Return (pip_size, pip_value_per_lot)."""
    sym = symbol.upper()
    if "XAU" in sym or "XAG" in sym:
        return 0.01, 1.0
    if "BTC" in sym or "ETH" in sym or "LTC" in sym or "XRP" in sym:
        return 1.0, 1.0
    return 0.0001, 10.0


# ---------------------------------------------------------------------------
# Signal dataclass + generation
# ---------------------------------------------------------------------------

@dataclass
class Signal:
    strategy: StrategyDefinition
    direction: str  # "long" or "short"


def generate_signals_for_row(
    row: pd.Series,
    strategies: List[StrategyDefinition],
) -> List[Signal]:
    from ..backtests.engine import _eval_rule

    signals: List[Signal] = []
    for strat in strategies:
        long_hit = _eval_rule(row, strat.long_entry_rule)
        short_hit = _eval_rule(row, strat.short_entry_rule)
        logger.debug(
            "Entry eval: strategy=%s long=%s short=%s",
            strat.name, long_hit, short_hit,
        )
        if long_hit:
            signals.append(Signal(strategy=strat, direction="long"))
        if short_hit:
            signals.append(Signal(strategy=strat, direction="short"))
    return signals


def _regime_edge(stats: Dict[str, Any], regime_label: str) -> float:
    if not stats:
        return -999.0
    ex = stats.get("strategy_explain", {}) or {}
    rp = ex.get("regime_pnl", {}) or {}
    regime_stats = rp.get(regime_label, {}) or {}
    try:
        return float(regime_stats.get("return_pct", -999.0) or -999.0)
    except Exception:
        return -999.0


def _map_current_to_regime_pnl_label(current_regime: str) -> str:
    if current_regime in {"trending_up", "trending_down", "ranging"}:
        return current_regime
    if current_regime in {"high_vol", "low_vol"}:
        return "ranging"
    return "unknown"


# ---------------------------------------------------------------------------
# Main execution
# ---------------------------------------------------------------------------

def execute_signals_for_symbol(
    symbol: str,
    timeframe: str,
    features_df: pd.DataFrame,
    pool: StrategyPool,
    risk_perc: float,
) -> Tuple[List[Tuple[Signal, str]], Dict[str, bool]]:
    summary: Dict[str, bool] = {
        "blocked_daily_limits": False,
        "no_strategies_in_pool": False,
        "no_strategies_with_edge": False,
        "no_entry_active": False,
        "no_entry_exploratory": False,
    }

    if features_df.empty:
        logger.warning("Empty features_df for %s %s", symbol, timeframe)
        summary["no_strategies_with_edge"] = True
        return [], summary

    latest = features_df.sort_values("time").iloc[-1]
    current_regime = str(latest.get("regime", "unknown"))
    logger.info("Current regime for %s %s: %s", symbol, timeframe, current_regime)

    from ..config import risk_config
    from ..execution.live_monitor import _get_account_equity

    current_equity = _get_account_equity()

    if not can_open_new_trade(
        current_equity=current_equity,
        max_dd_pct=risk_config.max_daily_drawdown_pct,
        max_trades=risk_config.max_trades_per_day,
        enabled=risk_config.daily_limits_enabled,
    ):
        logger.info(
            "Daily limits prevent new trades for %s %s (equity=%.2f)",
            symbol, timeframe, current_equity,
        )
        summary["blocked_daily_limits"] = True
        return [], summary

    active_records = [
        rec for rec in pool.strategies.values()
        if rec.status == "active" and rec.symbol == symbol and rec.timeframe == timeframe
    ]
    exploratory_records = [
        rec for rec in pool.strategies.values()
        if rec.status == "exploratory" and rec.symbol == symbol and rec.timeframe == timeframe
    ]

    if not active_records and not exploratory_records:
        logger.info("No active/exploratory strategies for %s %s", symbol, timeframe)
        summary["no_strategies_in_pool"] = True
        return [], summary

    regime_label = _map_current_to_regime_pnl_label(current_regime)

    def _filter_and_rank(records, tier: str) -> List[Any]:
        if not records:
            return []
        if regime_label == "unknown":
            logger.warning(
                "Unknown regime for %s %s — passing all %d %s strategies",
                symbol, timeframe, len(records), tier,
            )
            return records

        threshold = ACTIVE_REGIME_EDGE_THRESHOLD if tier == "active" else EXPLORATORY_REGIME_EDGE_THRESHOLD
        scored: List[Tuple[float, Any]] = []
        for rec in records:
            edge = _regime_edge(rec.stats or {}, regime_label)
            scored.append((edge, rec))
            logger.info(
                "Regime edge: symbol=%s timeframe=%s regime=%s strategy=%s tier=%s edge=%.3f threshold=%.1f",
                symbol, timeframe, regime_label, rec.name, tier, edge, threshold,
            )

        kept = sorted([(e, r) for e, r in scored if e > threshold], key=lambda x: x[0], reverse=True)
        filtered = [r for _, r in kept]

        if len(filtered) != len(records):
            blocked = [r.name for e, r in scored if e <= threshold]
            logger.info(
                "Regime filter %s %s (%s) [%s]: %d → %d passed | blocked: %s",
                symbol, timeframe, regime_label, tier, len(records), len(filtered), blocked,
            )

        if not filtered and scored and tier == "exploratory":
            scored.sort(key=lambda x: x[0], reverse=True)
            best_edge, best_rec = scored[0]
            filtered = [best_rec]
            logger.info(
                "Regime fallback %s %s: keeping best exploratory edge=%.2f",
                symbol, timeframe, best_edge,
            )

        return filtered

    active_records = _filter_and_rank(active_records, "active")[:5]
    exploratory_records = _filter_and_rank(exploratory_records, "exploratory")[:3]

    if not active_records and not exploratory_records:
        logger.info("No strategies with acceptable edge for %s %s", symbol, timeframe)
        summary["no_strategies_with_edge"] = True
        return [], summary

    from ..strategies.generator import load_strategy
    base_dir = Path(__file__).resolve().parents[1] / "strategies" / "generated"

    def _load_strats(records):
        out = []
        for rec in records:
            try:
                out.append(load_strategy(base_dir / f"{rec.name}.json"))
            except Exception:
                logger.exception("Failed to load strategy %s", rec.name)
        return out

    active_strategies = _load_strats(active_records)
    exploratory_strategies = _load_strats(exploratory_records)

    logger.info(
        "Feature snapshot for %s %s: time=%s regime=%s "
        "ma_short=%.5f ma_long=%.5f trend_strength=%.4f rsi=%.2f",
        symbol, timeframe, latest.get("time", "?"), current_regime,
        float(latest.get("ma_short", float("nan"))),
        float(latest.get("ma_long", float("nan"))),
        float(latest.get("trend_strength", float("nan"))),
        float(latest.get("rsi", float("nan"))),
    )

    results: List[Tuple[Signal, str]] = []
    pip_size, pip_value_per_lot = _pip_params(symbol)
    risk_perc_active = risk_perc
    risk_perc_exploratory = min(risk_perc * 0.25, 0.1)

    def _execute_batch(strategies: List[StrategyDefinition], rp: float, tier: str) -> None:
        sigs = generate_signals_for_row(latest, strategies)
        if not sigs:
            logger.info(
                "No entry conditions met for %s strategies on %s %s (%d evaluated)",
                tier, symbol, timeframe, len(strategies),
            )
            summary[f"no_entry_{tier}"] = True
            return

        logger.info("%d signal(s) from %s strategies for %s %s", len(sigs), tier, symbol, timeframe)

        for sig in sigs:
            strat = sig.strategy
            try:
                res = execute_trade(
                    strategy_name=strat.name,
                    symbol=symbol,
                    direction=sig.direction,
                    risk_perc=rp,
                    stop_loss_pips=strat.stop_loss_pips,
                    take_profit_pips=strat.take_profit_pips,
                    pip_size=pip_size,
                    pip_value_per_lot=pip_value_per_lot,
                )
                results.append((sig, res.reason))

                if res.success:
                    # Store ticket→strategy mapping (Exness strips special chars
                    # from comment, so comment-based attribution is not reliable)
                    if res.ticket is not None:
                        try:
                            register_ticket(res.ticket, strat.name)
                        except Exception:
                            logger.exception(
                                "Failed to register ticket %s → %s", res.ticket, strat.name
                            )
                    logger.info(
                        "Trade placed (%s): strategy=%s symbol=%s dir=%s vol=%s ticket=%s",
                        tier, strat.name, symbol, sig.direction,
                        getattr(res, "volume", "?"), res.ticket,
                    )
                else:
                    logger.warning(
                        "Trade rejected (%s): strategy=%s symbol=%s dir=%s reason=%s",
                        tier, strat.name, symbol, sig.direction, res.reason,
                    )
            except Exception as e:
                logger.exception("Error executing %s signal for %s: %s", tier, strat.name, e)
                results.append((sig, f"error: {e}"))

    if active_strategies:
        _execute_batch(active_strategies, risk_perc_active, "active")
    if exploratory_strategies:
        _execute_batch(exploratory_strategies, risk_perc_exploratory, "exploratory")

    return results, summary