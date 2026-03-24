# Phase 2 – Regime-Aware Live Strategy Selection

**Goal:**

1. Make live execution aware of the **current market regime**.
2. Prefer strategies whose historical performance (`regime_pnl`) shows
   an edge in the current regime.
3. Optionally limit the number of strategies firing in each run to keep
   live behavior focused and controlled.

This file provides **per-file instructions** for implementing Phase 2.

Root path for this project:

```text
C:\Users\afusi\.openclaw\workspace\autonomous_trading_ai
```

---

## 1. `execution/signals.py` – Regime Detection & Edge Computation

**File:** `execution/signals.py`

We will:

1. Read the latest `regime` label from the features DataFrame.
2. Define a helper function to compute a regime-specific edge for a
   strategy based on `strategy_explain.regime_pnl`.
3. Filter and rank `active` and `exploratory` strategies according to
   their edge in the current regime before generating signals.

These changes build on top of Phase 1 (which has already split
`active_records` and `exploratory_records`).

---

### 1.1. Read current regime from latest feature row

In `execute_signals_for_symbol`, we already determine:

```python
    if features_df.empty:
        return []

    latest = features_df.sort_values("time").iloc[-1]
```

Immediately after that, add code to capture the current regime label:

```python
    # Legacy regime label (e.g. "trending_up", "trending_down", "ranging", "high_vol", "low_vol")
    current_regime = str(latest.get("regime", "unknown"))
    logger.info("Current regime for %s %s: %s", symbol, timeframe, current_regime)
```

This uses the existing `regime` column produced by
`research.regime.add_regime_column`.

---

### 1.2. Helper to compute regime-specific edge from stats

At the top level of `execution/signals.py` (near other helpers), add a
new function:

```python
from typing import Any, Dict


def _regime_edge(stats: Dict[str, Any], regime_label: str) -> float:
    """Return a regime-specific edge score for a strategy.

    Uses `strategy_explain.regime_pnl[regime_label].return_pct` when
    available. If the information is missing, falls back to a large
    negative value so the strategy is deprioritized when filtering by
    that regime.
    """
    if not stats:
        return -999.0

    ex = stats.get("strategy_explain", {}) or {}
    rp = ex.get("regime_pnl", {}) or {}
    regime_stats = rp.get(regime_label, {}) or {}
    try:
        return float(regime_stats.get("return_pct", -999.0) or -999.0)
    except Exception:
        return -999.0
```

This function assumes that `regime_label` will be one of the legacy
labels used in `regime_pnl` (e.g. `"trending_up"`, `"trending_down"`,
`"ranging"`).

---

### 1.3. Helper to map current_regime to regime_pnl label

Still in `execution/signals.py`, add a small helper to map the legacy
`current_regime` label to the appropriate key in `regime_pnl`:

```python
def _map_current_to_regime_pnl_label(current_regime: str) -> str:
    """Map the legacy `regime` label to a key in `regime_pnl`.

    This keeps the mapping explicit and easy to adjust.
    """
    if current_regime in {"trending_up", "trending_down", "ranging"}:
        return current_regime

    # High volatility but not clearly trending: treat as high_vol / fallback
    if current_regime in {"high_vol", "low_vol"}:
        # For now, use "ranging" as a conservative default
        return "ranging"

    return "unknown"
```

The mapping can be refined in the future; for now we keep it simple.

---

### 1.4. Filter and rank strategies by regime edge

After collecting `active_records` and `exploratory_records` (as in
Phase 1), we will:

1. Map `current_regime` to a `regime_pnl` label.
2. Filter out strategies with very poor edge in this regime.
3. Sort remaining strategies by descending edge.
4. Optionally limit the number of strategies considered.

Locate the code in `execute_signals_for_symbol` where
`active_records` and `exploratory_records` are defined (from Phase 1):

```python
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

Immediately after this block, add filtering and ranking logic:

```python
    regime_label = _map_current_to_regime_pnl_label(current_regime)

    def _filter_and_rank(records):
        if not records or regime_label == "unknown":
            return records

        scored = []
        for rec in records:
            edge = _regime_edge(rec.stats or {}, regime_label)
            scored.append((edge, rec))

        # Filter out strategies with very poor historical performance
        # in this regime (e.g. worse than -5% return).
        filtered = [rec for edge, rec in scored if edge > -5.0]

        # Sort by edge descending (best first)
        filtered.sort(key=lambda r: _regime_edge(r.stats or {}, regime_label), reverse=True)
        return filtered

    active_records = _filter_and_rank(active_records)
    exploratory_records = _filter_and_rank(exploratory_records)

    # Optionally cap the number of strategies considered per tier
    MAX_ACTIVE_PER_SYMBOL = 5
    MAX_EXPLORATORY_PER_SYMBOL = 3

    if len(active_records) > MAX_ACTIVE_PER_SYMBOL:
        active_records = active_records[:MAX_ACTIVE_PER_SYMBOL]

    if len(exploratory_records) > MAX_EXPLORATORY_PER_SYMBOL:
        exploratory_records = exploratory_records[:MAX_EXPLORATORY_PER_SYMBOL]

    if not active_records and not exploratory_records:
        logger.info(
            "No strategies with acceptable regime edge for %s %s in regime=%s",
            symbol,
            timeframe,
            current_regime,
        )
        return []
```

Notes:

- If `regime_label` is `"unknown"`, the helper simply returns the
  original lists without filtering.
- The threshold `edge > -5.0` is conservative and can be tuned.
- The `MAX_*` caps prevent too many strategies from firing
  simultaneously.

The rest of the function (loading StrategyDefinition instances, generating
signals, and executing trades with different risk tiers) remains as in
Phase 1, but will now operate on the **filtered** sets of records.

---

## 2. Behavioral Summary After Phase 2

After Phase 2 is implemented:

- For each symbol/timeframe, on each execution cycle:
  1. The latest feature row is inspected to determine `current_regime`.
  2. Strategies in the pool are filtered to those with status
     `active` or `exploratory`.
  3. For each status tier:
     - Strategies are evaluated for their historical edge in the
       relevant regime using `strategy_explain.regime_pnl`.
     - Strategies with very poor edge in that regime are dropped.
     - Remaining strategies are sorted by edge and capped to a small
       maximum per tier.
  4. Signals are then generated and executed using the respective risk
     tiers for `active` and `exploratory` strategies.

Result:

- In trending regimes (`trending_up` / `trending_down`), the system
  **prefers strategies that historically perform well in those regimes**.
- In ranging regimes, it **prefers strategies that do not perform
  terribly in ranges**.
- If no strategy shows acceptable edge in the current regime, the system
  will skip trading rather than force low-quality strategies.

---

## 3. Testing & Validation for Phase 2

After applying the above changes on top of Phase 1:

1. **Syntax / import check**
   - Run: `python -m compileall autonomous_trading_ai` or
     `python -c "import autonomous_trading_ai"`.

2. **Dry run execution job**
   - Ensure that features with a valid `regime` column exist.
   - Run `job_execute_signals()` once.
   - Check logs for lines like:

     ```text
     Current regime for XAUUSDm M15: trending_up
     ```

     and

     ```text
     Signal executed (active): ...
     Signal executed (exploratory): ...
     ```

3. **Edge filtering sanity**
   - Inspect the log entries around the filtering:
     - The message

       ```text
       No strategies with acceptable regime edge for ...
       ```

       should only appear when all strategies perform very poorly in the
       current regime historically.
   - Optionally, temporarily log the computed edge per strategy to
     confirm ranking behaves as expected.

Once tests pass, update relevant documentation (see
`DEVELOPMENT_PLAN.md`) and commit changes with a message like:

```text
feat: make live execution regime-aware for active and exploratory strategies
```