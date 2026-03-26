# backtests/ – Simulation, Evaluation & Explainability

## Purpose

This module runs **offline simulations** of strategies over historical data,
computes evaluation metrics, and builds structured explanations of behavior.

It provides:

- A bar-by-bar backtest engine with position management and trading costs.
- Strategy evaluation & scoring logic used by the research loop.
- Walk-forward validation for robustness.
- Monte Carlo PnL stress testing.
- `strategy_explain` objects (regime/session/risk/news behavior) used to
  enrich evaluation and pool promotion.

## Key Files

- `engine.py`
  - Core backtest engine and result structures.
  - `Trade` dataclass – single closed trade with:
    - `entry_time`, `exit_time`, `direction`, `entry_price`, `exit_price`,
      `stop_loss`, `take_profit`, `size`, `pnl`, optional `regime`.
  - `BacktestResult` dataclass – per-strategy summary:
    - `strategy`, `symbol`, `timeframe`, list of `trades`,
      `equity_curve` (pandas Series), `stats` dict.
    - `to_dict()` for JSON serialization (equity index → ISO strings).
  - `_eval_rule(row, rule)` – evaluates boolean rule strings against a feature row
    using a restricted `eval` namespace (only numeric fields from the row).
  - `TIMEFRAME_PERIODS_PER_YEAR` – mapping from timeframe to approx. periods/year
    for Sharpe scaling.
  - `run_backtest(df, strategy, ...)`:
    - Assumes `df` has `time, open, high, low, close` + feature columns.
    - Simulates multi-position long/short entries subject to `max_positions_total`.
    - Sizing per trade: risk-based using `risk_per_trade_pct` and SL distance.
    - SL/TP can be defined as fixed pips (`stop_loss_pips`/`take_profit_pips`) or
      as multiples of ATR when `strategy.sl_atr_mult` / `strategy.tp_atr_mult`
      are set and an `atr` column is present in `df`.
    - Applies costs via `apply_costs(...)` from `costs.py` (spread, commission, slippage).
    - Supports optional `regime_column` to tag trades with a regime string.
    - Tracks equity over time and computes basic stats via `_compute_basic_stats`.
    - Tries to build a `strategy_explain` (see `explain.py`) and attach it under
      `stats["strategy_explain"]`.
  - `_compute_basic_stats(equity_curve, trades, initial_equity, timeframe)`:
    - Computes:
      - `final_equity`, `net_profit`, `return_pct`.
      - `sharpe_ratio` using timeframe scaling.
      - `max_drawdown_pct` from equity curve.
      - `profit_factor` from gross profit/loss.
      - `win_rate`, `num_trades`.
  - `save_backtest_result(result)` – writes JSON files under
    `backtests/results/{strategy}_{symbol}_{timeframe}.json`.

- `evaluation.py`
  - Config + logic for turning backtest stats into a **single score** and an
    acceptance decision.
  - `EvaluationConfig` dataclass:
    - `min_trades`, `min_sharpe`, `max_drawdown_pct`, `min_profit_factor`.
    - Weights: `weight_sharpe`, `weight_profit_factor`, `weight_drawdown_penalty`.
  - `compute_score(stats, cfg=DEFAULT_EVAL_CONFIG)`:
    - Computes a base weighted score from Sharpe, profit factor, and a drawdown
      penalty (linear decay to 0 at `max_drawdown_pct`).
    - Adjusts the score using `strategy_explain` when available:
      - **Regime behavior** (`regime_pnl`): bonus for positive trend performance
        and non-disastrous range performance.
      - **Stability** (`stability`): penalty for high `sharpe_std`.
      - **News behavior** (`news_behavior`): penalty if high-impact news trading
        is consistently negative; bonus for good avoidance behavior.
  - `passes_thresholds(stats, cfg)` – enforces minimum requirements on
    trades/Sharpe/DD/profit factor.
  - `evaluate_strategy(stats, cfg)` – wraps everything into a new stats dict with
    `score` and boolean `accepted`.

- `explain.py`
  - Builds the `strategy_explain` object used by evaluation and the pool.
  - `build_strategy_explain(trades, features, regime_column="regime", initial_equity=None, symbol=None)`:
    - Expects trade records with times, prices, SL/TP, and PnL; and a feature
      DataFrame with `time`, a `regime` column, and optional `news_*` columns.
    - Maps trades to their nearest feature row at entry time.
    - Infers per-trade:
      - risk-reward (`RR`),
      - exit type (SL / TP / RULE) based on `exit_price` vs `sl`/`tp`,
      - session bucket (asia / london / new_york).
    - Produces several sections:
      - `regime_pnl` – PnL, returns, trade counts, RR and win rate by regime.
      - `session_pnl` – return and trade count by session.
      - `risk_behavior` – average RR, SL/TP/exit-rule ratios, holding time,
        max consecutive losses.
      - `stability` – sub-period Sharpe & returns, plus `sharpe_std`.
      - `news_behavior` – performance around news (when news features exist):
        high-impact window PnL, pre/post news performance, avoidance rate.
      - `meta` – high-level characterization and explicit routing hints, including:
        - `best_regime`, `worst_regime`
        - `best_session`, `worst_session`
        - `best_regime_return_pct`, `worst_regime_return_pct`
        - `best_session_return_pct`, `worst_session_return_pct`
        - `allowed_regimes`, `blocked_regimes`
        - `allowed_sessions`, `blocked_sessions`
        - `routing_confidence`
        - trend follower vs range trader flags.

- `walkforward.py`
  - Implements walk-forward validation over time-series data.
  - `WalkForwardConfig` – number of splits and train ratio per split.
  - `_split_walkforward_indices(n, n_splits, train_ratio)` – builds index ranges
    for train/test segments.
  - `walk_forward_test(df, strategy, cfg=None, **backtest_kwargs)`:
    - Sorts by time and splits the data into `n_splits` folds.
    - For each fold:
      - Uses the first part as train (currently unused, future hook for tuning).
      - Runs `run_backtest` on the test portion.
    - Aggregates all out-of-sample equity curves to compute:
      - overall Sharpe (scaled with 252),
      - overall max drawdown,
      - number of windows.
    - Returns:
      - `{"windows": [...], "aggregate": {...}}`.

- `monte_carlo.py`
  - Monte Carlo stress testing for a list of trades.
  - `monte_carlo_pnl(trades, n_runs=1000, slippage_std_pips=0.0, pip_size=0.0001)`:
    - Randomizes trade order per run.
    - Optionally applies random slippage in pips.
    - Accumulates equity, tracks max drawdown per run.
    - Returns distribution stats:
      - `mc_final_equity_mean`, `mc_final_equity_p5`, `mc_final_equity_p95`.
      - `mc_max_dd_mean`, `mc_max_dd_p5`, `mc_max_dd_p95`.

## Directories

- `backtests/results/`
  - JSON files storing `BacktestResult` outputs.
  - Used mainly for offline inspection and AI-assisted research (e.g. exported
    views of top/bottom strategies).

## How It’s Used

- `scheduler/job_research_strategies()`:
  - For each candidate strategy:
    - Calls `run_backtest(...)` with `regime_column="regime"`.
    - Passes `result.stats` into `evaluate_strategy(...)`.
    - Optionally runs `walk_forward_test(...)` and `monte_carlo_pnl(...)` and
      merges their aggregate stats into `eval_result`.
    - Stores `strategy_explain` inside stats, which then feeds into the scoring
      and `ResearchMemory`.

## Gotchas / Notes

- `_eval_rule` relies on `eval` with a restricted namespace; rules are generated
  by the system itself, not from arbitrary user input.
- Backtests are **single-symbol** and bar-based; they do not model
  multi-asset margin interactions or broker-specific quirks.
- The current walk-forward implementation does not re-optimize strategy
  parameters per window; it is purely an out-of-sample validation of a fixed
  strategy spec.
- Monte Carlo assumes independence of trade outcomes when shuffling; in
  practice, serial correlation may exist and is not modeled here.
