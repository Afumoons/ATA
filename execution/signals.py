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
# Exness strips special chars from MT5 comments, so we maintain a
# side-channel file: ticket_id → full_strategy_name.
# live_monitor.py reads this for PnL attribution.
# ---------------------------------------------------------------------------
_TICKET_MAP_PATH = Path(__file__).resolve().parent / "ticket_strategy_map.json"
_MAX_TICKET_MAP_SIZE = 2000


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
    mapping = _load_ticket_map()
    mapping[str(ticket)] = strategy_name
    _save_ticket_map(mapping)
    logger.debug("Registered ticket %s → %s", ticket, strategy_name)


def get_strategy_for_ticket(ticket: int) -> Optional[str]:
    return _load_ticket_map().get(str(ticket))


# ---------------------------------------------------------------------------
# Pip params
# ---------------------------------------------------------------------------

def _pip_params(symbol: str) -> tuple[float, float]:
    sym = symbol.upper()
    if "XAU" in sym or "XAG" in sym:
        return 0.01, 1.0
    if "BTC" in sym or "ETH" in sym or "LTC" in sym or "XRP" in sym:
        return 1.0, 1.0
    return 0.0001, 10.0


# ---------------------------------------------------------------------------
# Signal generation
# ---------------------------------------------------------------------------

@dataclass
class Signal:
    strategy: StrategyDefinition
    direction: str


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
        "blocked_news_lockout": False,
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

    # ------------------------------------------------------------------ #
    # Tier 1: News lockout guard — inside execute_signals_for_symbol      #
    # Protects against any caller bypassing the check in scheduler/main.  #
    # in_news_lockout=True means a high-impact event is within ±15 min.  #
    # ------------------------------------------------------------------ #
    if bool(latest.get("in_news_lockout", False)):
        logger.warning(
            "News lockout active for %s %s at %s — skipping signal generation "
            "(high-impact event within ±15 min)",
            symbol, timeframe, latest.get("time", "?"),
        )
        summary["blocked_news_lockout"] = True
        return [], summary

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

    # Latest ATR for adaptive SL sizing (if available)
    atr_value = float(latest.get("atr", 0.0) or 0.0)

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
                # ------------------------------------------------------------------ #
                # SL/TP sizing                                                        #
                #                                                                      #
                # Mirror backtests.engine behaviour:                                   #
                # - If ATR + sl_atr_mult + tp_atr_mult are available, derive BOTH     #
                #   stop_loss_pips and take_profit_pips from ATR (pure ATR mode).     #
                # - Otherwise fall back to static stop_loss_pips / take_profit_pips.  #
                # Optionally we still enforce a symbol-specific *minimum* SL distance  #
                # for very volatile symbols (XAU, BTC) to avoid 1-tick stop-outs.     #
                # ------------------------------------------------------------------ #
                stop_loss_pips = float(getattr(strat, "stop_loss_pips", 0.0) or 0.0)
                take_profit_pips = float(getattr(strat, "take_profit_pips", 0.0) or 0.0)

                sl_mult = getattr(strat, "sl_atr_mult", None)
                tp_mult = getattr(strat, "tp_atr_mult", None)

                # Pure ATR mode (matches backtests.engine): use ATR for both SL & TP
                if (
                    atr_value > 0.0
                    and sl_mult not in (None, 0, 0.0)
                    and tp_mult not in (None, 0, 0.0)
                ):
                    sl_price_dist = float(sl_mult) * atr_value
                    tp_price_dist = float(tp_mult) * atr_value

                    stop_loss_pips = sl_price_dist / max(pip_size, 1e-9)
                    take_profit_pips = tp_price_dist / max(pip_size, 1e-9)

                    logger.debug(
                        "ATR SL/TP: strategy=%s symbol=%s atr=%.3f sl_mult=%.2f tp_mult=%.2f sl_pips=%.1f tp_pips=%.1f",
                        strat.name,
                        symbol,
                        atr_value,
                        sl_mult,
                        tp_mult,
                        stop_loss_pips,
                        take_profit_pips,
                    )
                # Else: leave stop_loss_pips / take_profit_pips as configured (static mode)

                # Symbol-specific minimum SL distance (price-based), to avoid
                # 1-tick SL hits in volatile conditions. This is an additional
                # guard on top of the ATR sizing above.
                sym_u = symbol.upper()
                min_sl_pips = 0.0
                if "XAU" in sym_u:
                    # Minimum ~$2 distance in price
                    min_sl_price = 2.0
                    min_sl_pips = min_sl_price / max(pip_size, 1e-9)
                elif "BTC" in sym_u:
                    # Minimum ~$200 distance in price
                    min_sl_price = 200.0
                    min_sl_pips = min_sl_price / max(pip_size, 1e-9)

                if min_sl_pips > 0.0 and stop_loss_pips > 0.0 and stop_loss_pips < min_sl_pips:
                    logger.info(
                        "SL too tight for %s %s: %.1f pips < min %.1f pips (atr=%.3f) — clamping",
                        symbol, strat.name, stop_loss_pips, min_sl_pips, atr_value,
                    )
                    stop_loss_pips = min_sl_pips

                res = execute_trade(
                    strategy_name=strat.name,
                    symbol=symbol,
                    direction=sig.direction,
                    risk_perc=rp,
                    stop_loss_pips=stop_loss_pips,
                    take_profit_pips=take_profit_pips,
                    pip_size=pip_size,
                    pip_value_per_lot=pip_value_per_lot,
                    timeframe=timeframe,          # Tier 1: passed for comment generation
                )
                results.append((sig, res.reason))

                if res.success:
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