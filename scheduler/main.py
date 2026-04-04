from __future__ import annotations

import time as _time
from datetime import datetime
from pathlib import Path
from collections import Counter, defaultdict

from apscheduler.schedulers.background import BackgroundScheduler

from ..logging_utils import get_logger
from ..config import scheduler_config, risk_config, canonical_symbol
from ..data.collector_mt5 import initialize_mt5, shutdown_mt5, fetch_ohlc, save_ohlc
from ..research.features import compute_features, save_features
from ..research.regime import add_regime_column
from ..research.features import load_features
from ..strategies.live_manifest import load_live_manifest, manifest_entries_for_slot, strategy_pool_from_manifest_entries
from ..strategies.pool import load_pool, save_pool
from ..strategies.evolution import evolve_population, load_population, save_population
from ..strategies.generator import load_strategy
from ..backtests.engine import run_backtest
from ..backtests.evaluation import evaluate_strategy
from ..backtests.walkforward import walk_forward_test
from ..backtests.monte_carlo import monte_carlo_pnl
from ..execution.live_monitor import update_live_stats
from ..execution.live_decay import evaluate_live_decay, apply_live_decay_actions
from ..execution.signals import execute_signals_for_symbol
from ..execution.strategy_live_stats import load_all_strategy_stats, MAX_RECENT_TRADES
from ..vector_memory.research_memory import ResearchMemory

logger = get_logger(__name__)
BASE_DIR = Path(__file__).resolve().parents[1]

MANAGED_SYMBOLS = ["XAUUSDc","BTCUSDc","XAGUSDc"]
TIMEFRAME = "M15"
MINIMUM_EDGE_FOR_EXECUTION = 0.0

# Keep execution quality gating aligned with active-promotion requirements:
# an `active` strategy should not be routinely promoted into a live tier that
# can never pass execution gating solely because WF Sharpe uses a much harsher cutoff.
EXEC_MIN_WF_SHARPE = 0.75
EXEC_MAX_DD_PCT = 12.0
EXEC_MIN_TRADES = 160
EXEC_MAX_CONSEC_LOSS = 15
MAX_EXECUTION_POOL = 10
MAX_EXECUTION_PER_BEST_REGIME = 5
MAX_EXECUTION_PER_FAMILY = 4

SPECIALIST_EXEC_MIN_TRADES = 120
EXPLORATORY_SPECIALIST_MIN_TRADES = 100
BTC_EXEC_MIN_TRADES = 100
BTC_SPECIALIST_EXEC_MIN_TRADES = 80
BTC_EXPLORATORY_SPECIALIST_MIN_TRADES = 70
XAG_EXEC_MIN_TRADES = 80
XAG_SPECIALIST_EXEC_MIN_TRADES = 60
XAG_EXPLORATORY_SPECIALIST_MIN_TRADES = 50
XAG_BOOTSTRAP_MIN_TRADES = 20
XAG_BOOTSTRAP_MIN_PF = 1.01
XAG_BOOTSTRAP_MIN_SHARPE = 0.05
XAG_BOOTSTRAP_MIN_WF_SHARPE = 0.05

REGIME_SORT_NORM = 20.0
SESSION_SORT_NORM = 10.0

STATUS_SORT_BONUS = {
    "active": 1.15,
    "exploratory": 0.95,
    "candidate": 0.75,
    "disabled": 0.50,
}

DEFAULT_BACKTEST_KWARGS = {
    "spread": 0.35,
    "commission_per_lot": 7.0,
    "slippage_pips": 2.0,
    "max_positions_total": 1,
    "max_positions_per_strategy": 1,
}

CHEAP_PRESCREEN_BACKTEST_KWARGS = {
    "spread": 0.25,
    "commission_per_lot": 0.0,
    "slippage_pips": 0.0,
    "max_positions_total": 1,
    "max_positions_per_strategy": 1,
}

CHEAP_PRESCREEN_MIN_TRADES = 20
CHEAP_PRESCREEN_MIN_PF = 0.95
CHEAP_PRESCREEN_MIN_SHARPE = -0.10
CHEAP_PRESCREEN_MAX_DD_PCT = 35.0

XAU_BACKTEST_KWARGS = {
    "spread": 0.60,
    "commission_per_lot": 7.0,
    "slippage_pips": 4.0,
}

BTC_BACKTEST_KWARGS = {
    "spread": 8.0,
    "commission_per_lot": 0.0,
    "slippage_pips": 12.0,
}


def _current_session() -> str:
    from datetime import datetime, timezone
    hour = datetime.now(timezone.utc).hour
    if 0 <= hour < 7:
        return "asia"
    if 7 <= hour < 13:
        return "london"
    return "new_york"


def _hybrid_regime_score(rec, current_regime: str, current_session: str = "") -> float:
    s = rec.stats or {}
    wf = float(s.get("wf_overall_sharpe", 0) or 0)
    ex = s.get("strategy_explain", {}) or {}
    meta = ex.get("meta", {}) or {}

    regime_pnl = ex.get("regime_pnl", {}) or {}
    regime_ret = float((regime_pnl.get(current_regime, {}) or {}).get("return_pct", 0))
    regime_bonus = 1.0 + max(-0.5, min(0.5, regime_ret / REGIME_SORT_NORM))

    session_bonus = 1.0
    if current_session:
        session_pnl = ex.get("session_pnl", {}) or {}
        session_ret = float((session_pnl.get(current_session, {}) or {}).get("return_pct", 0))
        session_bonus = 1.0 + max(-0.5, min(0.5, session_ret / SESSION_SORT_NORM))

    status_bonus = STATUS_SORT_BONUS.get(getattr(rec, "status", "candidate"), 0.75)
    specialist_bonus = 1.0 + 0.20 * float(meta.get("specialist_score", 0.0) or 0.0)
    routing_bonus = 1.0 + 0.15 * float(meta.get("routing_confidence", 0.0) or 0.0)
    return wf * regime_bonus * session_bonus * status_bonus * specialist_bonus * routing_bonus


def _base_research_min_trades(symbol: str) -> int:
    sym_u = symbol.upper()
    if "XAG" in sym_u:
        return 35
    if "BTC" in sym_u:
        return 45
    return 60


def _bootstrap_research_min_trades(symbol: str) -> int:
    sym_u = symbol.upper()
    if "XAG" in sym_u:
        return XAG_BOOTSTRAP_MIN_TRADES
    if "BTC" in sym_u:
        return 30
    return 40


def _bootstrap_min_pf(symbol: str) -> float:
    sym_u = symbol.upper()
    if "XAG" in sym_u:
        return XAG_BOOTSTRAP_MIN_PF
    if "BTC" in sym_u:
        return 1.03
    return 1.05


def _bootstrap_min_sharpe(symbol: str) -> float:
    sym_u = symbol.upper()
    if "XAG" in sym_u:
        return XAG_BOOTSTRAP_MIN_SHARPE
    if "BTC" in sym_u:
        return 0.08
    return 0.12


def _bootstrap_min_wf_sharpe(symbol: str) -> float:
    sym_u = symbol.upper()
    if "XAG" in sym_u:
        return XAG_BOOTSTRAP_MIN_WF_SHARPE
    if "BTC" in sym_u:
        return 0.10
    return 0.15


def _execution_min_trades(symbol: str, *, bounded_specialist: bool, exploratory: bool, routing_conf: float, specialist_score: float) -> int:
    sym_u = symbol.upper()
    if "BTC" in sym_u:
        if exploratory and bounded_specialist and routing_conf >= 0.70:
            return BTC_EXPLORATORY_SPECIALIST_MIN_TRADES
        if bounded_specialist and routing_conf >= 0.65 and specialist_score >= 0.60:
            return BTC_SPECIALIST_EXEC_MIN_TRADES
        return BTC_EXEC_MIN_TRADES
    if "XAG" in sym_u:
        if exploratory and bounded_specialist and routing_conf >= 0.70:
            return XAG_EXPLORATORY_SPECIALIST_MIN_TRADES
        if bounded_specialist and routing_conf >= 0.65 and specialist_score >= 0.60:
            return XAG_SPECIALIST_EXEC_MIN_TRADES
        return XAG_EXEC_MIN_TRADES
    if exploratory and bounded_specialist and routing_conf >= 0.70:
        return EXPLORATORY_SPECIALIST_MIN_TRADES
    if bounded_specialist and routing_conf >= 0.65 and specialist_score >= 0.60:
        return SPECIALIST_EXEC_MIN_TRADES
    return EXEC_MIN_TRADES


def _research_backtest_kwargs(symbol: str) -> dict:
    params = dict(DEFAULT_BACKTEST_KWARGS)
    sym_u = symbol.upper()
    if "XAU" in sym_u:
        params.update(XAU_BACKTEST_KWARGS)
    if "BTC" in sym_u:
        params.update(BTC_BACKTEST_KWARGS)
    logger.info(
        "Research backtest costs for %s: spread=%.2f commission_per_lot=%.2f slippage_pips=%.2f",
        symbol,
        float(params.get("spread", 0.0) or 0.0),
        float(params.get("commission_per_lot", 0.0) or 0.0),
        float(params.get("slippage_pips", 0.0) or 0.0),
    )
    return params


def _cheap_prescreen_backtest_kwargs(symbol: str) -> dict:
    params = dict(CHEAP_PRESCREEN_BACKTEST_KWARGS)
    sym_u = symbol.upper()
    if "XAU" in sym_u:
        params["spread"] = 0.35
    if "BTC" in sym_u:
        params["spread"] = 4.0
    return params


def _passes_cheap_prescreen(feat, strat, symbol: str) -> tuple[bool, dict]:
    prescreen_kwargs = _cheap_prescreen_backtest_kwargs(symbol)
    result = run_backtest(feat, strat, regime_column="regime", **prescreen_kwargs)
    stats = result.stats or {}
    num_trades = float(stats.get("num_trades", 0.0) or 0.0)
    pf = float(stats.get("profit_factor", 0.0) or 0.0)
    sharpe = float(stats.get("sharpe_ratio", 0.0) or 0.0)
    dd = abs(float(stats.get("max_drawdown_pct", 0.0) or 0.0))

    passed = (
        num_trades >= CHEAP_PRESCREEN_MIN_TRADES
        and pf >= CHEAP_PRESCREEN_MIN_PF
        and sharpe >= CHEAP_PRESCREEN_MIN_SHARPE
        and dd <= CHEAP_PRESCREEN_MAX_DD_PCT
    )
    return passed, {
        "num_trades": num_trades,
        "profit_factor": pf,
        "sharpe_ratio": sharpe,
        "max_drawdown_pct": dd,
    }


def job_update_data() -> None:
    logger.info("Scheduler: job_update_data start")
    for symbol in MANAGED_SYMBOLS:
        try:
            df = fetch_ohlc(symbol, timeframe=TIMEFRAME)
            save_ohlc(df, symbol, TIMEFRAME)
            feat = compute_features(df, symbol, TIMEFRAME)
            feat = add_regime_column(feat)
            canon = canonical_symbol(symbol)
            save_features(feat, canon, TIMEFRAME)
            if canon != symbol:
                logger.info("Symbol alias: %s → saved features as %s", symbol, canon)
        except Exception as e:
            logger.exception("job_update_data error for %s: %s", symbol, e)
    logger.info("Scheduler: job_update_data done")


def job_update_news() -> None:
    logger.info("Scheduler: job_update_news start")
    try:
        from ..data.news_collector import update_news_events, get_upcoming_high_impact
        from ..notifications.whatsapp_notifier import send_news_alert
        import MetaTrader5 as mt5

        update_news_events()
        upcoming = get_upcoming_high_impact(hours_ahead=8.0, min_impact=3, gold_relevant_only=True)
        if not upcoming.empty:
            account_info = None
            try:
                from ..execution.live_monitor import get_equity_peak
                info = mt5.account_info()
                if info:
                    account_info = {"equity": float(info.equity), "peak": get_equity_peak()}
            except Exception:
                pass
            send_news_alert(upcoming, account_info=account_info)
    except Exception:
        logger.exception("job_update_news failed")
    logger.info("Scheduler: job_update_news done")


def job_news_alert() -> None:
    try:
        from ..data.news_collector import get_upcoming_high_impact
        from ..notifications.whatsapp_notifier import send_news_alert
        import MetaTrader5 as mt5

        upcoming = get_upcoming_high_impact(hours_ahead=1.0, min_impact=3, gold_relevant_only=True)
        if upcoming.empty:
            return

        account_info = None
        try:
            from ..execution.live_monitor import get_equity_peak
            info = mt5.account_info()
            if info:
                account_info = {"equity": float(info.equity), "peak": get_equity_peak()}
        except Exception:
            pass

        sent = send_news_alert(upcoming, account_info=account_info)
        if sent:
            logger.info("WhatsApp news alert sent: %d upcoming high-impact events", len(upcoming))
    except Exception:
        logger.exception("job_news_alert failed")


def _apply_live_degradation(pool) -> None:
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
        if rec.num_trades < max(15, MAX_RECENT_TRADES):
            continue

        initial_eq = float(stats.get("initial_equity", 1.0) or 1.0)
        live_ret_total_pct = rec.total_pnl / max(initial_eq, 1.0) * 100.0
        live_ret_recent_pct = sum(rec.recent_pnls) / max(initial_eq, 1.0) * 100.0 if rec.recent_pnls else 0.0
        recent_avg_pnl = float(rec.recent_avg_pnl or 0.0)

        severe_recent_break = live_ret_recent_pct < -3.0
        sustained_underperformance = (
            live_ret_recent_pct < 0.0
            and live_ret_total_pct < 0.0
            and live_ret_recent_pct < 0.25 * bt_ret
            and recent_avg_pnl <= 0.0
        )

        if severe_recent_break or sustained_underperformance:
            pool_rec.status = "candidate"
            logger.warning(
                "Degradation: demoting %s to candidate (bt_ret=%.2f%% bt_sharpe=%.2f live_total=%.2f%% live_recent=%.2f%% recent_avg_pnl=%.2f trades=%d severe=%s sustained=%s)",
                name, bt_ret, bt_sharpe, live_ret_total_pct, live_ret_recent_pct, recent_avg_pnl, rec.num_trades, severe_recent_break, sustained_underperformance,
            )
            try:
                from ..notifications.whatsapp_notifier import send_strategy_degradation_alert
                send_strategy_degradation_alert(strategy_name=name, recent_avg_pnl=rec.recent_avg_pnl, total_pnl=rec.total_pnl, new_status="candidate")
            except Exception:
                logger.exception("Failed to send strategy degradation WhatsApp alert")


def _log_research_skip_summary(symbol: str, timeframe: str, skip_counts: dict[str, int], skip_samples: dict[str, list[str]]) -> None:
    if not skip_counts:
        return
    ordered = {key: skip_counts[key] for key in sorted(skip_counts.keys())}
    sample = {key: skip_samples.get(key, [])[:3] for key in ordered}
    logger.info(
        "Research skip summary for %s %s: counts=%s samples=%s",
        symbol,
        timeframe,
        ordered,
        sample,
    )


def _memory_is_clearly_bad(candidate, memory: ResearchMemory, symbol: str, timeframe: str) -> bool:
    try:
        params = getattr(candidate, "params", {}) or {}
        query_text = "\n".join([
            f"symbol={symbol}",
            f"timeframe={timeframe}",
            f"family={params.get('family', '')}",
            f"playbook={params.get('playbook_type', '')}",
            f"long_entry={getattr(candidate, 'long_entry_rule', '')}",
            f"short_entry={getattr(candidate, 'short_entry_rule', '')}",
            f"exit={getattr(candidate, 'exit_rule', '')}",
            f"sl_atr={getattr(candidate, 'sl_atr_mult', '')}",
            f"tp_atr={getattr(candidate, 'tp_atr_mult', '')}",
            f"regime={params.get('regime_type', '')}",
        ])
        neighbors = memory.query_similar_strategies(symbol=symbol, timeframe=timeframe, text=query_text, n_results=10)
    except Exception as e:
        logger.exception("ResearchMemory veto query failed for %s: %s", getattr(candidate, "name", "?"), e)
        return False

    if not neighbors or len(neighbors) < 5:
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

    if bad >= 5 and bad / float(len(neighbors)) >= 0.7:
        logger.info("Memory veto: skipping candidate %s (bad_neighbors=%d/%d)", getattr(candidate, "name", "<unnamed>"), bad, len(neighbors))
        return True
    return False


def _memory_dead_zone_penalty(candidate, memory: ResearchMemory, symbol: str, timeframe: str) -> tuple[float, dict]:
    try:
        params = getattr(candidate, "params", {}) or {}
        query_text = "\n".join([
            f"symbol={symbol}",
            f"timeframe={timeframe}",
            f"family={params.get('family', '')}",
            f"playbook={params.get('playbook_type', '')}",
            f"long_entry={getattr(candidate, 'long_entry_rule', '')}",
            f"short_entry={getattr(candidate, 'short_entry_rule', '')}",
            f"exit={getattr(candidate, 'exit_rule', '')}",
            f"sl_atr={getattr(candidate, 'sl_atr_mult', '')}",
            f"tp_atr={getattr(candidate, 'tp_atr_mult', '')}",
            f"regime={params.get('regime_type', '')}",
        ])
        neighbors = memory.query_similar_strategies(symbol=symbol, timeframe=timeframe, text=query_text, n_results=12)
    except Exception as e:
        logger.exception("ResearchMemory dead-zone query failed for %s: %s", getattr(candidate, "name", "?"), e)
        return 0.0, {}

    if not neighbors:
        return 0.0, {}

    weak = 0
    strong = 0
    same_family = 0
    wf_vals = []
    pf_vals = []

    candidate_family = str(params.get("family", "") or "")
    for nb in neighbors:
        nb_family = str(nb.get("meta_family") or nb.get("stat_family") or "")
        if candidate_family and nb_family == candidate_family:
            same_family += 1

        sharpe = nb.get("stat_sharpe_ratio")
        pf = nb.get("stat_profit_factor")
        ret_pct = nb.get("stat_return_pct")
        wf_sharpe = nb.get("stat_wf_overall_sharpe")

        if wf_sharpe is not None:
            wf_vals.append(float(wf_sharpe))
        if pf is not None:
            pf_vals.append(float(pf))

        if (
            (sharpe is not None and float(sharpe) < 0.10)
            or (pf is not None and float(pf) < 1.02)
            or (ret_pct is not None and float(ret_pct) <= 0.0)
            or (wf_sharpe is not None and float(wf_sharpe) < 0.15)
        ):
            weak += 1
        if (
            (sharpe is not None and float(sharpe) > 0.35)
            or (pf is not None and float(pf) > 1.15)
            or (ret_pct is not None and float(ret_pct) > 2.0)
            or (wf_sharpe is not None and float(wf_sharpe) > 0.35)
        ):
            strong += 1

    total = len(neighbors)
    weak_ratio = weak / float(total)
    strong_ratio = strong / float(total)
    same_family_ratio = same_family / float(total)

    penalty = 0.0
    if weak_ratio >= 0.55:
        penalty += min(0.35, weak_ratio * 0.35)
    if same_family_ratio >= 0.65 and strong_ratio <= 0.20:
        penalty += 0.10
    if wf_vals and sum(wf_vals) / len(wf_vals) < 0.12:
        penalty += 0.10
    if pf_vals and sum(pf_vals) / len(pf_vals) < 1.03:
        penalty += 0.08

    return penalty, {
        "neighbors": total,
        "weak_ratio": weak_ratio,
        "strong_ratio": strong_ratio,
        "same_family_ratio": same_family_ratio,
    }


def job_research_strategies() -> None:
    logger.info("Scheduler: job_research_strategies start")
    pool = load_pool()
    memory = ResearchMemory()
    researched_canonicals: set[str] = set()

    for symbol in MANAGED_SYMBOLS:
        canon = canonical_symbol(symbol)
        if canon in researched_canonicals:
            logger.info("Skipping %s — canonical %s already researched this cycle", symbol, canon)
            continue
        researched_canonicals.add(canon)

        try:
            feat = load_features(canon, TIMEFRAME)
        except FileNotFoundError:
            try:
                feat = load_features(symbol, TIMEFRAME)
                logger.info("Research fallback: loaded legacy features for %s using actual symbol", symbol)
            except FileNotFoundError:
                logger.warning("No features for %s/%s %s; skipping research", symbol, canon, TIMEFRAME)
                continue
        except Exception as e:
            logger.exception("Failed to load features for %s/%s: %s", symbol, canon, e)
            continue

        bt_kwargs = _research_backtest_kwargs(canon)

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
                        f"family={params.get('family', '')}",
                        f"playbook={params.get('playbook_type', '')}",
                        f"long_entry={getattr(strat_obj, 'long_entry_rule', '')}",
                        f"short_entry={getattr(strat_obj, 'short_entry_rule', '')}",
                        f"exit={getattr(strat_obj, 'exit_rule', '')}",
                        f"sl_atr={getattr(strat_obj, 'sl_atr_mult', '')}",
                        f"tp_atr={getattr(strat_obj, 'tp_atr_mult', '')}",
                        f"regime={params.get('regime_type', '')}",
                    ])
                except Exception:
                    pass
                neighbors = memory.query_similar_strategies(symbol=rec.symbol, timeframe=rec.timeframe, text=strat_text, n_results=10)
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
            return bonus

        parent_candidates = [
            rec for rec in pool.strategies.values()
            if canonical_symbol(rec.symbol) == canon and rec.timeframe == TIMEFRAME
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

        family_mix = Counter(str((getattr(s, 'params', {}) or {}).get('family', 'unknown')) for s in new_population)
        logger.info("Research family mix for %s (%s) %s: %s", symbol, canon, TIMEFRAME, dict(family_mix))
        research_skip_counts: dict[str, int] = defaultdict(int)
        research_skip_samples: dict[str, list[str]] = defaultdict(list)

        for strat in new_population:
            try:
                if _memory_is_clearly_bad(strat, memory, canon, TIMEFRAME):
                    research_skip_counts["memory_veto"] += 1
                    if len(research_skip_samples["memory_veto"]) < 3:
                        research_skip_samples["memory_veto"].append(strat.name)
                    continue

                feat.attrs["strategy_params"] = getattr(strat, "params", {}) or {}

                prescreen_ok, prescreen_stats = _passes_cheap_prescreen(feat, strat, canon)
                if not prescreen_ok:
                    research_skip_counts["cheap_prescreen"] += 1
                    if len(research_skip_samples["cheap_prescreen"]) < 3:
                        research_skip_samples["cheap_prescreen"].append(
                            f"{strat.name}:tr={prescreen_stats['num_trades']:.0f},pf={prescreen_stats['profit_factor']:.2f},sh={prescreen_stats['sharpe_ratio']:.2f},dd={prescreen_stats['max_drawdown_pct']:.1f}"
                        )
                    continue

                result = run_backtest(feat, strat, regime_column="regime", **bt_kwargs)
                eval_result = evaluate_strategy(result.stats)

                dead_zone_penalty, dead_zone_meta = _memory_dead_zone_penalty(strat, memory, canon, TIMEFRAME)
                if dead_zone_penalty > 0.0:
                    eval_result["score"] = float(eval_result.get("score", 0.0) or 0.0) - dead_zone_penalty
                    eval_result["research_dead_zone_penalty"] = dead_zone_penalty
                    eval_result["research_dead_zone_meta"] = dead_zone_meta
                    if dead_zone_penalty >= 0.30:
                        research_skip_counts["dead_zone_penalty"] += 1
                        if len(research_skip_samples["dead_zone_penalty"]) < 3:
                            research_skip_samples["dead_zone_penalty"].append(
                                f"{strat.name}:pen={dead_zone_penalty:.2f},weak={dead_zone_meta.get('weak_ratio', 0.0):.2f},fam={dead_zone_meta.get('same_family_ratio', 0.0):.2f}"
                            )
                        continue

                num_trades = float(eval_result.get("num_trades", 0.0) or 0.0)
                params = getattr(strat, "params", {}) or {}
                playbook_type = str(params.get("playbook_type", "") or "")
                family = str(params.get("family", "") or "")
                is_xag = "XAG" in canon.upper()
                bootstrap_candidate = (
                    playbook_type in {"xau_impulse_pullback", "xau_session_continuation"}
                    or family in {"xau_impulse_pullback", "xau_session_continuation"}
                    or (is_xag and family in {"compression_breakout", "vol_breakout", "session_breakout", "pullback_trend"})
                )

                base_min_trades = _base_research_min_trades(canon)
                if num_trades < base_min_trades and not bootstrap_candidate:
                    research_skip_counts["low_trade_count"] += 1
                    if len(research_skip_samples["low_trade_count"]) < 3:
                        research_skip_samples["low_trade_count"].append(f"{strat.name}:{num_trades:.0f}")
                    continue
                bootstrap_min_trades = _bootstrap_research_min_trades(canon)
                if num_trades < bootstrap_min_trades and bootstrap_candidate:
                    research_skip_counts["bootstrap_too_few_trades"] += 1
                    if len(research_skip_samples["bootstrap_too_few_trades"]) < 3:
                        research_skip_samples["bootstrap_too_few_trades"].append(f"{strat.name}:{num_trades:.0f}")
                    continue

                pf = float(eval_result.get("profit_factor", 0.0) or 0.0)
                sharpe = float(eval_result.get("sharpe_ratio", 0.0) or 0.0)
                bootstrap_pf = _bootstrap_min_pf(canon)
                bootstrap_sharpe = _bootstrap_min_sharpe(canon)
                if (pf < 1.10 or sharpe < 0.20) and not (bootstrap_candidate and pf >= bootstrap_pf and sharpe >= bootstrap_sharpe):
                    research_skip_counts["weak_perf"] += 1
                    if len(research_skip_samples["weak_perf"]) < 3:
                        research_skip_samples["weak_perf"].append(f"{strat.name}:pf={pf:.2f},sh={sharpe:.2f}")
                    continue

                wf = walk_forward_test(feat, strat, **bt_kwargs)
                eval_result["research_bootstrap_candidate"] = bootstrap_candidate
                eval_result["research_bootstrap_applied"] = bool(bootstrap_candidate and (pf < 1.10 or sharpe < 0.20 or num_trades < 60))

                mc_method = "block" if len(result.trades) >= 12 else "shuffle"
                mc_block_size = 4 if len(result.trades) >= 24 else 3
                mc = monte_carlo_pnl(
                    result.trades,
                    n_runs=300,
                    slippage_std_pips=max(0.5, bt_kwargs["slippage_pips"] * 0.5),
                    pip_size=0.01 if "XAU" in canon else 1.0,
                    method=mc_method,
                    block_size=mc_block_size,
                    initial_equity=float(eval_result.get("initial_equity", 10000.0) or 10000.0),
                )

                eval_result["wf_overall_sharpe"] = wf.get("aggregate", {}).get("overall_sharpe", 0.0)
                eval_result["wf_overall_max_drawdown_pct"] = wf.get("aggregate", {}).get("overall_max_drawdown_pct", 0.0)
                eval_result["symbol"] = getattr(strat, "symbol", "")
                eval_result["timeframe"] = getattr(strat, "timeframe", "")
                eval_result["family"] = str((getattr(strat, "params", {}) or {}).get("family", "unknown"))
                eval_result["playbook_type"] = str((getattr(strat, "params", {}) or {}).get("playbook_type", "unknown"))
                eval_result.update(mc)

                mc_p5 = float(eval_result.get("mc_final_pnl_p5", 0.0) or 0.0)
                mc_dd_p95 = float(eval_result.get("mc_max_dd_p95", 0.0) or 0.0)
                mc_loss_prob = float(eval_result.get("mc_loss_prob", 0.0) or 0.0)
                wf_sharpe = float(eval_result.get("wf_overall_sharpe", 0.0) or 0.0)
                dd_abs = abs(float(eval_result.get("max_drawdown_pct", 100.0) or 100.0))
                explain = eval_result.get("strategy_explain", {}) or {}
                meta = explain.get("meta", {}) or {}
                risk_behavior = explain.get("risk_behavior", {}) or {}

                if wf_sharpe < 0.20 and not bootstrap_candidate:
                    research_skip_counts["weak_wf_sharpe"] += 1
                    if len(research_skip_samples["weak_wf_sharpe"]) < 3:
                        research_skip_samples["weak_wf_sharpe"].append(f"{strat.name}:{wf_sharpe:.3f}")
                    continue
                bootstrap_wf = _bootstrap_min_wf_sharpe(canon)
                if wf_sharpe < bootstrap_wf and bootstrap_candidate:
                    research_skip_counts["bootstrap_weak_wf_sharpe"] += 1
                    if len(research_skip_samples["bootstrap_weak_wf_sharpe"]) < 3:
                        research_skip_samples["bootstrap_weak_wf_sharpe"].append(f"{strat.name}:{wf_sharpe:.3f}")
                    continue
                if mc_p5 <= 0.0:
                    research_skip_counts["mc_p5_non_positive"] += 1
                    if len(research_skip_samples["mc_p5_non_positive"]) < 3:
                        research_skip_samples["mc_p5_non_positive"].append(f"{strat.name}:{mc_p5:.2f}")
                    continue
                if mc_dd_p95 > 2500.0:
                    research_skip_counts["mc_dd_too_high"] += 1
                    if len(research_skip_samples["mc_dd_too_high"]) < 3:
                        research_skip_samples["mc_dd_too_high"].append(f"{strat.name}:{mc_dd_p95:.2f}")
                    continue
                if mc_loss_prob > 0.55:
                    research_skip_counts["mc_loss_prob_too_high"] += 1
                    if len(research_skip_samples["mc_loss_prob_too_high"]) < 3:
                        research_skip_samples["mc_loss_prob_too_high"].append(f"{strat.name}:{mc_loss_prob:.2f}")
                    continue
                exit_rule_ratio = float(risk_behavior.get("exit_rule_ratio", 0.0) or 0.0)
                tp_hit_ratio = float(risk_behavior.get("tp_hit_ratio", 0.0) or 0.0)
                has_time_stop = bool((getattr(strat, "params", {}) or {}).get("has_time_stop", False))
                has_session_exit_guard = bool((getattr(strat, "params", {}) or {}).get("has_session_exit_guard", False))
                if exit_rule_ratio > 0.80 and not has_time_stop:
                    research_skip_counts["exit_rule_dependency"] += 1
                    if len(research_skip_samples["exit_rule_dependency"]) < 3:
                        research_skip_samples["exit_rule_dependency"].append(strat.name)
                    continue
                if exit_rule_ratio > 0.88:
                    research_skip_counts["extreme_exit_rule_dependency"] += 1
                    if len(research_skip_samples["extreme_exit_rule_dependency"]) < 3:
                        research_skip_samples["extreme_exit_rule_dependency"].append(strat.name)
                    continue
                if tp_hit_ratio < 0.08 and exit_rule_ratio > 0.75 and not has_session_exit_guard:
                    research_skip_counts["weak_exit_signature"] += 1
                    if len(research_skip_samples["weak_exit_signature"]) < 3:
                        research_skip_samples["weak_exit_signature"].append(
                            f"{strat.name}:tp={tp_hit_ratio:.2f},exit={exit_rule_ratio:.2f}"
                        )
                    continue
                avg_holding_bars = float(risk_behavior.get("avg_holding_bars", 0.0) or 0.0)
                if avg_holding_bars < 1.0:
                    research_skip_counts["holding_too_short_warning"] += 1
                    if len(research_skip_samples["holding_too_short_warning"]) < 3:
                        research_skip_samples["holding_too_short_warning"].append(f"{strat.name}:{avg_holding_bars:.2f}")
                    logger.info(
                        "Research warning: %s has avg_holding_bars=%.2f (<1.0) but is no longer hard-rejected",
                        strat.name,
                        avg_holding_bars,
                    )

                trend_ret = (
                    (explain.get("regime_pnl", {}).get("trending_up", {}) or {}).get("return_pct", 0.0)
                    + (explain.get("regime_pnl", {}).get("trending_down", {}) or {}).get("return_pct", 0.0)
                )
                range_ret = float((explain.get("regime_pnl", {}).get("ranging", {}) or {}).get("return_pct", 0.0))
                routing_conf = float(meta.get("routing_confidence", 0.0) or 0.0)
                specialist_score = float(meta.get("specialist_score", 0.0) or 0.0)
                bounded_role = bool(meta.get("allowed_regimes") or meta.get("allowed_sessions") or meta.get("blocked_regimes") or meta.get("blocked_sessions"))
                ret_val = float(eval_result.get("return_pct", 0.0) or 0.0)

                if (
                    num_trades >= 100
                    and ret_val > 0.0
                    and dd_abs <= 15.0
                    and pf >= 1.18
                    and wf_sharpe >= 0.75
                    and mc_p5 > 25.0
                    and specialist_score >= 0.60
                    and routing_conf >= 0.60
                    and bounded_role
                    and max(trend_ret, range_ret, ret_val) > 0.0
                ):
                    status = "active"
                elif (
                    eval_result.get("accepted")
                    and wf_sharpe >= 0.30
                    and mc_p5 > 0.0
                    and specialist_score >= 0.40
                    and routing_conf >= 0.40
                    and num_trades >= 40
                ) or (
                    is_xag
                    and bootstrap_candidate
                    and eval_result.get("accepted")
                    and wf_sharpe >= _bootstrap_min_wf_sharpe(canon)
                    and mc_p5 > 0.0
                    and num_trades >= _bootstrap_research_min_trades(canon)
                    and pf >= _bootstrap_min_pf(canon)
                    and sharpe >= _bootstrap_min_sharpe(canon)
                ):
                    status = "exploratory"
                else:
                    status = "disabled"

                strat_params = dict(getattr(strat, "params", {}) or {})
                eval_result["strategy"] = {
                    "long_entry_rule": getattr(strat, "long_entry_rule", "") or "",
                    "short_entry_rule": getattr(strat, "short_entry_rule", "") or "",
                    "exit_rule": getattr(strat, "exit_rule", "") or "",
                    "sl_atr_mult": getattr(strat, "sl_atr_mult", ""),
                    "tp_atr_mult": getattr(strat, "tp_atr_mult", ""),
                    "stop_loss_pips": getattr(strat, "stop_loss_pips", 0.0) or 0.0,
                    "take_profit_pips": getattr(strat, "take_profit_pips", 0.0) or 0.0,
                    "family": str(strat_params.get("family", "unknown")),
                    "playbook_type": str(strat_params.get("playbook_type", "unknown")),
                    "params": strat_params,
                }

                pool.upsert_strategy(strategy=strat, stats=eval_result, score=eval_result.get("score", 0.0), status=status)
                memory.store_strategy_result(strategy_name=strat.name, symbol=strat.symbol, timeframe=strat.timeframe, stats=eval_result)
            except Exception as e:
                logger.exception("Research error for %s: %s", strat.name, e)

        _log_research_skip_summary(canon, TIMEFRAME, research_skip_counts, research_skip_samples)

    _apply_live_degradation(pool)
    pool.prune(max_inactive=200, min_family_keep=8)
    save_pool(pool)
    logger.info("Scheduler: job_research_strategies done")


def _execution_family(rec) -> str:
    s = rec.stats or {}
    st = s.get("strategy", {}) or {}
    params = (st.get("params") if isinstance(st, dict) else {}) or {}
    return str(
        st.get("family")
        or st.get("playbook_type")
        or params.get("family")
        or params.get("playbook_type")
        or s.get("family")
        or s.get("playbook_type")
        or "unknown"
    )


def _execution_best_regime(rec) -> str:
    ex = ((rec.stats or {}).get("strategy_explain", {}) or {})
    meta = ex.get("meta", {}) or {}
    return str(meta.get("best_regime", "unknown") or "unknown")


def _select_diversified_execution_pool(records, current_regime: str, current_session: str, limit: int = MAX_EXECUTION_POOL):
    ranked = sorted(records, key=lambda r: _hybrid_regime_score(r, current_regime, current_session), reverse=True)
    selected = []
    remaining = list(ranked)
    regime_counts = defaultdict(int)
    family_counts = defaultdict(int)

    def _take(allow_family_overflow: bool, allow_regime_overflow: bool):
        nonlocal remaining
        next_remaining = []
        for rec in remaining:
            if len(selected) >= limit:
                next_remaining.append(rec)
                continue
            regime = _execution_best_regime(rec)
            family = _execution_family(rec)
            regime_blocked = regime_counts[regime] >= MAX_EXECUTION_PER_BEST_REGIME
            family_blocked = family_counts[family] >= MAX_EXECUTION_PER_FAMILY
            if (regime_blocked and not allow_regime_overflow) or (family_blocked and not allow_family_overflow):
                next_remaining.append(rec)
                continue
            selected.append(rec)
            regime_counts[regime] += 1
            family_counts[family] += 1
        remaining = next_remaining

    _take(allow_family_overflow=False, allow_regime_overflow=False)
    if len(selected) < limit:
        _take(allow_family_overflow=True, allow_regime_overflow=False)
    if len(selected) < limit:
        _take(allow_family_overflow=True, allow_regime_overflow=True)
    return selected[:limit]


def job_execute_signals() -> None:
    logger.info("Scheduler: job_execute_signals start")
    pool = load_pool()
    live_manifest = load_live_manifest()
    risk_perc = min(2.0, risk_config.max_risk_per_trade_pct)

    for symbol in MANAGED_SYMBOLS:
        canon = canonical_symbol(symbol)
        try:
            feat = load_features(canon, TIMEFRAME)
        except FileNotFoundError:
            try:
                feat = load_features(symbol, TIMEFRAME)
                logger.info("Execution fallback: loaded legacy features for %s using actual symbol", symbol)
            except FileNotFoundError:
                logger.warning("No features for %s/%s %s; skipping signals", symbol, canon, TIMEFRAME)
                continue
        except Exception as e:
            logger.exception("Failed to load features for %s/%s: %s", symbol, canon, e)
            continue

        try:
            latest = feat.iloc[-1]
            if bool(latest.get("in_news_lockout", False)):
                logger.warning("News lockout active for %s %s — skipping signal generation", symbol, TIMEFRAME)
                continue
        except Exception:
            pass

        manifest_entries = manifest_entries_for_slot(live_manifest, symbol=canon, timeframe=TIMEFRAME)
        manifest_pool = strategy_pool_from_manifest_entries(manifest_entries)
        live_tier_strats = list(manifest_pool.strategies.values())
        manifest_loaded = bool(live_tier_strats)

        if not live_tier_strats and canon != symbol:
            manifest_entries = manifest_entries_for_slot(live_manifest, symbol=symbol, timeframe=TIMEFRAME)
            manifest_pool = strategy_pool_from_manifest_entries(manifest_entries)
            live_tier_strats = list(manifest_pool.strategies.values())
            manifest_loaded = bool(live_tier_strats)
            if live_tier_strats:
                logger.info(
                    "Execution manifest fallback: loaded entries for actual symbol %s (canonical %s)",
                    symbol,
                    canon,
                )

        if not live_tier_strats:
            live_tier_strats = [
                rec for rec in pool.strategies.values()
                if canonical_symbol(rec.symbol) == canon and rec.timeframe == TIMEFRAME and rec.status in {"active", "exploratory"}
            ]
            if live_tier_strats:
                logger.warning(
                    "Live manifest missing/stale for %s/%s %s — falling back to pool scan (%d live strategies)",
                    symbol,
                    canon,
                    TIMEFRAME,
                    len(live_tier_strats),
                )

        if not live_tier_strats:
            logger.warning("No active/exploratory strategies in runtime set for %s %s — skipping execution", symbol, TIMEFRAME)
            continue

        strats_by_wf = sorted(
            live_tier_strats,
            key=lambda r: (
                STATUS_SORT_BONUS.get(getattr(r, "status", "candidate"), 0.75),
                float((r.stats or {}).get("wf_overall_sharpe", 0) or 0),
                float((((r.stats or {}).get("strategy_explain", {}) or {}).get("meta", {}) or {}).get("specialist_score", 0.0) or 0.0),
            ),
            reverse=True,
        )

        seen_fps: set = set()
        unique_strats = []
        rule_cache: dict = {}
        strat_base_dir = BASE_DIR / "strategies" / "generated"

        for rec in strats_by_wf:
            if rec.name in rule_cache:
                fp = rule_cache[rec.name]
            else:
                try:
                    path = strat_base_dir / f"{rec.name}.json"
                    s = load_strategy(path)
                    params = getattr(s, "params", {}) or {}
                    fp = (
                        str(params.get("family", "")),
                        str(getattr(s, "long_entry_rule", "") or ""),
                        str(getattr(s, "short_entry_rule", "") or ""),
                        str(getattr(s, "exit_rule", "") or ""),
                        round(float(getattr(s, "stop_loss_pips", 0) or 0), 0),
                    )
                except Exception:
                    st = rec.stats or {}
                    fp = (
                        st.get("family", ""),
                        round(float(st.get("sharpe_ratio", 0) or 0), 4),
                        round(float(st.get("profit_factor", 0) or 0), 4),
                        round(float(st.get("return_pct", 0) or 0), 4),
                        int(st.get("num_trades", 0) or 0),
                    )
                rule_cache[rec.name] = fp

            if fp not in seen_fps:
                seen_fps.add(fp)
                unique_strats.append(rec)

        def _passes_quality(rec) -> bool:
            s = rec.stats or {}
            ex = s.get("strategy_explain", {}) or {}
            risk_beh = ex.get("risk_behavior", {}) or {}
            meta = ex.get("meta", {}) or {}
            wf = float(s.get("wf_overall_sharpe", 0) or 0)
            dd = abs(float(s.get("max_drawdown_pct", 0) or 0))
            tr = int(s.get("num_trades", 0) or 0)
            cls = int(risk_beh.get("max_consecutive_losses", 0) or 0)
            routing_conf = float(meta.get("routing_confidence", 0.0) or 0.0)
            specialist_score = float(meta.get("specialist_score", 0.0) or 0.0)
            allowed_regimes = list(meta.get("allowed_regimes", []) or [])
            allowed_sessions = list(meta.get("allowed_sessions", []) or [])
            bounded_specialist = bool(allowed_regimes or allowed_sessions)
            mc_p5 = float(s.get("mc_final_pnl_p5", 0.0) or 0.0)

            min_trades = _execution_min_trades(
                str(getattr(rec, "symbol", "") or ""),
                bounded_specialist=bounded_specialist,
                exploratory=bool(getattr(rec, "status", "candidate") == "exploratory"),
                routing_conf=routing_conf,
                specialist_score=specialist_score,
            )

            return (
                wf >= EXEC_MIN_WF_SHARPE
                and dd <= EXEC_MAX_DD_PCT
                and tr >= min_trades
                and cls <= EXEC_MAX_CONSEC_LOSS
                and mc_p5 > 0.0
                and (specialist_score >= 0.30 or wf >= 5.0)
            )

        quality_fail_counts: Counter[str] = Counter()

        def _quality_fail_reasons(rec) -> list[str]:
            s = rec.stats or {}
            ex = s.get("strategy_explain", {}) or {}
            risk_beh = ex.get("risk_behavior", {}) or {}
            meta = ex.get("meta", {}) or {}
            wf = float(s.get("wf_overall_sharpe", 0) or 0)
            dd = abs(float(s.get("max_drawdown_pct", 0) or 0))
            tr = int(s.get("num_trades", 0) or 0)
            cls = int(risk_beh.get("max_consecutive_losses", 0) or 0)
            routing_conf = float(meta.get("routing_confidence", 0.0) or 0.0)
            specialist_score = float(meta.get("specialist_score", 0.0) or 0.0)
            allowed_regimes = list(meta.get("allowed_regimes", []) or [])
            allowed_sessions = list(meta.get("allowed_sessions", []) or [])
            bounded_specialist = bool(allowed_regimes or allowed_sessions)
            mc_p5 = float(s.get("mc_final_pnl_p5", 0.0) or 0.0)

            min_trades = _execution_min_trades(
                str(getattr(rec, "symbol", "") or ""),
                bounded_specialist=bounded_specialist,
                exploratory=bool(getattr(rec, "status", "candidate") == "exploratory"),
                routing_conf=routing_conf,
                specialist_score=specialist_score,
            )

            reasons: list[str] = []
            if wf < EXEC_MIN_WF_SHARPE:
                reasons.append(f"wf<{EXEC_MIN_WF_SHARPE}")
            if dd > EXEC_MAX_DD_PCT:
                reasons.append(f"dd>{EXEC_MAX_DD_PCT}")
            if tr < min_trades:
                reasons.append(f"trades<{min_trades}")
            if cls > EXEC_MAX_CONSEC_LOSS:
                reasons.append(f"cls>{EXEC_MAX_CONSEC_LOSS}")
            if mc_p5 <= 0.0:
                reasons.append("mc_p5<=0")
            if not (specialist_score >= 0.30 or wf >= 5.0):
                reasons.append("specialist<0.30_and_wf<5")
            return reasons

        quality_strats = []
        for r in unique_strats:
            reasons = _quality_fail_reasons(r)
            if reasons:
                for reason in reasons:
                    quality_fail_counts[reason] += 1
                continue
            quality_strats.append(r)

        current_regime = "unknown"
        current_session = _current_session()
        try:
            current_regime = str(feat.iloc[-1].get("regime", "unknown"))
        except Exception:
            pass

        final_strats = _select_diversified_execution_pool(quality_strats, current_regime, current_session, limit=MAX_EXECUTION_POOL)

        if len(live_tier_strats) != len(final_strats):
            n_dupes = len(live_tier_strats) - len(unique_strats)
            n_filtered = len(unique_strats) - len(quality_strats)
            n_capped = max(0, len(quality_strats) - len(final_strats))
            logger.info(
                "Execution pool %s %s [regime=%s session=%s]: %d live-tier → %d unique (-%d clones) → %d quality (-%d threshold) → %d final (-%d capped)",
                symbol, TIMEFRAME, current_regime, current_session,
                len(live_tier_strats), len(unique_strats), n_dupes,
                len(quality_strats), n_filtered, len(final_strats), n_capped,
            )

        if not final_strats:
            logger.warning(
                "No strategies passed execution filter for %s %s | live_tier=%d unique=%d quality_fail_counts=%s",
                symbol,
                TIMEFRAME,
                len(live_tier_strats),
                len(unique_strats),
                dict(quality_fail_counts),
            )
            continue

        from ..strategies.pool import StrategyPool
        filtered_pool = StrategyPool()
        filtered_pool.strategies = {r.name: r for r in final_strats}

        if manifest_loaded:
            logger.info(
                "Execution runtime source %s %s: manifest entries=%d final=%d",
                symbol,
                TIMEFRAME,
                len(manifest_entries),
                len(final_strats),
            )

        results, summary = execute_signals_for_symbol(symbol, TIMEFRAME, feat, filtered_pool, risk_perc=risk_perc)

        if results:
            for sig, reason in results:
                logger.info("Signal result: strategy=%s symbol=%s dir=%s reason=%s", sig.strategy.name, symbol, sig.direction, reason)
        else:
            logger.info("No signals for %s %s — summary=%s", symbol, TIMEFRAME, summary)

    logger.info("Scheduler: job_execute_signals done")


def job_live_monitor() -> None:
    logger.info("Scheduler: job_live_monitor start")
    try:
        update_live_stats()
    except Exception as e:
        logger.exception("job_live_monitor error: %s", e)

    try:
        pool = load_pool()
        live_stats = load_all_strategy_stats()
        actions = evaluate_live_decay(pool, live_stats)
        changed = apply_live_decay_actions(pool, actions)
        if actions:
            save_pool(pool)
            logger.info(
                "job_live_monitor: processed %d live decay actions (%d status changes)",
                len(actions),
                changed,
            )
    except Exception:
        logger.exception("job_live_monitor live_decay error")

    try:
        from ..execution.live_observer import snapshot_open_trades
        snapshot_open_trades()
    except Exception:
        logger.exception("job_live_monitor snapshot_open_trades error")

    logger.info("Scheduler: job_live_monitor done")


def start_scheduler() -> BackgroundScheduler:
    if not scheduler_config.enable_scheduler:
        logger.warning("Scheduler is disabled via config")
        return BackgroundScheduler()

    logger.info("Starting MT5 and scheduler...")
    initialize_mt5()

    sched = BackgroundScheduler(timezone="UTC")
    sched.add_job(job_update_data, "interval", minutes=5, id="update_data")
    sched.add_job(job_research_strategies, "interval", minutes=30, id="research_strategies")
    sched.add_job(job_execute_signals, "interval", minutes=5, id="execute_signals")
    sched.add_job(job_live_monitor, "interval", minutes=5, id="live_monitor")
    sched.add_job(job_update_news, "cron", hour=6, minute=0, id="update_news")
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
