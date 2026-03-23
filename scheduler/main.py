from __future__ import annotations

import time as _time
from datetime import datetime
from pathlib import Path

from apscheduler.schedulers.background import BackgroundScheduler

from ..logging_utils import get_logger
from ..config import scheduler_config, risk_config
from ..data.collector_mt5 import initialize_mt5, shutdown_mt5, fetch_ohlc, save_ohlc
from ..research.features import compute_features, save_features
from ..research.regime import add_regime_column
from ..research.features import load_features
from ..strategies.pool import load_pool, save_pool
from ..strategies.evolution import evolve_population, load_population, save_population
from ..strategies.generator import load_strategy
from ..backtests.engine import run_backtest
from ..backtests.evaluation import evaluate_strategy
from ..backtests.walkforward import walk_forward_test
from ..backtests.monte_carlo import monte_carlo_pnl
from ..execution.live_monitor import update_live_stats
from ..execution.signals import execute_signals_for_symbol
from ..execution.strategy_live_stats import load_all_strategy_stats, MAX_RECENT_TRADES
from ..vector_memory.research_memory import ResearchMemory

logger = get_logger(__name__)
BASE_DIR = Path(__file__).resolve().parents[1]

# Symbols/timeframes to manage (can be externalized/configured later)
MANAGED_SYMBOLS = ["XAUUSDm", "BTCUSDm"]
TIMEFRAME = "M15"

# Minimum edge score for a strategy to be allowed to execute live signals.
MINIMUM_EDGE_FOR_EXECUTION = 0.0

# ---------------------------------------------------------------------------
# Execution pool filtering
#
# Three-stage filter:
#   Stage 1 — Deduplicate: drop clones with identical RULE STRINGS,
#             keeping only the one with the highest WF Sharpe per cluster.
#             Previously used backtest stats as fingerprint — this allowed
#             strategies with identical long/short rules but different names
#             to all fire simultaneously (concentration blast).
#   Stage 2 — Quality gate: enforce minimum robustness thresholds.
#   Stage 3 — Cap: limit final pool to MAX_EXECUTION_POOL.
# ---------------------------------------------------------------------------

EXEC_MIN_WF_SHARPE   = 2.0   # walk-forward Sharpe — primary robustness gate
EXEC_MAX_DD_PCT      = 12.0  # max drawdown ceiling (absolute %)
EXEC_MIN_TRADES      = 200   # minimum trades for statistical significance
EXEC_MAX_CONSEC_LOSS = 15    # max consecutive losses — controls tail risk
MAX_EXECUTION_POOL   = 10    # hard cap on strategies executing per cycle

# Regime-adaptive sort weight (Stage 3).
REGIME_SORT_NORM     = 20.0

# Session-adaptive sort weight.
SESSION_SORT_NORM    = 10.0


def _current_session() -> str:
    """Return current trading session based on UTC hour."""
    from datetime import datetime, timezone
    hour = datetime.now(timezone.utc).hour
    if 0 <= hour < 7:
        return "asia"
    if 7 <= hour < 13:
        return "london"
    return "new_york"


# ---------------------------------------------------------------------------
# Regime-adaptive execution scoring
# ---------------------------------------------------------------------------

def _hybrid_regime_score(rec, current_regime: str, current_session: str = "") -> float:
    """Regime- and session-adaptive sort key for execution pool selection."""
    s = rec.stats or {}
    wf = float(s.get("wf_overall_sharpe", 0) or 0)
    ex = s.get("strategy_explain", {}) or {}

    # Regime component
    regime_pnl = ex.get("regime_pnl", {}) or {}
    regime_ret = float(
        (regime_pnl.get(current_regime, {}) or {}).get("return_pct", 0)
    )
    regime_bonus = 1.0 + max(-0.5, min(0.5, regime_ret / REGIME_SORT_NORM))

    # Session component
    session_bonus = 1.0
    if current_session:
        session_pnl = ex.get("session_pnl", {}) or {}
        session_ret = float(
            (session_pnl.get(current_session, {}) or {}).get("return_pct", 0)
        )
        session_bonus = 1.0 + max(-0.5, min(0.5, session_ret / SESSION_SORT_NORM))

    return wf * regime_bonus * session_bonus


def job_update_data() -> None:
    """Fetch latest OHLC, compute features + regimes for managed symbols."""
    logger.info("Scheduler: job_update_data start")
    for symbol in MANAGED_SYMBOLS:
        try:
            df = fetch_ohlc(symbol, timeframe=TIMEFRAME)
            save_ohlc(df, symbol, TIMEFRAME)
            feat = compute_features(df, symbol, TIMEFRAME)
            feat = add_regime_column(feat)
            save_features(feat, symbol, TIMEFRAME)
        except Exception as e:
            logger.exception("job_update_data error for %s: %s", symbol, e)
    logger.info("Scheduler: job_update_data done")


# ---------------------------------------------------------------------------
# News jobs
# ---------------------------------------------------------------------------

def job_update_news() -> None:
    """Fetch Forex Factory calendar and save to news_events.parquet."""
    logger.info("Scheduler: job_update_news start")
    try:
        from ..data.news_collector import update_news_events, get_upcoming_high_impact
        from ..notifications.whatsapp_notifier import send_news_alert
        import MetaTrader5 as mt5

        update_news_events()

        upcoming = get_upcoming_high_impact(
            hours_ahead=8.0,
            min_impact=3,
            gold_relevant_only=True,
        )
        if not upcoming.empty:
            account_info = None
            try:
                from ..execution.live_monitor import get_equity_peak
                info = mt5.account_info()
                if info:
                    account_info = {
                        "equity": float(info.equity),
                        "peak": get_equity_peak(),
                    }
            except Exception:
                pass
            send_news_alert(upcoming, account_info=account_info)

    except Exception:
        logger.exception("job_update_news failed")
    logger.info("Scheduler: job_update_news done")


def job_news_alert() -> None:
    """Check for upcoming high-impact events and send WhatsApp alert if within 30 min."""
    try:
        from ..data.news_collector import get_upcoming_high_impact
        from ..notifications.whatsapp_notifier import send_news_alert
        import MetaTrader5 as mt5

        upcoming = get_upcoming_high_impact(
            hours_ahead=1.0,
            min_impact=3,
            gold_relevant_only=True,
        )
        if upcoming.empty:
            return

        account_info = None
        try:
            from ..execution.live_monitor import get_equity_peak
            info = mt5.account_info()
            if info:
                account_info = {
                    "equity": float(info.equity),
                    "peak": get_equity_peak(),
                }
        except Exception:
            pass

        sent = send_news_alert(upcoming, account_info=account_info)
        if sent:
            logger.info(
                "WhatsApp news alert sent: %d upcoming high-impact events", len(upcoming)
            )

    except Exception:
        logger.exception("job_news_alert failed")


# ---------------------------------------------------------------------------
# Strategy degradation
# ---------------------------------------------------------------------------

def _apply_live_degradation(pool) -> None:
    """Demote clearly underperforming active strategies based on live PnL."""
    live_stats = load_all_strategy_stats()
    if not live_stats:
        return

    for name, rec in live_stats.items():
        pool_rec = pool.strategies.get(name)
        if not pool_rec or pool_rec.status != "active":
            continue

        stats = pool_rec.stats or {}
        bt_ret = float(stats.get("return_pct", 0.0) or 0.0)
        bt_sharpe = float(stats.get("sharpe_ratio", 0.0) or 0.0)

        if bt_ret <= 0 or bt_sharpe <= 0.3:
            continue

        if rec.num_trades < max(10, MAX_RECENT_TRADES):
            continue

        initial_eq = float(stats.get("initial_equity", 1.0) or 1.0)
        live_ret_total_pct = rec.total_pnl / max(initial_eq, 1.0) * 100.0
        live_ret_recent_pct = (
            sum(rec.recent_pnls) / max(initial_eq, 1.0) * 100.0
            if rec.recent_pnls else 0.0
        )

        if (
            live_ret_recent_pct < -3.0
            or live_ret_recent_pct < 0.25 * bt_ret
        ):
            pool_rec.status = "candidate"
            logger.warning(
                "Degradation: demoting %s to candidate "
                "(bt_ret=%.2f%% bt_sharpe=%.2f "
                "live_total=%.2f%% live_recent=%.2f%% trades=%d)",
                name, bt_ret, bt_sharpe,
                live_ret_total_pct, live_ret_recent_pct, rec.num_trades,
            )
            try:
                from ..notifications.whatsapp_notifier import send_strategy_degradation_alert
                send_strategy_degradation_alert(
                    strategy_name=name,
                    recent_avg_pnl=rec.recent_avg_pnl,
                    total_pnl=rec.total_pnl,
                    new_status="candidate",
                )
            except Exception:
                logger.exception("Failed to send strategy degradation WhatsApp alert")


# ---------------------------------------------------------------------------
# Memory helpers
# ---------------------------------------------------------------------------

def _memory_is_clearly_bad(
    candidate, memory: ResearchMemory, symbol: str, timeframe: str
) -> bool:
    """Veto only obviously bad pattern families using ResearchMemory."""
    try:
        params = getattr(candidate, "params", {}) or {}
        query_text = "\n".join([
            f"symbol={symbol}",
            f"timeframe={timeframe}",
            f"long_entry={getattr(candidate, 'long_entry_rule', '')}",
            f"short_entry={getattr(candidate, 'short_entry_rule', '')}",
            f"exit={getattr(candidate, 'exit_rule', '')}",
            f"sl_atr={getattr(candidate, 'sl_atr_mult', '')}",
            f"tp_atr={getattr(candidate, 'tp_atr_mult', '')}",
            f"regime={params.get('regime_type', '')}",
        ])
        neighbors = memory.query_similar_strategies(
            symbol=symbol, timeframe=timeframe,
            text=query_text, n_results=10,
        )
    except Exception as e:
        logger.exception("ResearchMemory veto query failed for %s: %s",
                         getattr(candidate, "name", "?"), e)
        return False

    if not neighbors:
        return False

    total = len(neighbors)
    if total < 5:
        return False

    bad = 0
    for nb in neighbors:
        sharpe = nb.get("stat_sharpe_ratio")
        pf = nb.get("stat_profit_factor")
        ret_pct = nb.get("stat_return_pct")
        wf_sharpe = nb.get("stat_wf_overall_sharpe")

        is_bad = False
        if sharpe is not None and sharpe < 0.0:
            is_bad = True
        if pf is not None and pf < 1.0:
            is_bad = True
        if ret_pct is not None and ret_pct < -5.0:
            is_bad = True
        if wf_sharpe is not None and wf_sharpe < 0.05:
            is_bad = True
        if is_bad:
            bad += 1

    if bad >= 5 and bad / float(total) >= 0.7:
        logger.info(
            "Memory veto: skipping candidate %s (bad_neighbors=%d/%d)",
            getattr(candidate, "name", "<unnamed>"), bad, total,
        )
        return True

    return False


# ---------------------------------------------------------------------------
# Research job
# ---------------------------------------------------------------------------

def job_research_strategies() -> None:
    """Generate/evolve strategies, backtest, evaluate, update pool + memory."""
    logger.info("Scheduler: job_research_strategies start")
    pool = load_pool()
    memory = ResearchMemory()

    for symbol in MANAGED_SYMBOLS:
        try:
            feat = load_features(symbol, TIMEFRAME)
        except FileNotFoundError:
            logger.warning("No features for %s %s; skipping research", symbol, TIMEFRAME)
            continue
        except Exception as e:
            logger.exception("Failed to load features for %s: %s", symbol, e)
            continue

        def _memory_bonus_for_parent(rec) -> float:
            try:
                strat_text = f"symbol={rec.symbol}\ntimeframe={rec.timeframe}"
                try:
                    path = BASE_DIR / "strategies" / "generated" / f"{rec.name}.json"
                    strat_obj = load_strategy(path)
                    params = getattr(strat_obj, "params", {}) or {}
                    strat_text = "\n".join([
                        f"symbol={rec.symbol}",
                        f"timeframe={rec.timeframe}",
                        f"long_entry={getattr(strat_obj, 'long_entry_rule', '')}",
                        f"short_entry={getattr(strat_obj, 'short_entry_rule', '')}",
                        f"exit={getattr(strat_obj, 'exit_rule', '')}",
                        f"sl_atr={getattr(strat_obj, 'sl_atr_mult', '')}",
                        f"tp_atr={getattr(strat_obj, 'tp_atr_mult', '')}",
                        f"regime={params.get('regime_type', '')}",
                    ])
                except Exception:
                    pass

                neighbors = memory.query_similar_strategies(
                    symbol=rec.symbol, timeframe=rec.timeframe,
                    text=strat_text, n_results=10,
                )
            except Exception as e:
                logger.error("Memory bonus query failed for %s: %s", rec.name, e)
                return 0.0

            if not neighbors:
                return 0.0

            good = bad = 0
            for nb in neighbors:
                sharpe = nb.get("stat_sharpe_ratio")
                pf = nb.get("stat_profit_factor")
                ret_pct = nb.get("stat_return_pct")
                if sharpe is None and pf is None and ret_pct is None:
                    continue
                is_good = is_bad = False
                if sharpe is not None:
                    if sharpe > 0.3: is_good = True
                    elif sharpe < 0.0: is_bad = True
                if pf is not None:
                    if pf > 1.1: is_good = True
                    elif pf < 1.0: is_bad = True
                if ret_pct is not None:
                    if ret_pct > 0.0: is_good = True
                    elif ret_pct < -5.0: is_bad = True
                if is_good: good += 1
                if is_bad: bad += 1

            total = good + bad
            if total == 0:
                return 0.0
            balance = (good - bad) / float(total)
            bonus = max(-0.2, min(0.2, balance * 0.2))
            if bonus != 0.0:
                logger.info(
                    "Memory bonus for %s: score=%.3f good=%d bad=%d bonus=%.3f",
                    rec.name, rec.score, good, bad, bonus,
                )
            return bonus

        parent_candidates = [
            rec for rec in pool.strategies.values()
            if rec.symbol == symbol and rec.timeframe == TIMEFRAME
        ]
        scored_parents = []
        for rec in parent_candidates:
            bonus = _memory_bonus_for_parent(rec)
            scored_parents.append((rec.score + bonus, rec))
        scored_parents.sort(key=lambda x: x[0], reverse=True)
        parent_records = [rec for _, rec in scored_parents[:20]]

        existing_strats = []
        for rec in parent_records:
            path = BASE_DIR / "strategies" / "generated" / f"{rec.name}.json"
            try:
                strat = load_strategy(path)
                existing_strats.append((strat, rec.score))
            except Exception as e:
                logger.exception("Failed to load parent %s: %s", rec.name, e)

        new_population = evolve_population(symbol, TIMEFRAME, existing_strats)
        save_population(new_population)

        for strat in new_population:
            try:
                if _memory_is_clearly_bad(strat, memory, symbol, TIMEFRAME):
                    continue

                result = run_backtest(feat, strat, regime_column="regime")
                eval_result = evaluate_strategy(result.stats)

                num_trades = eval_result.get("num_trades", 0.0)
                if num_trades < 50:
                    logger.info(
                        "Skipping %s — low trade count (%.0f < 50)", strat.name, num_trades
                    )
                    continue

                pf = float(eval_result.get("profit_factor", 0.0) or 0.0)
                sharpe = float(eval_result.get("sharpe_ratio", 0.0) or 0.0)
                if pf < 1.05 or sharpe < 0.15:
                    logger.info(
                        "Skipping %s — weak perf (pf=%.2f sharpe=%.2f)", strat.name, pf, sharpe
                    )
                    continue

                wf = walk_forward_test(feat, strat)
                mc = monte_carlo_pnl(result.trades, n_runs=200)

                eval_result["wf_overall_sharpe"] = (
                    wf.get("aggregate", {}).get("overall_sharpe", 0.0)
                )
                eval_result["wf_overall_max_drawdown_pct"] = (
                    wf.get("aggregate", {}).get("overall_max_drawdown_pct", 0.0)
                )

                # Persist basic identity so promotion logic can be symbol-aware
                # (e.g. relax trend filters for BTC range traders).
                eval_result["symbol"] = getattr(strat, "symbol", "")
                eval_result["timeframe"] = getattr(strat, "timeframe", "")

                eval_result.update(mc)

                wf_sharpe = float(eval_result.get("wf_overall_sharpe", 0.0) or 0.0)
                if wf_sharpe < 0.05:
                    logger.info(
                        "Skipping %s — weak WF sharpe (%.3f < 0.05)", strat.name, wf_sharpe
                    )
                    continue

                def _should_promote(stats: dict) -> bool:
                    ex = stats.get("strategy_explain", {}) or {}
                    regime = ex.get("regime_pnl", {}) or {}
                    trend_ret = (
                        regime.get("trending_up", {}).get("return_pct", 0.0)
                        + regime.get("trending_down", {}).get("return_pct", 0.0)
                    )
                    range_ret = regime.get("ranging", {}).get("return_pct", 0.0)

                    # BTC range traders often have near-zero trending returns but
                    # excellent overall robustness. For BTC symbols we therefore
                    # relax the hard requirement on trend_ret and only enforce it
                    # for non-BTC pairs.
                    symbol = str(stats.get("symbol", "") or "").upper()
                    is_btc = symbol.startswith("BTC")

                    trend_gate_ok = trend_ret > 0.0 if not is_btc else True

                    return (
                        stats.get("num_trades", 0.0) >= 50
                        and stats.get("return_pct", 0.0) > 0.0
                        and stats.get("max_drawdown_pct", 100.0) <= 20.0
                        and stats.get("profit_factor", 0.0) >= 1.2
                        and trend_gate_ok
                        and range_ret > -5.0
                    )

                ex = eval_result.get("strategy_explain", {}) or {}
                regime = ex.get("regime_pnl", {}) or {}
                trend_ret = (
                    regime.get("trending_up", {}).get("return_pct", 0.0)
                    + regime.get("trending_down", {}).get("return_pct", 0.0)
                )
                range_ret = regime.get("ranging", {}).get("return_pct", 0.0)
                num_trades = eval_result.get("num_trades", 0.0) or 0.0

                if _should_promote(eval_result) and wf_sharpe >= 0.5:
                    status = "active"
                elif eval_result.get("accepted") and wf_sharpe >= 0.2:
                    if num_trades >= 20 and trend_ret > 0.0 and range_ret > -10.0:
                        status = "exploratory"
                    else:
                        status = "candidate"
                else:
                    status = "disabled"

                # Persist core strategy rules into stats["strategy"] so that
                # StrategyPool._rebuild_fp_map() can reconstruct structural
                # fingerprints across process restarts. Without this, all
                # records share an empty/None strategy dict and deduplication
                # silently degrades.
                eval_result["strategy"] = {
                    "long_entry_rule": getattr(strat, "long_entry_rule", "") or "",
                    "short_entry_rule": getattr(strat, "short_entry_rule", "") or "",
                    "exit_rule": getattr(strat, "exit_rule", "") or "",
                    "sl_atr_mult": getattr(strat, "sl_atr_mult", ""),
                    "tp_atr_mult": getattr(strat, "tp_atr_mult", ""),
                }

                pool.upsert_strategy(
                    strategy=strat,
                    stats=eval_result,
                    score=eval_result.get("score", 0.0),
                    status=status,
                )
                memory.store_strategy_result(
                    strategy_name=strat.name,
                    symbol=strat.symbol,
                    timeframe=strat.timeframe,
                    stats=eval_result,
                )

            except Exception as e:
                logger.exception("Research error for %s: %s", strat.name, e)

    _apply_live_degradation(pool)
    pool.prune(max_inactive=200)
    save_pool(pool)
    logger.info("Scheduler: job_research_strategies done")


# ---------------------------------------------------------------------------
# Signal execution
# ---------------------------------------------------------------------------

def job_execute_signals() -> None:
    """Generate and execute signals for active strategies."""
    logger.info("Scheduler: job_execute_signals start")
    pool = load_pool()
    risk_perc = min(2.0, risk_config.max_risk_per_trade_pct)

    from ..research.features import load_features

    for symbol in MANAGED_SYMBOLS:
        try:
            feat = load_features(symbol, TIMEFRAME)
        except FileNotFoundError:
            logger.warning("No features for %s %s; skipping signals", symbol, TIMEFRAME)
            continue
        except Exception as e:
            logger.exception("Failed to load features for %s: %s", symbol, e)
            continue

        # ---- News lockout check ----
        try:
            latest = feat.iloc[-1]
            if bool(latest.get("in_news_lockout", False)):
                logger.warning(
                    "News lockout active for %s %s — skipping signal generation",
                    symbol, TIMEFRAME,
                )
                continue
        except Exception:
            pass

        active_strats = [
            rec for rec in pool.strategies.values()
            if rec.symbol == symbol
            and rec.timeframe == TIMEFRAME
            and rec.status == "active"
        ]

        if not active_strats:
            logger.warning(
                "No active strategies in pool for %s %s — skipping execution",
                symbol, TIMEFRAME,
            )
            continue

        # ------------------------------------------------------------------ #
        # Stage 1 — Deduplicate clones by RULE STRINGS                        #
        #                                                                      #
        # FIX: Previously fingerprinted by backtest stats (sharpe, pf, etc.)  #
        # which allowed strategies with identical entry/exit rules but         #
        # different names to all fire the same signal simultaneously,          #
        # creating a concentration blast (e.g. 5 identical shorts in 1 bar).  #
        #                                                                      #
        # New fingerprint: (long_entry_rule, short_entry_rule, exit_rule,      #
        # stop_loss_pips) — two strategies are clones if they fire the same    #
        # signal under the same conditions with the same SL.                  #
        #                                                                      #
        # Keep the one with the highest WF Sharpe per clone cluster.          #
        # Fall back to stats-based fingerprint if strategy JSON cannot be     #
        # loaded (e.g. file deleted after pool upsert).                       #
        # ------------------------------------------------------------------ #
        strats_by_wf = sorted(
            active_strats,
            key=lambda r: float((r.stats or {}).get("wf_overall_sharpe", 0) or 0),
            reverse=True,
        )

        seen_fps: set = set()
        unique_strats = []
        _strat_base_dir = BASE_DIR / "strategies" / "generated"
        _rule_cache: dict = {}  # name → fingerprint tuple, avoid re-loading same file

        for rec in strats_by_wf:
            if rec.name in _rule_cache:
                fp = _rule_cache[rec.name]
            else:
                try:
                    _path = _strat_base_dir / f"{rec.name}.json"
                    _s = load_strategy(_path)
                    fp = (
                        str(getattr(_s, "long_entry_rule", "") or ""),
                        str(getattr(_s, "short_entry_rule", "") or ""),
                        str(getattr(_s, "exit_rule", "") or ""),
                        round(float(getattr(_s, "stop_loss_pips", 0) or 0), 0),
                    )
                except Exception:
                    # Fallback: stats-based fingerprint if file not loadable
                    s = rec.stats or {}
                    fp = (
                        round(float(s.get("sharpe_ratio", 0) or 0), 4),
                        round(float(s.get("profit_factor", 0) or 0), 4),
                        round(float(s.get("return_pct", 0) or 0), 4),
                        int(s.get("num_trades", 0) or 0),
                    )
                _rule_cache[rec.name] = fp

            if fp not in seen_fps:
                seen_fps.add(fp)
                unique_strats.append(rec)

        # ------------------------------------------------------------------ #
        # Stage 2 — Quality gate                                              #
        # ------------------------------------------------------------------ #
        def _passes_quality(rec) -> bool:
            s = rec.stats or {}
            ex = s.get("strategy_explain", {}) or {}
            risk_beh = ex.get("risk_behavior", {}) or {}
            wf  = float(s.get("wf_overall_sharpe", 0) or 0)
            dd  = abs(float(s.get("max_drawdown_pct", 0) or 0))
            tr  = int(s.get("num_trades", 0) or 0)
            cls = int(risk_beh.get("max_consecutive_losses", 0) or 0)
            return (
                wf  >= EXEC_MIN_WF_SHARPE
                and dd  <= EXEC_MAX_DD_PCT
                and tr  >= EXEC_MIN_TRADES
                and cls <= EXEC_MAX_CONSEC_LOSS
            )

        quality_strats = [r for r in unique_strats if _passes_quality(r)]

        # ------------------------------------------------------------------ #
        # Stage 3 — Regime-adaptive sort + cap to MAX_EXECUTION_POOL          #
        # ------------------------------------------------------------------ #
        current_regime = "unknown"
        current_session = _current_session()
        try:
            current_regime = str(feat.iloc[-1].get("regime", "unknown"))
        except Exception:
            pass

        final_strats = sorted(
            quality_strats,
            key=lambda r: _hybrid_regime_score(r, current_regime, current_session),
            reverse=True,
        )[:MAX_EXECUTION_POOL]

        if len(active_strats) != len(final_strats):
            n_dupes = len(active_strats) - len(unique_strats)
            n_filtered = len(unique_strats) - len(quality_strats)
            n_capped = max(0, len(quality_strats) - len(final_strats))
            logger.info(
                "Execution pool %s %s [regime=%s session=%s]: "
                "%d active → %d unique (-%d clones) "
                "→ %d quality (-%d threshold) → %d final (-%d capped)",
                symbol, TIMEFRAME, current_regime, current_session,
                len(active_strats), len(unique_strats), n_dupes,
                len(quality_strats), n_filtered,
                len(final_strats), n_capped,
            )

        if not final_strats:
            logger.warning(
                "No strategies passed execution filter for %s %s "
                "(active=%d unique=%d quality=%d) — "
                "consider relaxing EXEC_MIN_WF_SHARPE or EXEC_MAX_DD_PCT",
                symbol, TIMEFRAME,
                len(active_strats), len(unique_strats), len(quality_strats),
            )
            continue

        low_edge = [r for r in final_strats if r.score <= MINIMUM_EDGE_FOR_EXECUTION]
        if low_edge:
            logger.warning(
                "Low/negative edge strategies in execution pool for %s %s: %s",
                symbol, TIMEFRAME,
                {r.name: round(r.score, 3) for r in low_edge},
            )

        logger.info(
            "Executing signals for %s %s [regime=%s session=%s] — %d strategies "
            "(hybrid_score range: %.2f – %.2f)",
            symbol, TIMEFRAME, current_regime, current_session, len(final_strats),
            _hybrid_regime_score(final_strats[-1], current_regime, current_session),
            _hybrid_regime_score(final_strats[0], current_regime, current_session),
        )

        # Build a temporary pool view containing only final_strats
        from ..strategies.pool import StrategyPool
        filtered_pool = StrategyPool()
        filtered_pool.strategies = {r.name: r for r in final_strats}

        results, summary = execute_signals_for_symbol(
            symbol, TIMEFRAME, feat, filtered_pool, risk_perc=risk_perc
        )

        if results:
            for sig, reason in results:
                logger.info(
                    "Signal result: strategy=%s symbol=%s dir=%s reason=%s",
                    sig.strategy.name, symbol, sig.direction, reason,
                )
        else:
            if summary.get("blocked_daily_limits"):
                logger.info("No signals for %s %s — blocked by daily limits", symbol, TIMEFRAME)
            elif summary.get("no_strategies_in_pool"):
                logger.info("No signals for %s %s — no active/exploratory strategies", symbol, TIMEFRAME)
            elif summary.get("no_strategies_with_edge"):
                logger.info("No signals for %s %s — no strategies passed regime/edge filters", symbol, TIMEFRAME)
            else:
                logger.info("No signals for %s %s — entry conditions not met", symbol, TIMEFRAME)

    logger.info("Scheduler: job_execute_signals done")


# ---------------------------------------------------------------------------
# Live monitor
# ---------------------------------------------------------------------------

def job_live_monitor() -> None:
    """Update live stats, enforce portfolio-level safety, and snapshot open trades."""
    logger.info("Scheduler: job_live_monitor start")
    try:
        update_live_stats()
    except Exception as e:
        logger.exception("job_live_monitor error: %s", e)

    try:
        from ..execution.live_observer import snapshot_open_trades
        snapshot_open_trades()
    except Exception:
        logger.exception("job_live_monitor snapshot_open_trades error")

    logger.info("Scheduler: job_live_monitor done")


# ---------------------------------------------------------------------------
# Scheduler lifecycle
# ---------------------------------------------------------------------------

def start_scheduler() -> BackgroundScheduler:
    if not scheduler_config.enable_scheduler:
        logger.warning("Scheduler is disabled via config")
        return BackgroundScheduler()

    logger.info("Starting MT5 and scheduler...")
    initialize_mt5()

    sched = BackgroundScheduler(timezone="UTC")

    # Every 5 min: OHLC + features + regimes
    sched.add_job(job_update_data, "interval", minutes=5, id="update_data")

    # Every 30 min: research / evolve / backtest
    sched.add_job(job_research_strategies, "interval", minutes=30, id="research_strategies")

    # Every 5 min: live signal execution (with news lockout)
    sched.add_job(job_execute_signals, "interval", minutes=5, id="execute_signals")

    # Every 5 min: equity monitor + circuit breaker
    sched.add_job(job_live_monitor, "interval", minutes=5, id="live_monitor")

    # Daily 06:00 UTC: fetch Forex Factory calendar
    sched.add_job(job_update_news, "cron", hour=6, minute=0, id="update_news")

    # Every 5 min: WhatsApp alert check for upcoming high-impact events
    sched.add_job(job_news_alert, "interval", minutes=5, id="news_alert")

    sched.start()
    logger.info("Scheduler started with %d jobs", len(sched.get_jobs()))
    return sched


def shutdown_scheduler(sched: BackgroundScheduler) -> None:
    logger.info("Shutting down scheduler and MT5...")
    sched.shutdown(wait=False)
    shutdown_mt5()


if __name__ == "__main__":
    sched = start_scheduler()
    try:
        while True:
            _time.sleep(60)
    except KeyboardInterrupt:
        logger.info("KeyboardInterrupt received; shutting down")
        shutdown_scheduler(sched)