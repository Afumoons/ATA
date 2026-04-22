from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional, List, Dict

import numpy as np
import pandas as pd

from ..logging_utils import get_logger
from ..strategies.base import StrategyDefinition
from .costs import apply_costs, dynamic_spread_multiplier, dynamic_slippage_multiplier

logger = get_logger(__name__)

BACKTESTS_DIR = Path(__file__).resolve().parent
RESULTS_DIR = BACKTESTS_DIR / "results"
RESULTS_DIR.mkdir(exist_ok=True)


@dataclass
class Trade:
    entry_time: pd.Timestamp
    exit_time: pd.Timestamp
    direction: str
    entry_price: float
    exit_price: float
    stop_loss: float
    take_profit: float
    size: float
    pnl: float
    regime: Optional[str] = None


@dataclass
class BacktestResult:
    strategy: StrategyDefinition
    symbol: str
    timeframe: str
    trades: List[Trade]
    equity_curve: pd.Series
    stats: Dict[str, float]

    def to_dict(self) -> Dict:
        return {
            "strategy": self.strategy.to_dict(),
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "trades": [asdict(t) for t in self.trades],
            "equity_curve": [
                {"time": str(ts), "equity": float(val)}
                for ts, val in self.equity_curve.items()
            ],
            "stats": self.stats,
        }


def _build_local_vars(row: pd.Series, bars_since_entry: int = 0) -> Dict:
    local_vars = {k: (v.item() if hasattr(v, "item") else v) for k, v in row.items()}
    local_vars["bars_since_entry"] = int(bars_since_entry)
    return local_vars


def _eval_rule(row: pd.Series, rule: Optional[str], bars_since_entry: int = 0) -> bool:
    if not rule:
        return False
    try:
        return bool(eval(rule, {"__builtins__": {}}, _build_local_vars(row, bars_since_entry=bars_since_entry)))
    except Exception:
        return False


def _get_periods_per_year(symbol: str, timeframe: str) -> float:
    tf = timeframe.upper()
    sym = symbol.upper()

    if any(x in sym for x in ["BTC", "ETH", "LTC", "XRP"]):
        mapping = {
            "M1": 365 * 24 * 60,
            "M5": 365 * 24 * 12,
            "M15": 365 * 24 * 4,
            "M30": 365 * 24 * 2,
            "H1": 365 * 24,
            "H4": 365 * 6,
            "D1": 365,
        }
        return float(mapping.get(tf, 365 * 24 * 4))

    mapping = {
        "M1": 252 * 23 * 60,
        "M5": 252 * 23 * 12,
        "M15": 252 * 23 * 4,
        "M30": 252 * 23 * 2,
        "H1": 252 * 23,
        "H4": 252 * 23 / 4,
        "D1": 252,
    }
    return float(mapping.get(tf, 252 * 23 * 4))


# ---------------------------------------------------------------------------
# Backtest engine
# ---------------------------------------------------------------------------

def run_backtest(
    df: pd.DataFrame,
    strategy: StrategyDefinition,
    initial_equity: float = 10_000.0,
    risk_per_trade_pct: float = 1,
    pip_size: Optional[float] = None,
    max_positions_total: int = 5,
    max_positions_per_strategy: int = 1,
    spread: float = 0.0,
    commission_per_lot: float = 0.0,
    slippage_pips: float = 0.0,
    regime_column: Optional[str] = None,
    periods_per_year: Optional[float] = None,
) -> BacktestResult:
    logger.info(
        "Running backtest for %s on %s %s (len=%d)",
        strategy.name,
        strategy.symbol,
        strategy.timeframe,
        len(df),
    )

    df = df.copy().reset_index(drop=True)
    if df.empty:
        logger.warning(
            "Backtest received empty dataframe for %s on %s %s; returning zero-trade stats",
            strategy.name,
            strategy.symbol,
            strategy.timeframe,
        )
        equity_series = pd.Series([initial_equity], dtype=float)
        stats = _compute_basic_stats(
            equity_curve=equity_series,
            trades=[],
            initial_equity=initial_equity,
            periods_per_year=periods_per_year or 252.0,
        )
        return BacktestResult(
            strategy=strategy,
            symbol=strategy.symbol,
            timeframe=strategy.timeframe,
            trades=[],
            equity_curve=equity_series,
            stats=stats,
        )

    equity = initial_equity
    equity_curve: List[float] = []
    times: List[pd.Timestamp] = []
    trades: List[Trade] = []
    positions: List[Dict] = []
    same_bar_ambiguity_count = 0
    same_bar_ambiguity_stop_loss_count = 0
    same_bar_ambiguity_take_profit_count = 0

    if pip_size is None:
        pip_size = 0.01 if "XAU" in strategy.symbol or "XAG" in strategy.symbol else 0.0001

    use_atr = (
        "atr" in df.columns
        and getattr(strategy, "sl_atr_mult", None) is not None
        and getattr(strategy, "tp_atr_mult", None) is not None
    )
    sl_atr_mult: float = getattr(strategy, "sl_atr_mult", 2.0) or 2.0
    tp_atr_mult: float = getattr(strategy, "tp_atr_mult", 2.0) or 2.0

    has_regime_col = regime_column is not None and regime_column in df.columns
    has_atr_col = "atr" in df.columns
    has_spread_col = "spread" in df.columns

    for i in range(len(df)):
        row = df.iloc[i]
        time = pd.to_datetime(row["time"])
        close = float(row["close"])
        high = float(row["high"])
        low = float(row["low"])

        base_row_spread = float(row.get("spread", spread) or spread) if has_spread_col else float(spread)
        news_delta_min = float(row.get("news_time_delta_min", 9999.0) or 9999.0)
        news_impact = int(row.get("news_impact_level", 0) or 0)
        vol_regime = str(row.get("vol_regime", row.get("regime", "")) or "")

        spread_mult = dynamic_spread_multiplier(
            news_delta_min=news_delta_min,
            news_impact=news_impact,
            vol_regime=vol_regime,
        )
        row_spread = base_row_spread * spread_mult

        effective_slippage_pips = float(slippage_pips) * dynamic_slippage_multiplier(
            news_delta_min=news_delta_min,
            news_impact=news_impact,
            vol_regime=vol_regime,
        )
        if bool(row.get("in_news_lockout", False)):
            effective_slippage_pips += max(1.0, float(slippage_pips) * 1.5)

        local_vars = _build_local_vars(row)

        remaining: List[Dict] = []
        for pos in positions:
            pos["bars_held"] = int(pos.get("bars_held", 0)) + 1
            exit_reason = None
            exit_price = close

            if pos["direction"] == "long":
                hit_sl = low <= pos["stop_loss"]
                hit_tp = high >= pos["take_profit"]
                if hit_sl and hit_tp:
                    same_bar_ambiguity_count += 1
                    same_bar_ambiguity_stop_loss_count += 1
                    same_bar_ambiguity_take_profit_count += 1
                if hit_sl:
                    exit_price = pos["stop_loss"]
                    exit_reason = "stop_loss"
                elif hit_tp:
                    exit_price = pos["take_profit"]
                    exit_reason = "take_profit"
            else:
                hit_sl = high >= pos["stop_loss"]
                hit_tp = low <= pos["take_profit"]
                if hit_sl and hit_tp:
                    same_bar_ambiguity_count += 1
                    same_bar_ambiguity_stop_loss_count += 1
                    same_bar_ambiguity_take_profit_count += 1
                if hit_sl:
                    exit_price = pos["stop_loss"]
                    exit_reason = "stop_loss"
                elif hit_tp:
                    exit_price = pos["take_profit"]
                    exit_reason = "take_profit"

            if exit_reason is None:
                try:
                    if strategy.exit_rule and bool(eval(strategy.exit_rule, {"__builtins__": {}}, _build_local_vars(row, bars_since_entry=pos["bars_held"]))):
                        exit_reason = "exit_rule"
                except Exception:
                    pass

            if exit_reason is not None:
                pnl = apply_costs(
                    direction=pos["direction"],
                    entry_price=pos["entry_price"],
                    exit_price=exit_price,
                    size=pos["size"],
                    spread=row_spread,
                    commission_per_lot=commission_per_lot,
                    slippage_pips=effective_slippage_pips,
                    pip_size=pip_size,
                )
                equity += pnl
                trades.append(Trade(
                    entry_time=pos["entry_time"],
                    exit_time=time,
                    direction=pos["direction"],
                    entry_price=pos["entry_price"],
                    exit_price=exit_price,
                    stop_loss=pos["stop_loss"],
                    take_profit=pos["take_profit"],
                    size=pos["size"],
                    pnl=pnl,
                    regime=pos.get("regime"),
                ))
            else:
                remaining.append(pos)

        positions = remaining

        strategy_open_positions = len(positions)
        can_open_for_strategy = strategy_open_positions < max_positions_per_strategy
        can_open_total = len(positions) < max_positions_total

        if can_open_total and can_open_for_strategy:
            atr_value = float(row["atr"]) if use_atr and has_atr_col else None
            regime_label = str(row[regime_column]) if has_regime_col else None

            def _try_open(direction: str) -> bool:
                nonlocal equity
                if len(positions) >= max_positions_total:
                    return False
                if len(positions) >= max_positions_per_strategy:
                    return False

                if use_atr and atr_value is not None:
                    sl_dist = sl_atr_mult * atr_value
                    tp_dist = tp_atr_mult * atr_value
                else:
                    sl_dist = strategy.stop_loss_pips * pip_size
                    tp_dist = strategy.take_profit_pips * pip_size

                if sl_dist <= 0:
                    return False

                risk_amount = equity * (risk_per_trade_pct / 100.0)
                size = risk_amount / sl_dist

                if direction == "long":
                    entry_price = close + (row_spread / 2.0)
                    sl = entry_price - sl_dist
                    tp = entry_price + tp_dist
                else:
                    entry_price = close - (row_spread / 2.0)
                    sl = entry_price + sl_dist
                    tp = entry_price - tp_dist

                positions.append({
                    "entry_time": time,
                    "entry_price": entry_price,
                    "direction": direction,
                    "size": size,
                    "stop_loss": sl,
                    "take_profit": tp,
                    "regime": regime_label,
                    "bars_held": 0,
                })
                return True

            opened_position = False
            try:
                if strategy.long_entry_rule and bool(eval(strategy.long_entry_rule, {"__builtins__": {}}, local_vars)):
                    opened_position = _try_open("long")
            except Exception:
                pass

            if not opened_position and len(positions) < max_positions_total and len(positions) < max_positions_per_strategy:
                try:
                    if strategy.short_entry_rule and bool(eval(strategy.short_entry_rule, {"__builtins__": {}}, local_vars)):
                        _try_open("short")
                except Exception:
                    pass

        times.append(time)
        equity_curve.append(equity)

    if positions:
        final_row = df.iloc[-1]
        final_time = pd.to_datetime(final_row["time"])
        final_close = float(final_row["close"])
        final_spread = float(final_row.get("spread", spread) or spread) if has_spread_col else float(spread)
        for pos in positions:
            pnl = apply_costs(
                direction=pos["direction"],
                entry_price=pos["entry_price"],
                exit_price=final_close,
                size=pos["size"],
                spread=final_spread,
                commission_per_lot=commission_per_lot,
                slippage_pips=slippage_pips,
                pip_size=pip_size,
            )
            equity += pnl
            trades.append(Trade(
                entry_time=pos["entry_time"],
                exit_time=final_time,
                direction=pos["direction"],
                entry_price=pos["entry_price"],
                exit_price=final_close,
                stop_loss=pos["stop_loss"],
                take_profit=pos["take_profit"],
                size=pos["size"],
                pnl=pnl,
                regime=pos.get("regime"),
            ))
        if times:
            equity_curve[-1] = equity

    equity_series = pd.Series(equity_curve, index=pd.to_datetime(times))

    ppy = periods_per_year or _get_periods_per_year(strategy.symbol, strategy.timeframe)
    stats = _compute_basic_stats(equity_series, trades, initial_equity, ppy)
    stats["same_bar_ambiguity_count"] = float(same_bar_ambiguity_count)
    stats["same_bar_ambiguity_stop_loss_count"] = float(same_bar_ambiguity_stop_loss_count)
    stats["same_bar_ambiguity_take_profit_count"] = float(same_bar_ambiguity_take_profit_count)
    stats["same_bar_ambiguity_rate"] = float(same_bar_ambiguity_count / len(trades)) if trades else 0.0

    try:
        from .explain import build_strategy_explain
        trades_df = pd.DataFrame([t.__dict__ for t in trades]) if trades else pd.DataFrame()
        explain = build_strategy_explain(
            trades=trades_df,
            features=df,
            regime_column=regime_column or "regime",
            initial_equity=initial_equity,
            symbol=strategy.symbol,
        )
        stats["strategy_explain"] = explain
    except Exception as e:
        logger.exception("Failed to build strategy_explain for %s: %s", strategy.name, e)

    logger.info(
        "Backtest complete for %s: trades=%d final_eq=%.2f return=%.2f%% sharpe=%.3f max_dd=%.2f%% same_bar_ambiguity=%d",
        strategy.name,
        len(trades),
        equity,
        stats.get("return_pct", 0.0),
        stats.get("sharpe_ratio", 0.0),
        stats.get("max_drawdown_pct", 0.0),
        same_bar_ambiguity_count,
    )

    return BacktestResult(
        strategy=strategy,
        symbol=strategy.symbol,
        timeframe=strategy.timeframe,
        trades=trades,
        equity_curve=equity_series,
        stats=stats,
    )


# ---------------------------------------------------------------------------
# Stats computation
# ---------------------------------------------------------------------------

def _compute_basic_stats(
    equity_curve: pd.Series,
    trades: List[Trade],
    initial_equity: float,
    periods_per_year: float,
) -> Dict[str, float]:
    if equity_curve.empty:
        return {"final_equity": initial_equity, "max_drawdown_pct": 0.0}

    final_equity = float(equity_curve.iloc[-1])
    returns = equity_curve.pct_change().dropna()

    sharpe = (
        float(np.sqrt(periods_per_year) * returns.mean() / (returns.std() + 1e-9))
        if not returns.empty
        else 0.0
    )

    running_max = equity_curve.cummax()
    max_dd = float((equity_curve / running_max - 1.0).min())

    gains = [t.pnl for t in trades if t.pnl > 0]
    losses = [t.pnl for t in trades if t.pnl < 0]
    gross_profit = float(sum(gains)) if gains else 0.0
    gross_loss = float(-sum(losses)) if losses else 0.0
    profit_factor = gross_profit / (gross_loss + 1e-9) if gross_loss > 0 else 0.0
    win_rate = len(gains) / len(trades) if trades else 0.0

    avg_win = gross_profit / len(gains) if gains else 0.0
    avg_loss = gross_loss / len(losses) if losses else 0.0

    return {
        "initial_equity": float(initial_equity),
        "final_equity": final_equity,
        "net_profit": final_equity - initial_equity,
        "return_pct": (final_equity - initial_equity) / initial_equity * 100.0,
        "sharpe_ratio": sharpe,
        "max_drawdown_pct": max_dd * 100.0,
        "profit_factor": profit_factor,
        "win_rate": win_rate,
        "num_trades": float(len(trades)),
        "avg_win": avg_win,
        "avg_loss": avg_loss,
        "expectancy": (win_rate * avg_win) - ((1 - win_rate) * avg_loss),
    }


# ---------------------------------------------------------------------------
# I/O
# ---------------------------------------------------------------------------

def save_backtest_result(result: BacktestResult) -> Path:
    import json
    path = RESULTS_DIR / f"{result.strategy.name}_{result.symbol}_{result.timeframe}.json"
    with path.open("w", encoding="utf-8") as f:
        json.dump(result.to_dict(), f, indent=2, default=str)
    logger.info("Saved backtest result to %s", path)
    return path
