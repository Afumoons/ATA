# Phase 1 – Exploratory Status & Risk Tiers

**Goal:**

1. Introduce a new `exploratory` status for strategies in the pool.
2. Ensure `job_research_strategies` can assign `exploratory` status to
   promising-but-not-fully-qualified strategies.
3. Update live execution so that `exploratory` strategies can open trades
   with **reduced per-trade risk**, while keeping `active` strategies at
   the normal risk tier.

This file provides **per-file instructions** for implementing Phase 1.

Root path for this project:

```text
C:\Users\afusi\.openclaw\workspace\autonomous_trading_ai
```

---

## 1. `strategies/pool.py` – Add `exploratory` Status

**File:** `strategies/pool.py`

### 1.1. Extend the `status` comment

Locate the `StrategyRecord` dataclass:

```python
@dataclass
class StrategyRecord:
    name: str
    symbol: str
    timeframe: str
    status: str  # "candidate", "active", "disabled", "retired"
    score: float
    stats: Dict[str, float]
```

Change the `status` comment to include `"exploratory"`:

```python
    status: str  # "candidate", "active", "exploratory", "disabled", "retired"
```

> Note: The status itself is a free-form string; we only document the
> valid values. No additional code changes are needed in this file for
> Phase 1.

---

## 2. `scheduler/main.py` – Assign `exploratory` Status in Research

**File:** `scheduler/main.py`

We will adjust `job_research_strategies()` so that:

- `active` remains reserved for strategies that meet **strict** criteria
  (as defined by `_should_promote`).
- `exploratory` is assigned to strategies that:
  - are `accepted` by evaluation (meet `EvaluationConfig` thresholds),
  - have enough backtest trades (e.g. `num_trades >= 20`), and
  - show positive performance in trending regimes.
- `candidate` remains the default for accepted but weaker strategies.

### 2.1. Locate the status assignment block

Inside `job_research_strategies`, after `eval_result` is computed and
before `pool.upsert_strategy(...)`, there is code similar to:

```python
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
```

### 2.2. Replace with logic that includes `exploratory`

Replace the above block with the following (or logically equivalent)
code:

```python
                # Determine pool status: active / exploratory / candidate / disabled
                ex = eval_result.get("strategy_explain", {}) or {}
                regime = ex.get("regime_pnl", {}) or {}
                trend_ret = (
                    regime.get("trending_up", {}).get("return_pct", 0.0) +
                    regime.get("trending_down", {}).get("return_pct", 0.0)
                )

                num_trades = eval_result.get("num_trades", 0.0) or 0.0

                if _should_promote(eval_result):
                    status = "active"
                elif eval_result.get("accepted"):
                    # Promising enough for exploratory live deployment:
                    # - sufficient trade count,
                    # - positive performance in trending regimes.
                    if num_trades >= 20 and trend_ret > 0.0:
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
```

Notes:

- Thresholds (`num_trades >= 20`, `trend_ret > 0.0`) are intentionally
  modest but non-trivial, so `exploratory` is still filtered.
- `active` logic remains entirely controlled by `_should_promote`.
- `candidate` and `disabled` semantics are unchanged.

---

## 3. `execution/signals.py` – Risk Tiers for Active vs Exploratory

**File:** `execution/signals.py`

We want `execute_signals_for_symbol` to:

1. Treat `active` and `exploratory` strategies separately.
2. Use a **lower risk_perc** for exploratory strategies.

### 3.1. Split pool records by status

Locate the section in `execute_signals_for_symbol` that currently
collects `active` strategies:

```python
    # Active strategies for this symbol/timeframe
    active_records = [
        rec
        for rec in pool.strategies.values()
        if rec.status == "active" and rec.symbol == symbol and rec.timeframe == timeframe
    ]
    if not active_records:
        return []
```

Replace it with code that also collects `exploratory` records:

```python
    # Strategies for this symbol/timeframe
    active_records = [
        rec
        for rec in pool.strategies.values()
        if rec.status == "active" and rec.symbol == symbol and rec.timeframe == timeframe
    ]

    exploratory_records = [
        rec
        for rec in pool.strategies.values()
        if rec.status == "exploratory" and rec.symbol == symbol and rec.timeframe == timeframe
    ]

    if not active_records and not exploratory_records:
        return []
```

### 3.2. Load StrategyDefinition instances for both tiers

Below, where `strategies` are loaded from disk, extend it to handle
both sets.

Existing code (simplified):

```python
    from ..strategies.generator import load_strategy
    from pathlib import Path

    strategies: List[StrategyDefinition] = []
    for rec in active_records:
        path = Path(__file__).resolve().parents[1] / "strategies" / "generated" / f"{rec.name}.json"
        try:
            strategies.append(load_strategy(path))
        except Exception as e:
            logger.exception("Failed to load strategy %s from %s: %s", rec.name, path, e)

    signals = generate_signals_for_row(latest, strategies)
    results: List[Tuple[Signal, str]] = []

    for sig in signals:
        ...
```

Replace this section with code that:

- Loads StrategyDefinition for active and exploratory separately.
- Applies different risk percentages when executing.

Example implementation:

```python
    from ..strategies.generator import load_strategy
    from pathlib import Path

    active_strategies: List[StrategyDefinition] = []
    exploratory_strategies: List[StrategyDefinition] = []

    base_dir = Path(__file__).resolve().parents[1] / "strategies" / "generated"

    # Load active strategies
    for rec in active_records:
        path = base_dir / f"{rec.name}.json"
        try:
            active_strategies.append(load_strategy(path))
        except Exception as e:
            logger.exception("Failed to load active strategy %s from %s: %s", rec.name, path, e)

    # Load exploratory strategies
    for rec in exploratory_records:
        path = base_dir / f"{rec.name}.json"
        try:
            exploratory_strategies.append(load_strategy(path))
        except Exception as e:
            logger.exception("Failed to load exploratory strategy %s from %s: %s", rec.name, path, e)

    results: List[Tuple[Signal, str]] = []

    # Risk tiers
    risk_perc_active = risk_perc
    # Exploratory strategies trade at significantly reduced risk
    risk_perc_exploratory = min(risk_perc * 0.25, 0.1)

    # Generate and execute signals for active strategies
    if active_strategies:
        active_signals = generate_signals_for_row(latest, active_strategies)
        for sig in active_signals:
            strat = sig.strategy
            try:
                res = execute_trade(
                    strategy_name=strat.name,
                    symbol= symbol,
                    direction=sig.direction,
                    risk_perc=risk_perc_active,
                    stop_loss_pips=strat.stop_loss_pips,
                    take_profit_pips=strat.take_profit_pips,
                    pip_size=0.01 if "XAU" in symbol or "XAG" in symbol else 0.0001,
                )
                results.append((sig, res.reason))
                if res.success:
                    logger.info(
                        "Signal executed (active): strategy=%s symbol=%s dir=%s",
                        strat.name,
                        symbol,
                        sig.direction,
                    )
                else:
                    logger.warning(
                        "Signal not executed (active): strategy=%s symbol=%s dir=%s reason=%s",
                        strat.name,
                        symbol,
                        sig.direction,
                        res.reason,
                    )
            except Exception as e:
                logger.exception("Error executing active signal for %s: %s", strat.name, e)
                results.append((sig, f"error: {e}"))

    # Generate and execute signals for exploratory strategies (reduced risk)
    if exploratory_strategies:
        exploratory_signals = generate_signals_for_row(latest, exploratory_strategies)
        for sig in exploratory_signals:
            strat = sig.strategy
            try:
                res = execute_trade(
                    strategy_name=strat.name,
                    symbol=symbol,
                    direction=sig.direction,
                    risk_perc=risk_perc_exploratory,
                    stop_loss_pips=strat.stop_loss_pips,
                    take_profit_pips=strat.take_profit_pips,
                    pip_size=0.01 if "XAU" in symbol or "XAG" in symbol else 0.0001,
                )
                results.append((sig, res.reason))
                if res.success:
                    logger.info(
                        "Signal executed (exploratory): strategy=%s symbol=%s dir=%s",
                        strat.name,
                        symbol,
                        sig.direction,
                    )
                else:
                    logger.warning(
                        "Signal not executed (exploratory): strategy=%s symbol=%s dir=%s reason=%s",
                        strat.name,
                        symbol,
                        sig.direction,
                        res.reason,
                    )
            except Exception as e:
                logger.exception("Error executing exploratory signal for %s: %s", strat.name, e)
                results.append((sig, f"error: {e}"))

    return results
```

Notes:

- We keep the existing `pip_size` logic.
- Daily limits via `can_open_new_trade` remain unchanged and gate
  both `active` and `exploratory` trades.
- The reduced risk for exploratory strategies is intentionally
  conservative.

---

## 4. Testing & Validation for Phase 1

After applying the above changes:

1. **Syntax / import check**
   - Run: `python -m compileall autonomous_trading_ai` or
     `python -c "import autonomous_trading_ai"`.

2. **Dry run research job** (in a safe environment)
   - Run `job_research_strategies()` once (via a small script or
     interactive session) and then inspect `strategies/pool_state.json`:
     - Verify that some strategies can now have status
       `"exploratory"` when they are accepted but not promoted to
       `"active"`.

3. **Dry run execution job**
   - Run `job_execute_signals()` once after features exist.
   - Check logs for entries indicating:
     - "Signal executed (active)..." and/or
     - "Signal executed (exploratory)..."
     - Ensure no unexpected errors occur in `execute_signals_for_symbol`.

Once tests pass, update documentation (see main DEVELOPMENT_PLAN) and
commit changes with a message like:

```text
feat: add exploratory strategy tier and separate risk levels
```