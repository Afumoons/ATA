# Phase 3 – Generator Improvements (More Practical Strategies)

Goal: increase the proportion of generated strategies that are **practical, active, and robust** for:
- **XAUUSD 15m**
- **BTCUSDT 15m**

without weakening risk controls.

The generator should focus on a small set of **simple, interpretable templates** built from:
- Price action
- Moving averages (EMA)
- RSI
- ATR
- (Optionally) Bollinger Bands

and avoid indicator soup (e.g. heavy Ichimoku/Fibonacci mixes) for now.

---

## 1. Template Families

Implement these as new entries in your generator templates (e.g. `LONG_ENTRY_TEMPLATES` / `SHORT_ENTRY_TEMPLATES`), with metadata so later phases can use `regime_type` and `symbol/timeframe` hints.

Each template should carry at least:
- `name`
- `direction` (long/short)
- `regime_type` (e.g. `trend`, `range`, `session_trend`)
- `symbols` / `timeframes` it is primarily designed for (XAUUSD_15m, BTCUSDT_15m)
- Parameter ranges (grids) as described below

### 1.1 Trend-Follow Breakout

**Regime type:** `trend`

**Applies to:**
- `XAUUSD_15m`
- `BTCUSDT_15m`

**Core logic (long):**
- Trend filter:
  - `EMA(ma_fast) > EMA(ma_slow)`
- Breakout:
  - `close > highest(high, breakout_lookback)`
- Entry:
  - Enter long on bar close when both conditions hold.
- Stop loss:
  - `SL = entry_price - sl_atr_mult * ATR(atr_period)`
- Take profit:
  - `TP = entry_price + tp_atr_mult * ATR(atr_period)`
- Optional early exit:
  - Exit if `close < EMA(ma_fast)` before SL/TP.

**Short version:** mirror conditions.

**Suggested parameter grids:**
- `ma_fast` ∈ {10, 14, 20}
- `ma_slow` ∈ {40, 50, 80}
  - Constraint: `ma_slow > ma_fast`.
- `breakout_lookback` ∈ {20, 40, 60}
- `atr_period` = 14
- `sl_atr_mult` ∈ {1.5, 2.0, 2.5}
- `tp_atr_mult` ∈ {2.0, 3.0, 4.0}

---

### 1.2 Pullback-in-Trend

**Regime type:** `trend`

**Applies to:**
- `XAUUSD_15m`
- `BTCUSDT_15m`

**Core logic (long):**
- Trend filter:
  - `EMA(ma_trend)` sloping up (approximation: `EMA(ma_trend) > EMA(ma_trend, offset=trend_lookback)`), and
  - `close > EMA(ma_trend)`.
- Pullback condition:
  - `close <= EMA(ma_pullback)` (price pulls back to/through fast MA), and
  - `RSI(rsi_period)` in a mild pullback range: `[rsi_pullback_low, 50]`.
- Entry:
  - Bullish bar off MA: `close > open` AND `close > EMA(ma_pullback)` after touching/breaking below it.
- Stop loss:
  - Below recent swing low **or** `entry_price - sl_atr_mult * ATR(atr_period)`.
- Take profit:
  - `entry_price + tp_atr_mult * ATR(atr_period)` **or** trailing exit when `close < EMA(ma_pullback)`.

**Short version:** invert all conditions.

**Suggested parameter grids:**
- `ma_trend` = 50 (EMA)
- `ma_pullback` = 20 (EMA)
- `trend_lookback` ∈ {10, 20}
- `rsi_period` = 14
- `rsi_pullback_low` ∈ {35, 40, 45} (cap logic at ≤ 50)
- `atr_period` = 14
- `sl_atr_mult` ∈ {1.5, 2.0, 2.5}
- `tp_atr_mult` ∈ {2.0, 2.5, 3.0}

---

### 1.3 Range RSI Mean-Reversion

**Regime type:** `range`

**Applies to:**
- `XAUUSD_15m`
- `BTCUSDT_15m`

**Core logic (long):**
- Regime filter (no strong trend):
  - `abs((close - EMA(ma_mid)) / ATR(atr_period)) < max_distance_atr`, and optionally
  - A low-trend proxy (e.g. ADX(14) < 20) if available.
- Entry:
  - `RSI(rsi_period) < rsi_oversold`, and
  - `close <= lower_bollinger(bb_period, bb_std)`.
- Stop loss:
  - `entry_price - sl_atr_mult * ATR(atr_period)`.
- Take profit:
  - Either `EMA(ma_mid)` or `entry_price + tp_atr_mult * ATR(atr_period)` (whichever exits first).

**Short version:**
- `RSI > rsi_overbought` and `close >= upper_bollinger`, TP at EMA or ATR multiple.

**Suggested parameter grids:**
- `ma_mid` = 50 EMA
- `rsi_period` = 14
- `rsi_oversold` ∈ {25, 30, 35}
- `rsi_overbought` ∈ {65, 70, 75}
- `bb_period` = 20
- `bb_std` = 2.0
- `atr_period` = 14
- `max_distance_atr` ∈ {0.5, 1.0}
- `sl_atr_mult` ∈ {1.0, 1.5, 1.8}
- `tp_atr_mult` ∈ {1.5, 2.0, 2.5}

> Governance note: even if backtest metrics look good, **range mean-reversion** strategies on 15m can be nasty. When mapping to statuses, it’s reasonable to treat these as `exploratory` first.

---

### 1.4 Session Breakout

**Regime type:** `session_trend`

**Applies to:**
- `XAUUSD_15m` (priority)
- `BTCUSDT_15m`

**Core logic (long):**
- Time filter (session-specific):
  - Only trade during defined high-liquidity windows, e.g. London or NY sessions (convert to server timezone in implementation).
- Pre-session range:
  - For the last `pre_session_lookback` bars, compute:
    - `session_low = lowest(low, pre_session_lookback)`
    - `session_high = highest(high, pre_session_lookback)`
- Volatility filter:
  - `ATR(atr_period) > atr_min` (avoid dead volatility).
- Entry:
  - `close > session_high`
  - `ATR(atr_period) > atr_min`
- Stop loss:
  - `entry_price - sl_atr_mult * ATR(atr_period)`.
- Take profit:
  - `entry_price + tp_atr_mult * ATR(atr_period)`.

**Short version:** breakout below `session_low` with analogous rules.

**Suggested parameter grids:**
- `pre_session_lookback` ∈ {12, 16, 20} (≈ 3–5 hours on 15m)
- `atr_period` = 14
- `atr_min` can be implemented as e.g. a fraction of recent median ATR:
  - `atr_min_mult` ∈ {0.6, 0.8, 1.0} × median ATR(atr_period) over last X days
  - or 
  - a static value per symbol/TF if simpler (choose sensible defaults).
- `sl_atr_mult` ∈ {1.5, 2.0}
- `tp_atr_mult` ∈ {2.0, 2.5, 3.0}
- Session windows:
  - Encode symbolic identifiers like `session_window = 'london' | 'ny'` and let execution-time code map those to timestamps.

---

## 2. Symbol/Timeframe Targeting

To actually get **enough trades** on the key markets, bias generation toward:

- `XAUUSD_15m`
- `BTCUSDT_15m`

Implementation suggestions:
- Allow templates to specify a preferred list of `(symbol, timeframe)` tuples.
- When sampling new candidates, overweight those symbol/TF combos.
- You may still allow templates to be reused on other symbols/TFs, but treat these two as primary for this phase.

---

## 3. Hard Filters for Backtest Results

These filters aim to remove obviously bad / overfitted strategies and raise the base quality of what reaches `candidate` / `exploratory` / `active`.

### 3.1 Minimum Trade Count

For 15m XAU/BTC, require **sufficient activity** over the backtest window:

- Backtest window: at least **6–12 months** of data.
- Hard floor: `num_trades >= 50`.
- Preferred: `num_trades >= 80`.

If a candidate fails `num_trades >= 50`, **discard it**, regardless of other stats.

### 3.2 Performance Floors

Starting thresholds (tune later if nothing passes):

- Profit Factor (`pf`) ≥ **1.3**
- Sharpe Ratio ≥ **0.5**
- Max drawdown (normalized to per-trade risk) within existing risk budget.

If these thresholds are too strict in practice, relax in this order:

1. Sharpe floor down toward ~0.2 (but not below 0.0).
2. Profit factor floor down toward ~1.15.
3. **Do not relax drawdown/risk limits** without explicit plan changes.

### 3.3 Indicator Simplicity / No Indicator Soup

At generation time, enforce:

- Each strategy uses **at most 2–3 core indicators** (e.g. EMA + RSI + ATR or EMA + Bollinger + ATR).
- Avoid mixing heavy constructs like Ichimoku + MACD + multiple oscillators in a single rule.
- For this phase, **down-weight or temporarily exclude** Ichimoku/Fibonacci-based templates from the generator. We can reintroduce 1–2 carefully constrained variants later once the MA/RSI/ATR families are working well.

---

## 4. Status / Risk Tier Mapping Guidance

These generator changes interact with Phase 1+2 logic for statuses and risk tiers:

- **Trend-Follow Breakout / Pullback / Session Breakout:**
  - Eligible for `active` **if** they meet the stricter thresholds for active strategies in `job_research_strategies`.
  - Otherwise, they may be promoted to `exploratory` if they satisfy the criteria for that tier (e.g. minimum trade count, positive performance in relevant regimes).

- **Range RSI Mean-Reversion:**
  - By default, treat as `exploratory` even with good backtest stats, due to mean-reversion risk on 15m.
  - Only promote to `active` with strong, stable performance and when it fits the overall risk plan.

Ensure that Phase 1 logic for:
- `StrategyRecord.status`,
- promotion/demotion between `candidate` / `exploratory` / `active`,

is applied **after** these generator filters and metrics are computed.

---

## 5. Regime Metadata for Phase 2

To support Phase 2 regime-aware selection, add simple metadata to each template:

- `regime_type`:
  - `trend` for Trend Breakout / Pullback
  - `range` for RSI Mean-Reversion
  - `session_trend` for Session Breakout

Later, when computing `strategy_explain.regime_pnl` and selecting strategies in `execute_signals_for_symbol`, this metadata can be combined with regime labels and regime-specific performance to:
- Prefer `trend` strategies in trending regimes,
- Prefer `range` strategies in ranging regimes,
- Prefer `session_trend` strategies during high-impact sessions.

---

## 6. Implementation Checklist for the Dev Agent

When working on Phase 3:

1. **Review existing generator code**
   - Identify where `LONG_ENTRY_TEMPLATES` / `SHORT_ENTRY_TEMPLATES` (or equivalent) live.
   - Identify where backtest stats (num_trades, pf, Sharpe, etc.) are computed and stored.

2. **Add the new template families**
   - Implement the four families above with parameter grids and metadata.
   - Ensure they are wired to XAUUSD_15m and BTCUSDT_15m as preferred symbol/TF combos.

3. **Implement hard filters**
   - Enforce minimum trade count and performance floors when evaluating candidates.
   - Discard strategies that fail hard constraints.

4. **Enforce simplicity / down-weight Ichimoku & Fibonacci**
   - Either disable existing heavy indicator templates or reduce their generation probability.

5. **Tag templates with regime metadata**
   - Add `regime_type` for each template family.

6. **Run basic tests**
   - `python -m compileall autonomous_trading_ai` **or** `python -c "import autonomous_trading_ai"`.
   - If a test suite exists, run it (e.g. `pytest`).

7. **Git + dev log**
   - Commit changes with a clear message (e.g. `feat: add xau/btc 15m generator templates`).
   - Append an entry to `notes/dev_log.md` summarizing:
     - Phase: Phase 3 – generator improvements
     - Changes: which template families / filters were added
     - Tests run and results
     - Any follow-up TODOs or tuning notes.

8. **WhatsApp status report**
   - In the cron-run summary, explicitly mention:
     - New template families (trend breakout, pullback, range RSI, session breakout)
     - That they are targeted at XAUUSD/BTCUSDT 15m
     - Any observed impact on strategy counts (`candidate` / `exploratory` / `active`).
