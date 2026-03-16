# Phase 3 – Strategy Generator Improvements

**Goal:**

1. Increase the proportion of generated strategies that:
   - trade often enough (reasonable `num_trades`), and
   - have structurally sound logic for both trend and range regimes.
2. Make SL/TP sizing more **volatility-aware** (ATR-based, optional but
   recommended).
3. Keep the generator simple and robust, avoiding overfitting and
   excessive complexity.

This file provides **per-file, step-by-step instructions** for
implementing Phase 3.

Root path for this project:

```text
C:\Users\afusi\.openclaw\workspace\autonomous_trading_ai
```

---

## 0. Files Affected in Phase 3

Primary:

- `strategies/generator.py`
- `strategies/base.py` (for optional ATR-based parameters)
- `backtests/engine.py` (only if ATR-based SL/TP is implemented)

Secondary (documentation):

- `strategies/README.md`
- `backtests/README.md`

Phase 3 can be implemented in two sub-steps:

1. **3A – Template extensions** (safe, simple, no change in backtest API).
2. **3B – ATR-based SL/TP** (slightly more involved, touches backtest
   engine).

Background agent should complete 3A first, test, commit, then optionally
proceed to 3B in a separate run.

---

## 3A – Extend Templates for Trend & Range Playbooks

### 3A.1. Add range/mean-reversion templates

**File:** `strategies/generator.py`

Goal: introduce simple range / mean-reversion entry templates using RSI
and low trend_strength.

1. Open `strategies/generator.py` and locate:

   ```python
   LONG_ENTRY_TEMPLATES = [
       # Ichimoku: bullish alignment above the cloud
       "tenkan_sen > kijun_sen and close > senkou_span_a and close > senkou_span_b",
       # Fib + trend
       "fib_zone_382 == 1 and trend_strength > {trend_min}",
   ]

   SHORT_ENTRY_TEMPLATES = [
       # Ichimoku: bearish alignment below the cloud
       "tenkan_sen < kijun_sen and close < senkou_span_a and close < senkou_span_b",
       # Fib + trend
       "fib_zone_618 == 1 and trend_strength < -{trend_min}",
   ]
   ```

2. Append **range/mean-reversion** patterns that use RSI and small
   trend_strength:

   ```python
   # Range / mean reversion: fade extremes when trend_strength is low
   LONG_ENTRY_TEMPLATES.append(
       "rsi < 35 and trend_strength > -0.1 and trend_strength < 0.1"
   )

   SHORT_ENTRY_TEMPLATES.append(
       "rsi > 65 and trend_strength > -0.1 and trend_strength < 0.1"
   )
   ```

   Place these appends immediately after the initial template lists are
declared.

Notes:

- Thresholds (35/65, ±0.1) are deliberately modest; they can be tuned
  later based on research results.
- This change does **not** require any other module changes.

---

### 3A.2. Add simple MA-based trend templates (optional but useful)

Still in `strategies/generator.py`, extend the templates further to
include simple moving-average-based trend-follow entries.

1. After the previous appends, add:

   ```python
   # MA-based trend continuation
   LONG_ENTRY_TEMPLATES.append(
       "ma_short > ma_long and trend_strength > {trend_min}"
   )

   SHORT_ENTRY_TEMPLATES.append(
       "ma_short < ma_long and trend_strength < -{trend_min}"
   )
   ```

2. Ensure that `compute_features` already populates `ma_short` and
   `ma_long` (it does, according to `research/features.py`).

Result:

- Generator can now produce:
  - Ichimoku + fib strategies (existing behavior),
  - Range/mean-reversion strategies,
  - MA-based trend continuation strategies.

---

### 3A.3. Tests & docs for 3A

1. **Syntax / import check**
   - `python -m compileall autonomous_trading_ai` or
     `python -c "import autonomous_trading_ai"`.

2. **Dummy generation test** (optional but recommended)
   - In a small script or REPL:

     ```python
     from autonomous_trading_ai.strategies.generator import generate_batch

     batch = generate_batch("XAUUSDm", "M15", 5)
     for s in batch:
         print(s.name, s.long_entry_rule, s.short_entry_rule)
     ```

   - Confirm that some generated strategies use the new templates
     (`rsi < 35 ...`, `ma_short > ma_long`, etc.).

3. **Docs**
   - Update `strategies/README.md` to:
     - Mention that templates now cover:
       - Ichimoku + fib continuation.
       - Range/mean-reversion with RSI.
       - MA-based trend continuation.

4. **Commit**
   - Commit with a message like:

     ```text
     feat: extend strategy generator with range and MA trend templates
     ```

   - Log the change in `notes/dev_log.md`.

After 3A is complete, the system will explore a richer set of playbooks
without changing SL/TP behavior.

---

## 3B – ATR-Based SL/TP (Optional, More Advanced)

> Only attempt this sub-phase after 3A is implemented, tested, and
> committed.

Goal: allow strategies to use SL/TP distances defined as multiples of
ATR instead of fixed pips, making position sizing more robust to changes
in volatility.

### 3B.1. Extend StrategyDefinition with ATR multipliers

**File:** `strategies/base.py`

1. Locate `StrategyDefinition` dataclass. It currently defines fields
   including `stop_loss_pips`, `take_profit_pips`, and `params`.

2. Add two optional fields with default `None`:

   ```python
   from typing import Optional

   @dataclass
   class StrategyDefinition:
       ...
       stop_loss_pips: int
       take_profit_pips: int
       params: Dict[str, Any]

       # Optional ATR-based risk parameters
       sl_atr_mult: Optional[float] = None
       tp_atr_mult: Optional[float] = None
   ```

3. Ensure `to_dict` / `from_dict` methods (if present) serialize and
   deserialize these fields correctly. If `to_dict()` just does
   `asdict(self)`, no extra work is needed.

---

### 3B.2. Populate ATR multipliers in generator

**File:** `strategies/generator.py`

1. In `random_strategy`, after `params` dict is constructed, define
   random ATR multipliers:

   ```python
   sl_atr_mult = round(random.choice([1.0, 1.5, 2.0]), 2)
   tp_atr_mult = round(random.choice([1.5, 2.0, 2.5]), 2)

   params["sl_atr_mult"] = sl_atr_mult
   params["tp_atr_mult"] = tp_atr_mult
   ```

2. When instantiating `StrategyDefinition`, pass these fields:

   ```python
   strat = StrategyDefinition(
       name=name,
       symbol=symbol,
       timeframe=timeframe,
       long_entry_rule=long_entry_rule,
       short_entry_rule=short_entry_rule,
       exit_rule=exit_rule,
       stop_loss_pips=stop_loss_pips,
       take_profit_pips=take_profit_pips,
       params=params,
       sl_atr_mult=sl_atr_mult,
       tp_atr_mult=tp_atr_mult,
   )
   ```

3. Existing strategies without these fields will still load with
   `sl_atr_mult=None`, `tp_atr_mult=None`.

---

### 3B.3. Use ATR-based SL/TP in backtests (when available)

**File:** `backtests/engine.py`

We modify `run_backtest` so that, when a strategy has ATR multipliers
and the DataFrame has an `atr` column, we compute SL/TP levels based on
ATR instead of fixed pips.

1. In `run_backtest`, after `pip_size` is determined, add:

   ```python
    # ATR-based SL/TP support
    use_atr = "atr" in df.columns and getattr(strategy, "sl_atr_mult", None) is not None
    sl_atr_mult = getattr(strategy, "sl_atr_mult", None)
    tp_atr_mult = getattr(strategy, "tp_atr_mult", None)
   ```

2. When opening positions (inside the loop, in the long/short entry
   sections), adjust the logic:

   **Long entries** – replace the block:

   ```python
            if _eval_rule(row, strategy.long_entry_rule):
                risk_amount = equity * (risk_per_trade_pct / 100.0)
                sl_distance = strategy.stop_loss_pips * pip_size
                if sl_distance > 0:
                    size = risk_amount / sl_distance
                    stop_loss = close - strategy.stop_loss_pips * pip_size
                    take_profit = close + strategy.take_profit_pips * pip_size
                    ...
   ```

   With logic that can use ATR:

   ```python
            if _eval_rule(row, strategy.long_entry_rule):
                risk_amount = equity * (risk_per_trade_pct / 100.0)

                if use_atr and sl_atr_mult is not None and tp_atr_mult is not None:
                    atr_value = float(row["atr"])
                    # Convert ATR to price distance directly (ATR is in price units)
                    sl_distance = sl_atr_mult * atr_value
                    tp_distance = tp_atr_mult * atr_value
                else:
                    sl_distance = strategy.stop_loss_pips * pip_size
                    tp_distance = strategy.take_profit_pips * pip_size

                if sl_distance > 0:
                    size = risk_amount / sl_distance
                    stop_loss = close - sl_distance
                    take_profit = close + tp_distance
                    regime = str(row[regime_column]) if regime_column and regime_column in row else None
                    positions.append(
                        {
                            "entry_time": time,
                            "entry_price": close,
                            "direction": "long",
                            "size": size,
                            "stop_loss": stop_loss,
                            "take_profit": take_profit,
                            "regime": regime,
                        }
                    )
   ```

   **Short entries** – similarly, replace the current block with:

   ```python
            if len(positions) < max_positions_total and _eval_rule(row, strategy.short_entry_rule):
                risk_amount = equity * (risk_per_trade_pct / 100.0)

                if use_atr and sl_atr_mult is not None and tp_atr_mult is not None:
                    atr_value = float(row["atr"])
                    sl_distance = sl_atr_mult * atr_value
                    tp_distance = tp_atr_mult * atr_value
                else:
                    sl_distance = strategy.stop_loss_pips * pip_size
                    tp_distance = strategy.take_profit_pips * pip_size

                if sl_distance > 0:
                    size = risk_amount / sl_distance
                    stop_loss = close + sl_distance
                    take_profit = close - tp_distance
                    regime = str(row[regime_column]) if regime_column and regime_column in row else None
                    positions.append(
                        {
                            "entry_time": time,
                            "entry_price": close,
                            "direction": "short",
                            "size": size,
                            "stop_loss": stop_loss,
                            "take_profit": take_profit,
                            "regime": regime,
                        }
                    )
   ```

Notes:

- ATR is assumed to be in price units (as computed by
  `research/features.compute_atr`).
- Existing behavior is preserved when `sl_atr_mult` / `tp_atr_mult` are
  `None` or `atr` is missing.

---

### 3B.4. Tests & docs for 3B

1. **Syntax / import check**
   - `python -m compileall autonomous_trading_ai` or
     `python -c "import autonomous_trading_ai"`.

2. **Backtest sanity test**
   - Pick a small sample of features with `atr` column present.
   - Run `run_backtest` on a strategy that has `sl_atr_mult` set.
   - Confirm that:
     - positions are opened,
     - SL/TP levels differ when ATR changes,
     - no exceptions are thrown.

3. **Docs**
   - Update `strategies/README.md` to mention ATR-based parameters.
   - Update `backtests/README.md` to mention optional ATR-based SL/TP
     sizing.

4. **Commit**
   - Commit with a message like:

     ```text
     feat: add ATR-based SL/TP support to strategy generator and backtests
     ```

   - Log details in `notes/dev_log.md`.

---

## 4. Safety & Scope Notes for Phase 3

- Do **not** increase risk per trade; ATR-based sizing only changes how
  SL distance is computed, not the fraction of equity at risk.
- Keep generator changes **simple and interpretable**. Avoid adding
  overly complex templates or opaque rule structures.
- If ATR-based SL/TP introduces instability or unexpected behavior in
  tests, it is acceptable to:
  - keep the new fields in `StrategyDefinition`, but
  - temporarily disable `use_atr` (force `use_atr = False`) until a
    human reviews the behavior.

Once Phase 3 is implemented and stable, the system should be exploring a
more diverse and realistic set of strategies, with SL/TP distances that
respond better to changing volatility regimes.