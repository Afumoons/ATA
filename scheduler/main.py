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
        live_ret_recent_pct = sum(rec.recent_pnls) / max(initial_eq, 1.0) * 100.0 if rec.recent_pnls else 0.0

        # Simple degradation rules (conservative):
        # - recent live return clearly negative, OR
        # - recent live return far below backtest expectation.
        if (
            live_ret_recent_pct < -3.0
            or live_ret_recent_pct < 0.25 * bt_ret
        ):
            old_status = pool_rec.status
            pool_rec.status = "candidate"
            logger.warning(
                "Degradation: demoting %s from %s to candidate (bt_ret=%.2f%%, bt_sharpe=%.2f, "
                "live_total_ret=%.2f%%, live_recent_ret=%.2f%%, live_trades=%d, recent_window=%d)",
                name,
                old_status,
                bt_ret,
                bt_sharpe,
                live_ret_total_pct,
                live_ret_recent_pct,
                rec.num_trades,
                len(rec.recent_pnls),
            )


def job_research_strategies() -> None:
    """Generate/evolve strategies, backtest, evaluate, and update pool + memory."""
    logger.info("Scheduler: job_research_strategies start")
    pool = load_pool()
    memory = ResearchMemory()

    for symbol in MANAGED_SYMBOLS:
        try:
            feat = load_features(symbol, TIMEFRAME)
        except FileNotFoundError:
            logger.warning("No features found for %s %s; skipping research", symbol, TIMEFRAME)
            continue
        except Exception as e:
            logger.exception("Failed to load features for %s: %s", symbol, e)
            continue

        # Select top parent strategies from pool for this symbol/timeframe
        from ..strategies.generator import load_strategy

        parent_records = [
            rec
            for rec in pool.strategies.values()
            if rec.symbol == symbol and rec.timeframe == TIMEFRAME
        ]
        parent_records.sort(key=lambda r: r.score, reverse=True)
        parent_records = parent_records[:20]

        existing_strats = []
        for rec in parent_records:
            path = BASE_DIR / "strategies" / "generated" / f"{rec.name}.json"
            try:
                strat = load_strategy(path)
                existing_strats.append((strat, rec.score))
            except Exception as e:
                logger.exception("Failed to load parent strategy %s from %s: %s", rec.name, path, e)

        # Evolve population for this symbol/timeframe (or random if no parents yet)
        new_population = evolve_population(symbol, TIMEFRAME, existing_strats)
        save_population(new_population)

        for strat in new_population:
            try:
                result = run_backtest(
                    feat,
                    strat,
                    regime_column="regime",
                )
                eval_result = evaluate_strategy(result.stats)

                # Skip strategies that essentially never trade (num_trades too low)
                num_trades = eval_result.get("num_trades", 0.0)
                if num_trades < 5:
                    logger.info("Skipping strategy %s due to low trade count: %.0f", strat.name, num_trades)
                    continue

                # Walk-forward
                wf = walk_forward_test(feat, strat)
                mc = monte_carlo_pnl(result.trades, n_runs=200)

                # Merge robustness stats into eval_result
                eval_result["wf_overall_sharpe"] = wf.get("aggregate", {}).get("overall_sharpe", 0.0)
                eval_result["wf_overall_max_drawdown_pct"] = wf.get("aggregate", {}).get("overall_max_drawdown_pct", 0.0)
                eval_result.update(mc)

                # Determine pool status: active / candidate / disabled
                def _should_promote(stats: dict) -> bool:
                    ex = stats.get("strategy_explain", {}) or {}
                    regime = ex.get("regime_pnl", {}) or {}
                    trend_ret = (
                        regime.get("trending_up", {}).get("return_pct", 0.0) +
                        regime.get("trending_down", {}).get("return_pct", 0.0)
                    )
                    range_ret = regime.get("ranging", {}).get("return_pct", 0.0)

                    return (
                        stats.get("num_trades", 0.0) >= 40 and
                        stats.get("return_pct", 0.0) > 0.0 and
                        stats.get("max_drawdown_pct", 100.0) <= 20.0 and
                        stats.get("profit_factor", 0.0) >= 1.1 and
                        trend_ret > 0.0 and
                        range_ret > -5.0
                    )

                if _should_promote(eval_result):
                    status = "active"
                elif eval_result.get("accepted"):
                    status = "candidate"
                else:
                    status = "disabled"

                pool.upsert_strategy(
                    strategy=strat,
                    stats=eval_result,
                    score=eval_result.get("score", 0.0),
                    status=status,
                )

                # Store research result in Chroma
                memory.store_strategy_result(
                    strategy_name=strat.name,
                    symbol=strat.symbol,
                    timeframe=strat.timeframe,
                    stats=eval_result,
                )

            except Exception as e:
                logger.exception("Research error for strategy %s: %s", strat.name, e)

    # After updating pool with latest backtest-based scores/statuses, apply
    # conservative live degradation rules based on StrategyLiveStats.
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
            logger.warning("No features for %s %s; skipping signal execution", symbol, TIMEFRAME)
            continue
        except Exception as e:
            logger.exception("Failed to load features for %s: %s", symbol, e)
            continue

        results = execute_signals_for_symbol(symbol, TIMEFRAME, feat, pool, risk_perc=risk_perc)
        for sig, reason in results:
            logger.info(
                "Signal result: strategy=%s symbol=%s dir=%s reason=%s",
                sig.strategy.name,
                symbol,
                sig.direction,
                reason,
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
    sched.add_job(job_research_strategies, "interval", minutes=30, id="research_strategies")

    # Every 5 minutes: generate/execute signals from active strategies
    sched.add_job(job_execute_signals, "interval", minutes=5, id="execute_signals")

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
    # Simple standalone runner
    sched = start_scheduler()
    try:
        import time

        while True:
            time.sleep(60)
    except KeyboardInterrupt:
        logger.info("KeyboardInterrupt received; shutting down")
        shutdown_scheduler(sched)
