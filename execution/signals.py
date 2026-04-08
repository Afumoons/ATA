from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import List, Tuple, Any, Dict, Optional, Iterable

from collections import Counter, defaultdict
from types import SimpleNamespace
import re

import pandas as pd

from ..config import routing_config, canonical_symbol
from ..logging_utils import get_logger
from ..strategies.base import StrategyDefinition
from ..strategies.live_manifest import strategy_definition_from_manifest_entry
from ..strategies.pool import StrategyPool
from ..execution.engine import execute_trade
from ..execution.live_state_utils import can_open_new_trade, strategy_has_open_position

_MAX_SIGNALS_PER_DIRECTION = 2
_MAX_SIGNALS_PER_FAMILY = 2
_CORRELATED_SIGNAL_LOOKBACK = 12

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Ticket → strategy name mapping
# Exness strips special chars from MT5 comments, so we maintain a
# side-channel file: ticket_id → full_strategy_name.
# live_monitor.py reads this for PnL attribution.
# ---------------------------------------------------------------------------
_TICKET_MAP_PATH = Path(__file__).resolve().parent / "ticket_strategy_map.json"
_TRADES_LOG_PATH = Path(__file__).resolve().parent / "trades.log"
_MAX_TICKET_MAP_SIZE = 2000
_TICKET_MAP_CACHE: Dict[str, str] | None = None
_TICKET_MAP_CACHE_KEY: tuple[float | None, float | None] | None = None


def _rebuild_ticket_map_from_trades_log(limit_lines: int = 5000) -> Dict[str, str]:
    mapping: Dict[str, str] = {}
    if not _TRADES_LOG_PATH.exists():
        return mapping

    ticket_re = re.compile(r"ticket=(\d+)")
    strategy_re = re.compile(r"strategy=([^\s]+)")

    try:
        with _TRADES_LOG_PATH.open("r", encoding="utf-8") as f:
            lines = f.readlines()[-limit_lines:]
    except Exception:
        logger.exception("Failed to read trades.log for ticket-map rebuild")
        return mapping

    for line in lines:
        try:
            t_match = ticket_re.search(line)
            s_match = strategy_re.search(line)
            if not t_match or not s_match:
                continue
            mapping[str(t_match.group(1))] = s_match.group(1)
        except Exception:
            continue
    return mapping


def _load_ticket_map() -> Dict[str, str]:
    global _TICKET_MAP_CACHE, _TICKET_MAP_CACHE_KEY

    file_mtime = _TICKET_MAP_PATH.stat().st_mtime if _TICKET_MAP_PATH.exists() else None
    log_mtime = _TRADES_LOG_PATH.stat().st_mtime if _TRADES_LOG_PATH.exists() else None
    cache_key = (file_mtime, log_mtime)

    if _TICKET_MAP_CACHE is not None and _TICKET_MAP_CACHE_KEY == cache_key:
        return dict(_TICKET_MAP_CACHE)

    file_map: Dict[str, str] = {}
    if _TICKET_MAP_PATH.exists():
        try:
            with _TICKET_MAP_PATH.open("r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                file_map = data
        except Exception:
            logger.exception("Failed to load ticket_strategy_map")

    log_map = _rebuild_ticket_map_from_trades_log()
    merged = {**log_map, **file_map}
    _TICKET_MAP_CACHE = dict(merged)
    _TICKET_MAP_CACHE_KEY = cache_key
    return merged


def _save_ticket_map(mapping: Dict[str, str]) -> None:
    global _TICKET_MAP_CACHE, _TICKET_MAP_CACHE_KEY
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
            _TICKET_MAP_CACHE = dict(mapping)
            file_mtime = _TICKET_MAP_PATH.stat().st_mtime if _TICKET_MAP_PATH.exists() else None
            log_mtime = _TRADES_LOG_PATH.stat().st_mtime if _TRADES_LOG_PATH.exists() else None
            _TICKET_MAP_CACHE_KEY = (file_mtime, log_mtime)
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
    if "XAU" in sym:
        return 0.01, 1.0
    if "XAG" in sym:
        return 0.01, 0.5
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


@dataclass
class RoutingContext:
    regime_label: str
    candidate_regime_labels: List[str]
    regime_class: str
    regime_type: str
    regime_confidence: float
    vol_regime: str
    session: str
    trend_strength: float


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


def _log_gate_summary(
    gate_name: str,
    symbol: str,
    timeframe: str,
    context_label: str,
    tier: str,
    before_count: int,
    after_count: int,
    blocked_items: List[str],
) -> None:
    if not blocked_items:
        return
    logger.info(
        "%s %s %s [%s %s]: %d → %d passed | blocked=%s sample=%s",
        gate_name,
        symbol,
        timeframe,
        context_label,
        tier,
        before_count,
        after_count,
        dict(Counter(item.split(":", 1)[1] for item in blocked_items)),
        blocked_items[:5],
    )



def _regime_edge(stats: Dict[str, Any], regime_labels: List[str]) -> tuple[float, str]:
    if not stats:
        return -999.0, "unknown"
    ex = stats.get("strategy_explain", {}) or {}
    rp = ex.get("regime_pnl", {}) or {}

    best_edge = -999.0
    best_label = "unknown"
    for regime_label in regime_labels:
        regime_stats = rp.get(regime_label, {}) or {}
        try:
            edge = float(regime_stats.get("return_pct", -999.0) or -999.0)
        except Exception:
            edge = -999.0
        if edge > best_edge:
            best_edge = edge
            best_label = regime_label
    return best_edge, best_label


def _family_label_from_strategy(strategy: StrategyDefinition) -> str:
    params = getattr(strategy, "params", None) or {}
    family = params.get("family") or params.get("playbook") or "unknown"
    return str(family or "unknown")


def _recent_signal_overlap_count(strategy_name: str, symbol: str, direction: str, *, lookback_lines: int = 500) -> int:
    if not _TRADES_LOG_PATH.exists():
        return 0

    try:
        with _TRADES_LOG_PATH.open("r", encoding="utf-8") as f:
            lines = f.readlines()[-lookback_lines:]
    except Exception:
        logger.exception("Failed to read trades.log for recent overlap count")
        return 0

    count = 0
    for line in reversed(lines):
        if f"symbol={symbol}" not in line or f"dir={direction}" not in line:
            continue
        count += 1
        if count >= _CORRELATED_SIGNAL_LOOKBACK:
            break
    return count


def _active_directional_exposure(symbol: str) -> tuple[Counter[str], Counter[tuple[str, str]]]:
    direction_counts: Counter[str] = Counter()
    family_counts: Counter[tuple[str, str]] = Counter()

    try:
        import MetaTrader5 as mt5  # type: ignore
    except Exception:
        return direction_counts, family_counts

    try:
        positions = mt5.positions_get(symbol=symbol)
    except Exception:
        logger.exception("Failed to read open positions for active exposure guard")
        return direction_counts, family_counts

    if not positions:
        return direction_counts, family_counts

    buy_type = getattr(mt5, "POSITION_TYPE_BUY", 0)
    sell_type = getattr(mt5, "POSITION_TYPE_SELL", 1)

    for pos in positions:
        ticket = getattr(pos, "ticket", None)
        mapped_name = None
        if ticket is not None:
            try:
                mapped_name = get_strategy_for_ticket(int(ticket))
            except Exception:
                mapped_name = None

        if not mapped_name:
            comment = str(getattr(pos, "comment", "") or "")
            uid4 = comment[-4:].lower() if len(comment) >= 4 else ""
            if uid4:
                try:
                    for candidate_name in _load_ticket_map().values():
                        candidate_name = str(candidate_name)
                        if candidate_name.split("_")[-1][:4].lower() == uid4:
                            mapped_name = candidate_name
                            break
                except Exception:
                    mapped_name = None

        family = "unknown"
        if mapped_name:
            family = _family_label_from_strategy(
                SimpleNamespace(name=mapped_name, params={"family": mapped_name.split("_")[0]})
            )
            try:
                strategy_rec = StrategyPool.load().strategies.get(mapped_name)
                if strategy_rec is not None:
                    family = _family_label_from_strategy(strategy_rec)
            except Exception:
                pass

        pos_type = getattr(pos, "type", None)
        direction = "long" if pos_type == buy_type else "short" if pos_type == sell_type else None
        if not direction:
            continue

        direction_counts[direction] += 1
        family_counts[(direction, family)] += 1

    return direction_counts, family_counts


def _dedupe_correlated_signals(signals: Iterable[Signal], symbol: str) -> tuple[list[Signal], list[str]]:
    ordered_signals = list(signals)
    kept: list[Signal] = []
    blocked: list[str] = []
    overlap_blocked_by_direction: dict[str, list[tuple[Signal, int]]] = defaultdict(list)
    active_direction_counts, active_family_counts = _active_directional_exposure(symbol)
    direction_counts: Counter[str] = Counter(active_direction_counts)
    family_counts: Counter[tuple[str, str]] = Counter(active_family_counts)

    for sig in ordered_signals:
        family = _family_label_from_strategy(sig.strategy)
        direction = sig.direction
        dir_count = direction_counts[direction]
        fam_key = (direction, family)
        fam_count = family_counts[fam_key]
        recent_overlap = _recent_signal_overlap_count(sig.strategy.name, symbol, direction)

        if dir_count >= _MAX_SIGNALS_PER_DIRECTION:
            blocked.append(f"{sig.strategy.name}:direction_cap:{direction}:active={dir_count}")
            continue
        if fam_count >= _MAX_SIGNALS_PER_FAMILY:
            blocked.append(f"{sig.strategy.name}:family_cap:{family}:{direction}:active={fam_count}")
            continue
        if recent_overlap >= _CORRELATED_SIGNAL_LOOKBACK:
            blocked.append(f"{sig.strategy.name}:recent_overlap:{direction}:{recent_overlap}")
            overlap_blocked_by_direction[direction].append((sig, recent_overlap))
            continue

        kept.append(sig)
        direction_counts[direction] += 1
        family_counts[fam_key] += 1

    # Failsafe: correlation control should reduce clustering, not hard-zero every
    # otherwise-valid candidate on a side. If a direction has zero survivors and
    # all remaining candidates were only blocked by recent-overlap, keep the best
    # fallback survivor (lowest overlap, preserving original ordering).
    kept_directions = {sig.direction for sig in kept}
    all_candidate_directions = {sig.direction for sig in ordered_signals}
    for direction in all_candidate_directions:
        if direction in kept_directions:
            continue
        overlap_blocked = overlap_blocked_by_direction.get(direction) or []
        if not overlap_blocked:
            continue
        survivor, overlap = sorted(overlap_blocked, key=lambda item: item[1])[0]
        kept.append(survivor)
        family = _family_label_from_strategy(survivor.strategy)
        direction_counts[direction] += 1
        family_counts[(direction, family)] += 1
        blocked.append(f"{survivor.strategy.name}:correlation_fallback_survivor:{direction}:{overlap}")
        logger.info(
            "Correlation fallback survivor kept for %s: strategy=%s direction=%s overlap=%d",
            symbol,
            survivor.strategy.name,
            direction,
            overlap,
        )

    return kept, blocked


def _current_session_from_row(row: pd.Series) -> str:
    ts = pd.to_datetime(row.get("time"))
    if getattr(ts, "tzinfo", None) is not None:
        ts = ts.tz_convert("UTC")
    hour = int(ts.hour)
    if 0 <= hour < 7:
        return "asia"
    if 7 <= hour < 13:
        return "london"
    return "new_york"


def _build_routing_context(row: pd.Series) -> RoutingContext:
    regime_label = str(row.get("regime", "unknown") or "unknown")
    regime_class = str(row.get("regime_class", "unknown") or "unknown")
    regime_type = str(row.get("regime_type", "unknown") or "unknown")
    vol_regime = str(row.get("vol_regime", "unknown") or "unknown")
    regime_confidence = float(row.get("regime_confidence", 0.0) or 0.0)
    trend_strength = float(row.get("trend_strength", 0.0) or 0.0)
    session = _current_session_from_row(row)

    candidate_labels: List[str] = []
    if regime_label in {"trending_up", "trending_down", "ranging", "high_vol", "low_vol"}:
        candidate_labels.append(regime_label)

    if regime_label == "high_vol":
        if regime_class == "trend":
            candidate_labels.append("trending_up" if trend_strength >= 0 else "trending_down")
        elif regime_class == "range":
            candidate_labels.append("ranging")
    elif regime_label == "low_vol" and regime_class == "range":
        candidate_labels.append("ranging")

    candidate_labels = list(dict.fromkeys([label for label in candidate_labels if label])) or ["unknown"]
    return RoutingContext(
        regime_label=regime_label,
        candidate_regime_labels=candidate_labels,
        regime_class=regime_class,
        regime_type=regime_type,
        regime_confidence=regime_confidence,
        vol_regime=vol_regime,
        session=session,
        trend_strength=trend_strength,
    )


def _passes_session_gate(stats: Dict[str, Any], current_session: str, routing_cfg=routing_config) -> tuple[bool, str]:
    ex = stats.get("strategy_explain", {}) or {}
    meta = ex.get("meta", {}) or {}
    allowed = [str(x) for x in (meta.get("allowed_sessions", []) or [])]
    blocked = [str(x) for x in (meta.get("blocked_sessions", []) or [])]
    best_session = str(meta.get("best_session", "") or "")

    if routing_cfg.enforce_blocked_sessions and current_session in blocked:
        return False, f"session_blocked:{current_session}"
    if routing_cfg.require_best_session_for_entry and best_session and current_session != best_session:
        return False, f"session_not_best:{current_session}:best={best_session}"
    if routing_cfg.enforce_allowed_sessions and allowed and current_session not in allowed:
        return False, f"session_not_allowed:{current_session}"
    return True, "ok"


def _passes_regime_gate(stats: Dict[str, Any], context: RoutingContext, routing_cfg=routing_config) -> tuple[bool, str, str]:
    ex = stats.get("strategy_explain", {}) or {}
    meta = ex.get("meta", {}) or {}
    allowed = [str(x) for x in (meta.get("allowed_regimes", []) or [])]
    blocked = [str(x) for x in (meta.get("blocked_regimes", []) or [])]

    candidate_labels = context.candidate_regime_labels
    blocked_hits = [label for label in candidate_labels if label in blocked]
    if routing_cfg.enforce_blocked_regimes and blocked_hits:
        return False, f"regime_blocked:{','.join(blocked_hits)}", blocked_hits[0]

    if routing_cfg.enforce_allowed_regimes and allowed:
        allowed_hits = [label for label in candidate_labels if label in allowed]
        if not allowed_hits:
            return False, f"regime_not_allowed:{','.join(candidate_labels)}", candidate_labels[0]
        return True, "ok", allowed_hits[0]

    return True, "ok", candidate_labels[0]


def _passes_regime_confidence_gate(context: RoutingContext, tier: str, routing_cfg=routing_config) -> tuple[bool, str]:
    confidence = context.regime_confidence
    min_conf = (
        routing_cfg.min_regime_confidence_active
        if tier == "active"
        else routing_cfg.min_regime_confidence_exploratory
    )

    if confidence < min_conf:
        return False, (
            f"low_routing_confidence:{confidence:.2f}"
            f":class={context.regime_class}:type={context.regime_type}:vol={context.vol_regime}"
        )
    return True, "ok"


def _passes_volatility_gate(stats: Dict[str, Any], context: RoutingContext, routing_cfg=routing_config) -> tuple[bool, str]:
    if not routing_cfg.enforce_volatility_mismatch_gate:
        return True, "ok"

    ex = stats.get("strategy_explain", {}) or {}
    meta = ex.get("meta", {}) or {}
    allowed = [str(x) for x in (meta.get("allowed_regimes", []) or [])]
    blocked = [str(x) for x in (meta.get("blocked_regimes", []) or [])]
    best_regime = str(meta.get("best_regime", "") or "")

    if context.regime_label == "high_vol" and context.regime_class in {"volatility_spike", "event_driven"}:
        if "high_vol" in blocked or best_regime in {"ranging", "low_vol"}:
            return False, f"volatility_mismatch:high_vol:{context.regime_class}:{best_regime or 'unknown'}"
        if allowed and all(label not in {"high_vol", "trending_up", "trending_down"} for label in allowed):
            return False, f"volatility_mismatch:high_vol:{context.regime_class}:allowed={','.join(allowed)}"

    if context.regime_label == "low_vol" and "low_vol" in blocked:
        return False, f"volatility_mismatch:low_vol:{best_regime or 'unknown'}"

    return True, "ok"


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
        "blocked_existing_position": False,
        "blocked_session_gate": False,
        "blocked_regime_gate": False,
        "blocked_routing_confidence": False,
        "blocked_volatility_gate": False,
        "no_strategies_in_pool": False,
        "no_strategies_with_edge": False,
        "no_eligible_specialists": False,
        "no_entry_active": False,
        "no_entry_exploratory": False,
    }

    if features_df.empty:
        logger.warning("Empty features_df for %s %s", symbol, timeframe)
        summary["no_strategies_with_edge"] = True
        return [], summary

    latest = features_df.sort_values("time").iloc[-1]
    context = _build_routing_context(latest)
    current_regime = context.regime_label
    current_session = context.session

    missing_structured_fields = [
        field_name
        for field_name in ("regime_class", "regime_type", "regime_confidence", "vol_regime")
        if field_name not in features_df.columns
    ]
    if missing_structured_fields:
        logger.warning(
            "Structured routing fields missing for %s %s: missing=%s — live routing may over-block or degrade to defaults",
            symbol,
            timeframe,
            missing_structured_fields,
        )
    elif context.regime_confidence <= 0.0:
        logger.warning(
            "Structured routing confidence is %.2f for %s %s at %s (regime=%s class=%s type=%s vol=%s) — check whether features were generated before structured regime enrichment",
            context.regime_confidence,
            symbol,
            timeframe,
            latest.get("time", "?"),
            context.regime_label,
            context.regime_class,
            context.regime_type,
            context.vol_regime,
        )

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

    logger.info(
        "Current routing context for %s %s: regime=%s candidates=%s class=%s type=%s conf=%.2f vol=%s session=%s",
        symbol,
        timeframe,
        current_regime,
        context.candidate_regime_labels,
        context.regime_class,
        context.regime_type,
        context.regime_confidence,
        context.vol_regime,
        current_session,
    )

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
        if rec.status == "active"
        and canonical_symbol(rec.symbol) == canonical_symbol(symbol)
        and rec.timeframe == timeframe
    ]
    exploratory_records = [
        rec for rec in pool.strategies.values()
        if rec.status == "exploratory"
        and canonical_symbol(rec.symbol) == canonical_symbol(symbol)
        and rec.timeframe == timeframe
    ]

    if not active_records and not exploratory_records:
        logger.info("No active/exploratory strategies for %s %s", symbol, timeframe)
        summary["no_strategies_in_pool"] = True
        return [], summary

    def _filter_and_rank(records, tier: str) -> List[Any]:
        if not records:
            return []

        session_eligible: List[Any] = []
        session_blocked: List[str] = []
        for rec in records:
            ok, reason = _passes_session_gate(rec.stats or {}, current_session, routing_cfg=routing_config)
            if ok:
                session_eligible.append(rec)
            else:
                session_blocked.append(f"{rec.name}:{reason}")

        if session_blocked:
            summary["blocked_session_gate"] = True
            _log_gate_summary(
                "Session gate",
                symbol,
                timeframe,
                current_session,
                tier,
                len(records),
                len(session_eligible),
                session_blocked,
            )

        if not session_eligible:
            return []

        confidence_eligible: List[Any] = []
        confidence_blocked: List[str] = []
        for rec in session_eligible:
            ok, reason = _passes_regime_confidence_gate(context, tier, routing_cfg=routing_config)
            if ok:
                confidence_eligible.append(rec)
            else:
                confidence_blocked.append(f"{rec.name}:{reason}")

        if confidence_blocked:
            summary["blocked_routing_confidence"] = True
            _log_gate_summary(
                "Routing confidence gate",
                symbol,
                timeframe,
                f"{current_regime}/{current_session}",
                tier,
                len(session_eligible),
                len(confidence_eligible),
                confidence_blocked,
            )

        if not confidence_eligible:
            return []

        volatility_eligible: List[Any] = []
        volatility_blocked: List[str] = []
        for rec in confidence_eligible:
            ok, reason = _passes_volatility_gate(rec.stats or {}, context, routing_cfg=routing_config)
            if ok:
                volatility_eligible.append(rec)
            else:
                volatility_blocked.append(f"{rec.name}:{reason}")

        if volatility_blocked:
            summary["blocked_volatility_gate"] = True
            _log_gate_summary(
                "Volatility gate",
                symbol,
                timeframe,
                f"{current_regime}/{context.regime_class}/{context.vol_regime}",
                tier,
                len(confidence_eligible),
                len(volatility_eligible),
                volatility_blocked,
            )

        if not volatility_eligible:
            return []

        if current_regime == "unknown":
            logger.warning(
                "Unknown regime for %s %s — passing all %d eligible %s strategies",
                symbol, timeframe, len(volatility_eligible), tier,
            )
            return volatility_eligible

        regime_eligible: List[Any] = []
        regime_policy_blocked: List[str] = []
        selected_regime_labels: Dict[str, str] = {}
        for rec in volatility_eligible:
            ok, reason, selected_label = _passes_regime_gate(rec.stats or {}, context, routing_cfg=routing_config)
            if ok:
                regime_eligible.append(rec)
                selected_regime_labels[rec.name] = selected_label
            else:
                regime_policy_blocked.append(f"{rec.name}:{reason}")

        if regime_policy_blocked:
            summary["blocked_regime_gate"] = True
            _log_gate_summary(
                "Regime policy gate",
                symbol,
                timeframe,
                f"{context.candidate_regime_labels}/{current_session}",
                tier,
                len(volatility_eligible),
                len(regime_eligible),
                regime_policy_blocked,
            )

        if not regime_eligible:
            return []

        threshold = (
            routing_config.active_regime_edge_threshold
            if tier == "active"
            else routing_config.exploratory_regime_edge_threshold
        )
        scored: List[Tuple[float, Any]] = []
        edge_selected_labels: Dict[str, str] = {}
        for rec in regime_eligible:
            edge, edge_label = _regime_edge(rec.stats or {}, context.candidate_regime_labels)
            scored.append((edge, rec))
            edge_selected_labels[rec.name] = edge_label or selected_regime_labels.get(rec.name, "unknown")

        kept = sorted([(e, r) for e, r in scored if e > threshold], key=lambda x: x[0], reverse=True)
        filtered = [r for _, r in kept]

        if scored:
            top_edges = [
                f"{rec.name}:{edge:.3f}@{edge_selected_labels.get(rec.name, 'unknown')}"
                for edge, rec in sorted(scored, key=lambda x: x[0], reverse=True)[:5]
            ]
            logger.info(
                "Regime edge summary %s %s [%s]: threshold=%.2f eligible=%d kept=%d top=%s",
                symbol,
                timeframe,
                tier,
                threshold,
                len(regime_eligible),
                len(filtered),
                top_edges,
            )

        if len(filtered) != len(regime_eligible):
            blocked = [f"{r.name}:{e:.3f}" for e, r in scored if e <= threshold]
            summary["blocked_regime_gate"] = True
            _log_gate_summary(
                "Regime edge filter",
                symbol,
                timeframe,
                f"{current_regime}/{current_session}",
                tier,
                len(regime_eligible),
                len(filtered),
                blocked,
            )

        if (
            not filtered
            and scored
            and tier == "exploratory"
            and routing_config.keep_best_exploratory_on_empty_edge_filter
        ):
            scored.sort(key=lambda x: x[0], reverse=True)
            best_edge, best_rec = scored[0]
            if best_edge >= 0.0:
                filtered = [best_rec]
                logger.info(
                    "Regime fallback %s %s: keeping best exploratory edge=%.2f after eligibility gates",
                    symbol, timeframe, best_edge,
                )
            else:
                logger.info(
                    "Regime fallback %s %s: rejected best exploratory edge=%.2f because it is negative",
                    symbol, timeframe, best_edge,
                )

        return filtered

    active_records = _filter_and_rank(active_records, "active")[:5]
    exploratory_records = _filter_and_rank(exploratory_records, "exploratory")[:3]

    if not active_records and not exploratory_records:
        if summary.get("blocked_session_gate") or summary.get("blocked_regime_gate") or summary.get("blocked_routing_confidence"):
            logger.info("No eligible specialists for %s %s after routing gates", symbol, timeframe)
            summary["no_eligible_specialists"] = True
        else:
            logger.info("No strategies with acceptable edge for %s %s", symbol, timeframe)
            summary["no_strategies_with_edge"] = True
        return [], summary

    from ..strategies.generator import load_strategy
    base_dir = Path(__file__).resolve().parents[1] / "strategies" / "generated"

    def _load_strats(records):
        out = []
        fallback_count = 0
        for rec in records:
            try:
                strategy_payload = ((rec.stats or {}).get("strategy") or {})
                has_manifest_payload = bool(
                    strategy_payload.get("long_entry_rule")
                    or strategy_payload.get("short_entry_rule")
                    or strategy_payload.get("params")
                )
                if has_manifest_payload:
                    entry = {
                        "name": rec.name,
                        "symbol": rec.symbol,
                        "timeframe": rec.timeframe,
                        "long_entry_rule": strategy_payload.get("long_entry_rule"),
                        "short_entry_rule": strategy_payload.get("short_entry_rule"),
                        "exit_rule": strategy_payload.get("exit_rule"),
                        "stop_loss_pips": strategy_payload.get("stop_loss_pips"),
                        "take_profit_pips": strategy_payload.get("take_profit_pips"),
                        "sl_atr_mult": strategy_payload.get("sl_atr_mult"),
                        "tp_atr_mult": strategy_payload.get("tp_atr_mult"),
                        "params": strategy_payload.get("params") or {},
                    }
                    out.append(strategy_definition_from_manifest_entry(entry))
                    continue

                out.append(load_strategy(base_dir / f"{rec.name}.json"))
                fallback_count += 1
            except Exception:
                logger.exception("Failed to load strategy %s", rec.name)
        if fallback_count:
            logger.info(
                "Execution strategy payload fallback for %s %s: %d/%d loaded from generated JSON",
                symbol,
                timeframe,
                fallback_count,
                len(records),
            )
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

        def _snapshot_open_positions():
            try:
                import MetaTrader5 as mt5
                return mt5.positions_get(symbol=symbol)
            except Exception:
                logger.exception("Failed to snapshot open positions for %s %s", symbol, timeframe)
                return None

        open_positions = _snapshot_open_positions() if sigs else None
        if not sigs:
            logger.info(
                "No entry conditions met for %s strategies on %s %s (%d evaluated)",
                tier, symbol, timeframe, len(strategies),
            )
            summary[f"no_entry_{tier}"] = True
            return

        deduped_sigs, blocked_correlated = _dedupe_correlated_signals(sigs, symbol)
        if blocked_correlated:
            logger.info(
                "Correlation gate %s %s [%s]: %d -> %d kept | blocked=%s sample=%s",
                symbol,
                timeframe,
                tier,
                len(sigs),
                len(deduped_sigs),
                dict(Counter(item.split(":", 2)[1] for item in blocked_correlated)),
                blocked_correlated[:5],
            )
        sigs = deduped_sigs
        if not sigs:
            summary[f"no_entry_{tier}"] = True
            return

        logger.info("%d signal(s) from %s strategies for %s %s", len(sigs), tier, symbol, timeframe)

        for sig in sigs:
            strat = sig.strategy
            try:
                if strategy_has_open_position(
                    strategy_name=strat.name,
                    symbol=symbol,
                    timeframe=timeframe,
                    positions=open_positions,
                ):
                    reason = "blocked_existing_position"
                    logger.info(
                        "Trade blocked (%s): strategy=%s symbol=%s timeframe=%s already has an open position",
                        tier,
                        strat.name,
                        symbol,
                        timeframe,
                    )
                    summary["blocked_existing_position"] = True
                    results.append((sig, reason))
                    continue

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
                    open_positions = _snapshot_open_positions()
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