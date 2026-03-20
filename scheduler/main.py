from __future__ import annotations

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
# MANAGED_SYMBOLS = ["XAUUSDm", "BTCUSDm"]
MANAGED_SYMBOLS = ["XAUUSDm"]
TIMEFRAME = "M15"

# Minimum edge score for a strategy to be allowed to execute live signals.
# Strategies with score <= this value will be flagged but still pass through
# to execute_signals_for_symbol (which has its own regime-based guard).
# Set to 0.0 to only warn; raise to e.g. 0.5 to hard-block low-edge strategies.
MINIMUM_EDGE_FOR_EXECUTION = 0.0


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


def _apply_live_degradation(pool) -> None:
    """Adjust strategy statuses based on simple live performance heuristics.

    Uses aggregated per-strategy PnL from `execution/strategy_live_stats.json`.
    This is intentionally conservative: it only *downgrades* strategies that
    are clearly underperforming live vs their backtest expectations.
    """
    live_stats = load_all_strategy_stats()
    if not live_stats:
        return

    for name, rec in live_stats.items():
        pool_rec = pool.strategies.get(name)
        if not pool_rec:
            continue
        if pool_rec.status != "active":
            continue

        stats = pool_rec.stats or {}
        bt_ret = float(stats.get("return_pct", 0.0) or 0.0)
        bt_sharpe = float(stats.get("sharpe_ratio", 0.0) or 0.0)

        # Only consider strategies that looked decent in backtest
        if bt_ret <= 0 or bt_sharpe <= 0.3:
            continue

        # Require a minimum amount of live data before judging
        if rec.num_trades < max(10, MAX_RECENT_TRADES):
            continue

        initial_eq = float(stats.get("initial_equity", 1.0) or 1.0)
        live_ret_total_pct = rec.total_pnl / max(initial_eq, 1.0) * 100.0
        live_ret_recent_pct = (
            sum(rec.recent_pnls) / max(initial_eq, 1.0) * 100.0
            if rec.recent_pnls
            else 0.0
        )

        if (
            live_ret_recent_pct < -3.0
            or live_ret_recent_pct < 0.25 * bt_ret
        ):
            old_status = pool_rec.status
            pool_rec.status = "candidate"
            logger.warning(
                "Degradation: demoting %s from %s to candidate "
                "(bt_ret=%.2f%%, bt_sharpe=%.2f, "
                "live_total_ret=%.2f%%, live_recent_ret=%.2f%%, "
                "live_trades=%d, recent_window=%d)",
                name,
                old_status,
                bt_ret,
                bt_sharpe,
                live_ret_total_pct,
                live_ret_recent_pct,
                rec.num_trades,
                len(rec.recent_pnls),
            )


def _memory_is_clearly_bad(
    candidate, memory: ResearchMemory, symbol: str, timeframe: str
) -> bool:
    """Heuristic filter using ResearchMemory to skip clearly bad pattern families.

    AGGRESSIVE MODE: significantly relaxed. Only veto a candidate if
    *all* sufficiently similar neighbors in memory are clearly terrible.
    This allows much wider exploration while still blocking obviously
    toxic pattern families.
    """
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

        res = memory.query_similar(
            text=query_text,
            n_results=8,
            where={"symbol": symbol, "timeframe": timeframe},
        )
    except Exception as e:
        logger.exception("ResearchMemory query failed for %s: %s", candidate.name, e)
        return False

    docs = (res.get("documents") or [[]])[0] or []
    if not docs:
        return False

    bad_votes = 0
    total_votes = 0

    for doc in docs:
        sharpe = None
        pf = None
        ret_pct = None
        for line in doc.splitlines():
            if line.startswith("sharpe_ratio="):
                _, v = line.split("=", 1)
                try:
                    sharpe = float(str(v).strip())
                except Exception:
                    sharpe = None
            elif line.startswith("profit_factor="):
                _, v = line.split("=", 1)
                try:
                    pf = float(str(v).strip())
                except Exception:
                    pf = None
            elif line.startswith("return_pct="):
                _, v = line.split("=", 1)
                try:
                    ret_pct = float(str(v).strip())
                except Exception:
                    ret_pct = None

        if sharpe is None and pf is None and ret_pct is None:
            continue

        total_votes += 1
        if (
            (sharpe is not None and sharpe < 0.0)
            or (pf is not None and pf < 1.0)
            or (ret_pct is not None and ret_pct < -5.0)
        ):
            bad_votes += 1

    # If we barely have any signal, don't veto
    if total_votes < 3:
        return False

    # AGGRESSIVE: only skip if *every* neighbor looks bad
    if bad_votes >= total_votes:
        logger.info(
            "Memory filter (aggressive): skipping candidate %s (bad_neighbors=%d/%d)",
            candidate.name,
            bad_votes,
            total_votes,
        )
        return True

    return False


def job_research_strategies() -> None:
    """Generate/evolve strategies, backtest, evaluate, and update pool + memory."""
    logger.info("Scheduler: job_research_strategies start")
    pool = load_pool()
    memory = ResearchMemory()

    for symbol in MANAGED_SYMBOLS:
        try:
            feat = load_features(symbol, TIMEFRAME)
        except FileNotFoundError:
            logger.warning(
                "No features found for %s %s; skipping research", symbol, TIMEFRAME
            )
            continue
        except Exception as e:
            logger.exception("Failed to load features for %s: %s", symbol, e)
            continue

        from ..strategies.generator import load_strategy

        def _memory_bonus_for_parent(rec) -> float:
            """Compute a small memory-based bonus for a parent candidate.

            Uses ResearchMemory to query similar strategies and aggregates
            neighbor quality from stored ``stat_*`` fields. The bonus is
            intentionally small so it nudges but does not dominate the base
            backtest score.
            """
            try:
                # Build a rich query text from strategy rules.
                # Load the strategy file so we have the actual rule strings.
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
                    pass  # fall back to minimal text above

                neighbors = memory.query_similar_strategies(
                    symbol=rec.symbol,
                    timeframe=rec.timeframe,
                    text=strat_text,
                    n_results=10,
                )
            except Exception as e:
                logger.error(
                    "Memory bonus: query failed for parent %s: %s", rec.name, e
                )
                return 0.0

            if not neighbors:
                return 0.0

            good = 0
            bad = 0
            for nb in neighbors:
                sharpe = nb.get("stat_sharpe_ratio")
                pf = nb.get("stat_profit_factor")
                ret_pct = nb.get("stat_return_pct")

                if sharpe is None and pf is None and ret_pct is None:
                    continue

                is_good = False
                is_bad = False

                if sharpe is not None:
                    if sharpe > 0.3:
                        is_good = True
                    elif sharpe < 0.0:
                        is_bad = True

                if pf is not None:
                    if pf > 1.1:
                        is_good = True
                    elif pf < 1.0:
                        is_bad = True

                if ret_pct is not None:
                    if ret_pct > 0.0:
                        is_good = True
                    elif ret_pct < -5.0:
                        is_bad = True

                if is_good:
                    good += 1
                if is_bad:
                    bad += 1

            total = good + bad
            if total == 0:
                return 0.0

            balance = (good - bad) / float(total)
            bonus = max(-0.2, min(0.2, balance * 0.2))

            if bonus != 0.0:
                logger.info(
                    "Memory bonus for parent %s: base_score=%.3f good=%d bad=%d bonus=%.3f",
                    rec.name,
                    rec.score,
                    good,
                    bad,
                    bonus,
                )
            return bonus

        parent_candidates = [
            rec
            for rec in pool.strategies.values()
            if rec.symbol == symbol and rec.timeframe == TIMEFRAME
        ]

        scored_parents = []
        for rec in parent_candidates:
            bonus = _memory_bonus_for_parent(rec)
            hybrid_score = rec.score + bonus
            scored_parents.append((hybrid_score, rec))

        scored_parents.sort(key=lambda x: x[0], reverse=True)
        top_scored = scored_parents[:20]
        parent_records = [rec for _, rec in top_scored]

        existing_strats = []
        for rec in parent_records:
            path = BASE_DIR / "strategies" / "generated" / f"{rec.name}.json"
            try:
                strat = load_strategy(path)
                existing_strats.append((strat, rec.score))
            except Exception as e:
                logger.exception(
                    "Failed to load parent strategy %s from %s: %s",
                    rec.name,
                    path,
                    e,
                )

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
                        "Skipping strategy %s due to low trade count "
                        "(Phase 3 floor=50): %.0f",
                        strat.name,
                        num_trades,
                    )
                    continue

                pf = float(eval_result.get("profit_factor", 0.0) or 0.0)
                sharpe = float(eval_result.get("sharpe_ratio", 0.0) or 0.0)
                if pf < 1.05 or sharpe < 0.15:
                    logger.info(
                        "Skipping strategy %s due to weak performance "
                        "(AGGRESSIVE Phase 3 floors pf>=1.05, sharpe>=0.15): "
                        "pf=%.2f sharpe=%.2f",
                        strat.name,
                        pf,
                        sharpe,
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
                eval_result.update(mc)

                wf_sharpe = float(eval_result.get("wf_overall_sharpe", 0.0) or 0.0)
                if wf_sharpe < 0.05:
                    logger.info(
                        "Skipping strategy %s due to very weak walk-forward Sharpe "
                        "(AGGRESSIVE wf_sharpe=%.3f < 0.05)",
                        strat.name,
                        wf_sharpe,
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
                    return (
                        stats.get("num_trades", 0.0) >= 50
                        and stats.get("return_pct", 0.0) > 0.0
                        and stats.get("max_drawdown_pct", 100.0) <= 20.0
                        and stats.get("profit_factor", 0.0) >= 1.1
                        and trend_ret > 0.0
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

                # AGGRESSIVE promotion thresholds:
                # - Active if core stats are good and wf_sharpe >= 0.15
                # - Exploratory if accepted and wf_sharpe >= 0.08
                # - Otherwise disabled
                if _should_promote(eval_result) and wf_sharpe >= 0.15:
                    status = "active"
                elif eval_result.get("accepted") and wf_sharpe >= 0.08:
                    if num_trades >= 20 and trend_ret > 0.0 and range_ret > -10.0:
                        status = "exploratory"
                    else:
                        status = "candidate"
                else:
                    status = "disabled"

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
                logger.exception(
                    "Research error for strategy %s: %s", strat.name, e
                )

    _apply_live_degradation(pool)
    save_pool(pool)
    logger.info("Scheduler: job_research_strategies done")


def job_execute_signals() -> None:
    """Generate and execute signals for active strategies based on latest features."""
    logger.info("Scheduler: job_execute_signals start")
    pool = load_pool()
    risk_perc = min(0.5, risk_config.max_risk_per_trade_pct)

    from ..research.features import load_features

    for symbol in MANAGED_SYMBOLS:
        try:
            feat = load_features(symbol, TIMEFRAME)
        except FileNotFoundError:
            logger.warning(
                "No features for %s %s; skipping signal execution", symbol, TIMEFRAME
            )
            continue
        except Exception as e:
            logger.exception("Failed to load features for %s: %s", symbol, e)
            continue

        # Audit pool health before execution
        active_strats = [
            rec
            for rec in pool.strategies.values()
            if rec.symbol == symbol
            and rec.timeframe == TIMEFRAME
            and rec.status == "active"
        ]

        if not active_strats:
            logger.warning(
                "No active strategies in pool for %s %s — skipping execution",
                symbol,
                TIMEFRAME,
            )
            continue

        low_edge = [r for r in active_strats if r.score <= MINIMUM_EDGE_FOR_EXECUTION]
        if low_edge:
            logger.warning(
                "Low/negative edge strategies active for %s %s: %s "
                "(scores: %s) — consider triggering retraining",
                symbol,
                TIMEFRAME,
                [r.name for r in low_edge],
                {r.name: round(r.score, 3) for r in low_edge},
            )

        logger.info(
            "Executing signals for %s %s — %d active strategies "
            "(scores: %s)",
            symbol,
            TIMEFRAME,
            len(active_strats),
            {r.name: round(r.score, 3) for r in active_strats},
        )

        results, summary = execute_signals_for_symbol(
            symbol, TIMEFRAME, feat, pool, risk_perc=risk_perc
        )

        if results:
            for sig, reason in results:
                logger.info(
                    "Signal result: strategy=%s symbol=%s dir=%s reason=%s",
                    sig.strategy.name,
                    symbol,
                    sig.direction,
                    reason,
                )
        else:
            if summary.get("blocked_daily_limits"):
                logger.info(
                    "No signals executed for %s %s — blocked by daily limits",
                    symbol,
                    TIMEFRAME,
                )
            elif summary.get("no_strategies_in_pool"):
                logger.info(
                    "No signals executed for %s %s — no active/exploratory strategies in pool",
                    symbol,
                    TIMEFRAME,
                )
            elif summary.get("no_strategies_with_edge"):
                logger.info(
                    "No signals executed for %s %s — no strategies passed regime/edge filters",
                    symbol,
                    TIMEFRAME,
                )
            else:
                no_entry_active = summary.get("no_entry_active", False)
                no_entry_exploratory = summary.get("no_entry_exploratory", False)

                if no_entry_active and not no_entry_exploratory:
                    logger.info(
                        "No signals executed for %s %s — entry conditions not met (active strategies)",
                        symbol,
                        TIMEFRAME,
                    )
                elif no_entry_exploratory and not no_entry_active:
                    logger.info(
                        "No signals executed for %s %s — entry conditions not met (exploratory strategies)",
                        symbol,
                        TIMEFRAME,
                    )
                elif no_entry_active and no_entry_exploratory:
                    logger.info(
                        "No signals executed for %s %s — entry conditions not met (active + exploratory)",
                        symbol,
                        TIMEFRAME,
                    )
                else:
                    logger.info(
                        "No signals executed for %s %s — see execute_signals_for_symbol logs for details",
                        symbol,
                        TIMEFRAME,
                    )

    logger.info("Scheduler: job_execute_signals done")


def job_live_monitor() -> None:
    """Update live stats and enforce basic portfolio-level safety."""
    logger.info("Scheduler: job_live_monitor start")
    try:
        update_live_stats()
    except Exception as e:
        logger.exception("job_live_monitor error: %s", e)
    logger.info("Scheduler: job_live_monitor done")


def start_scheduler() -> BackgroundScheduler:
    if not scheduler_config.enable_scheduler:
        logger.warning("Scheduler is disabled via config")
        return BackgroundScheduler()

    logger.info("Starting MT5 and scheduler...")
    initialize_mt5()

    sched = BackgroundScheduler(timezone="UTC")

    # Every 5 minutes: update data/features/regimes
    sched.add_job(job_update_data, "interval", minutes=5, id="update_data")

    # Every 30 minutes: research/evaluate/evolve strategies
    sched.add_job(
        job_research_strategies, "interval", minutes=30, id="research_strategies"
    )

    # Every 5 minutes: generate/execute signals from active strategies
    sched.add_job(
        job_execute_signals, "interval", minutes=5, id="execute_signals"
    )

    # Every 5 minutes: live monitoring
    sched.add_job(job_live_monitor, "interval", minutes=5, id="live_monitor")

    sched.start()
    logger.info("Scheduler started")
    return sched


def shutdown_scheduler(sched: BackgroundScheduler) -> None:
    logger.info("Shutting down scheduler and MT5...")
    sched.shutdown(wait=False)
    shutdown_mt5()


if __name__ == "__main__":
    sched = start_scheduler()
    try:
        import time

        while True:
            time.sleep(60)
    except KeyboardInterrupt:
        logger.info("KeyboardInterrupt received; shutting down")
        shutdown_scheduler(sched)