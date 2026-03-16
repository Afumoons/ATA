# Improvement Opportunities – autonomous_trading_ai

Snapshot as of 2026-03-12 – potential future upgrades we discussed.

## 1. Daily PnL wiring (live MT5 → DailyState) **[IMPLEMENTED 2026-03-12]**

**Goal:** Make `daily_pnl`, `daily_return_pct`, and `trades_today` reflect *real* closed PnL from MT5, so daily limits (if enabled) are meaningful.

**Design outline (agreed):**
- Add `closed_trades_state.json` under `execution/` to track:
  - `last_check_time` (ISO-8601 UTC)
  - `processed_deal_ids` (list of MT5 deal tickets already accounted for)
- In `execution/live_monitor.update_live_stats()`:
  - Load `closed_trades_state`.
  - Call `mt5.history_deals_get(last_check_time, now)`.
  - Filter for *close* deals (profit/loss realized) and exclude processed tickets.
  - For each new deal:
    - `pnl = deal.profit`.
    - `equity_now = _get_account_equity()`.
    - Call `register_trade_pnl(pnl, equity_now)` from `execution/live_state_utils`.
    - Append `deal.ticket` to `processed_deal_ids`.
  - Update `last_check_time = now`, save state.

**Impact:**
- Enables accurate daily loss / trade counts.
- Makes `daily_limits_enabled` safe to turn on later.

---

## 2. AI-assisted research – Level 2 (lightweight)

**Goal:** Let Clio do periodic pattern analysis on the strategy pool (not every cycle), even on a free/limited API budget.

**Ideas:**
- Build a small script (e.g. `scripts/ai_review_pool.py`) that:
  - Loads a *compressed* view of top/bottom strategies (reusing `ai_research_input.json` or a smaller variant).
  - Sends a short summary to Clio via OpenClaw for:
    - High-level pattern detection (what works/fails, by regime/session/news).
    - Suggestions for:
      - Generator templates (e.g. more/less Ichimoku, add RSI/ATR filters).
      - Evaluation tweaks (e.g. slightly different thresholds per regime type).
  - Writes a short "research notes" file (markdown) with recommendations for future implementation.

**Constraints:**
- Run **rarely** (e.g. manual trigger or at most once per day).
- Keep prompts compact (top 10 + bottom 5, minimal fields).
- No runtime dependency for live trading.

---

## 3. AI-assisted research – Level 3 (model-guided generation & scoring)

**Goal:** Move from "AI membantu membaca hasil riset" ke **"AI ikut mengarahkan riset"**.

**Ideas:**
- Tambah modul `ml_research/` yang berfokus pada meta-analisis strategi:
  - `strategy_meta_dataset.py` – membangun dataset dari `strategy_explain`, stats backtest, dan hasil live.
  - `meta_ranker.py` – model (mis. gradient boosting) yang memprediksi "survival probability" atau expected live edge dari strategi baru.
  - `guided_generator.py` – adaptor antara `generator/evolution` dan meta_ranker:
    - generate batch strategi → skor dengan meta_ranker → hanya subset teratas yang masuk ke backtest penuh.
- Integrasi dengan Chroma (`ResearchMemory`):
  - Gunakan similarity search untuk menemukan strategi mirip yang historically survive / gagal dan pakai itu sebagai fitur tambahan di meta_ranker.
- Feedback loop live:
  - Label tambahan: "live_outperform / live_underperform" untuk strategi yang sudah jalan cukup lama, sebagai target training untuk meta_ranker.

**Impact:**
- Mengurangi waktu & biaya compute karena backtest yang mahal hanya dijalankan pada kandidat yang sudah disaring.
- Membuka jalan ke **self-improving research loop**: sistem belajar pola strategi yang cenderung bertahan di live dan mengarahkan generator/evolution ke arah itu.

---

## 4. Session-aware behavior

**Goal:** Use `session_pnl` from `strategy_explain` to shape which strategies are active in which sessions (Asia/London/NY) or to bias evolution.

**Ideas:**
- Extend promotion logic in `scheduler/main.py` to:
  - Prefer strategies with positive/robust performance in the session you care most about (e.g. London/NY for XAUUSDm).
- Future: introduce session filters in `job_execute_signals` so certain strategies are only allowed to trade in certain sessions.

---

## 5. Post-session auto journaling

**Goal:** Mirror your manual journaling workflow (journal-YYYY-MM.md) using live trade data.

**Ideas:**
- Build a script (e.g. `scripts/export_live_trades_for_journal.py`) that:
  - Reads MT5 history for a given day.
  - Produces a markdown/CSV chunk following `trading-journal-template.md`.
  - Optionally tags trades by regime, setup type (if inferable), and news context.

---

## 6. Regime_structured rollout

Right now, we still use the legacy `regime` label column in many places. We have a richer
`detect_regime_structured` implementation that could be adopted more widely.

**Future work:**
- Replace `add_regime_column` calls with `detect_regime_structured` and store additional
  regime fields (`regime_class`, `regime_type`, `regime_confidence`, `regime_hints`).
- Allow strategies to reference these richer fields in their rules.

---

## 7. Parameterized risk profiles

**Goal:** Make it easy to switch between conservative / normal / aggressive risk profiles.

**Ideas:**
- Add a high-level risk mode in `RiskConfig` (e.g. `risk_mode = "aggressive"`).
- Derive `max_risk_per_trade_pct`, `max_portfolio_drawdown_pct`, and daily limits from that mode.
- Later: use `regime_hints` to adapt risk per trade based on regime (within safe bounds).

---

## 8. Live-performance aware strategy management

Beyond the implemented conservative *degradation* rules (demoting clearly
underperforming live strategies from `active` → `candidate`), a future extension
is to also **flag strategies whose live performance substantially exceeds their
backtest** despite weak historical stats.

**Goal:** Treat "backtest jelek, tapi 30 trade terakhir live bagus" as a
research signal, bukan langsung auto-promote.

**Ideas:**
- During `_apply_live_degradation` (or a sibling function), detect strategies where:
  - backtest `return_pct` and/or `sharpe_ratio` are low/negative, **but**
  - recent live return (rolling window) is significantly positive.
- Instead of promoting them automatically, annotate their `stats` with a flag, e.g.:
  - `stats["live_anomaly"] = "outperforming_backtest"`.
- Use this flag in AI-assisted research (Level 2/3) to:
  - surface them as R&D candidates for manual/AI review,
  - analyse whether the live edge is structural or hanya noise/regime-specific.

**Impact:**
- Menangkap potensi edge baru tanpa mengorbankan disiplin risk.
- Memisahkan:
  - "strategi yang kebetulan hoki" vs
  - "strategi yang mungkin menangkap perubahan struktur market".
- Menjaga sistem tetap **conservative di eksekusi**, tapi **curious di riset**.

---

## 9. External review – ChatGPT assessment snapshot (2026-03-12)

**Summary:**
- Overall system assessed as an **Advanced Autonomous Research + Execution Engine (~7.5–8/10 maturity)** for an individual developer / small quant lab.
- Strengths:
  - Full research loop (data → features → regime → strategy generation → backtest → evaluation → robustness → pool → execution).
  - Strategy evolution (elite selection, mutation, crossover).
  - Robustness testing (walk-forward, Monte Carlo).
  - Separated risk layer before MT5 execution.
  - Daily state control (PnL, trade caps, loss caps).
  - Strategy pool with statuses (`active`, `candidate`, `disabled`).
  - Scheduler orchestration for 24/7 operation.
  - Research memory (Chroma) + explainability.

**Identified missing components / future upgrade axes (ChatGPT):**
- Portfolio intelligence:
  - Account for correlation, clustered exposure, portfolio-level risk when selecting strategies.
  - Consider mean-variance / risk-parity / hierarchical risk parity style allocators.
- Strategy allocation engine:
  - Capital weighting per strategy based on Sharpe, stability, recent performance, and regime suitability (not equal-weight).
- Regime-adaptive allocation:
  - Use existing regime detection to route capital:
    - trend regimes → trend-follow strategies,
    - range regimes → mean reversion,
    - high-vol regimes → breakout, etc.
- Strategy degradation detection:
  - Detect edge decay in live trading and auto-quarantine strategies, e.g.:
    - live Sharpe < 0.5 × backtest Sharpe,
    - prolonged underperformance vs expectations.
- Position sizing engine:
  - Move beyond fixed risk% per trade towards volatility targeting / Kelly-style fractions / risk-parity sizing (within safe bounds).
- Research intelligence loop:
  - Use vector memory + explainability to *guide* strategy generation/evolution instead of pure generate→test.
- Portfolio backtesting:
  - Simulate portfolio-level equity & drawdown for combinations of strategies, not just per-strategy.
- Execution robustness:
  - Add retries, latency tolerance, spread-spike guards, partial-fill handling to the MT5 execution layer.

**Autonomy level framing (ChatGPT):**
- Current level estimated as **Level 7 – evolving autonomous research system** on a 1–10 autonomy scale.
- Clear path to Level 8–9 once portfolio intelligence, regime-adaptive allocation, and degradation detection are implemented.

---

## 10. External review – Claude assessment snapshot (2026-03-12)

**Summary:**
- Architecture considered **solid for a personal autonomous trading system**.
- End-to-end pipeline (data → features → strategy generation → backtesting → risk → execution → monitoring) is complete and ahead of most retail bots.
- Recognizes evolutionary strategy pool, vector memory, walk-forward + Monte Carlo, and layered risk management as strong points.

**Identified gaps / upgrade axes (Claude):**
- AI / ML depth:
  - Current system is rule-based + evolutionary optimization rather than true learning.
  - Suggested additions:
    - Predictive models (ML/DL) for signals (e.g. gradient boosting, light ML layer).
    - Online / incremental learning (e.g. River) or RL-style agents over time.
- Regime detection sophistication:
  - Current regime detection is heuristic/threshold-based.
  - Consider:
    - Hidden Markov Models for regime switching.
    - Unsupervised clustering (GMM, k-means) over return/volatility features.
- Macro news integration:
  - Macro/news features are currently optional; for XAUUSD they should be treated as critical.
  - Suggested:
    - Real-time news/calendar pipeline (e.g. Forex Factory, economic calendar APIs).
    - Sentiment/scoring models (FinBERT/GPT-based) for news impact.
    - Automatic "news blackout" windows for high-impact events.
- Live performance feedback loop:
  - Make live trade performance an explicit input into strategy evolution and selection, not just backtests.
  - Example: boost fitness for strategies with strong live Sharpe vs backtest, penalize those degrading.
- Adversarial / stress testing:
  - Beyond Monte Carlo, simulate:
    - flash crashes,
    - liquidity gaps,
    - spread spikes around news.

**Priority upgrade suggestions (Claude):**
- Add ML signal layer:
  - A lightweight ML model (e.g. LightGBM/XGBoost) as a scoring/filter over rule-based signals.
  - Optional online learner module for incremental adaptation.
- Real-time news pipeline:
  - Integrate calendar + sentiment features into the feature pipeline.
  - Enforce auto blackout/lockout rules around high-impact news.
- Agentic decision layer:
  - LLM-based meta-controller that reads research memory + live performance + market context to decide:
    - when to halt trading (risk-off),
    - which strategies to prioritize under current regime,
    - when to trigger deeper research cycles.
- Stronger live feedback into research:
  - Feed `closed_trades_state` / live MT5 history into the research loop as an explicit signal when evolving/promoting strategies.

**Autonomy / capability framing (Claude):**
- Scores (approximate):
  - Architecture: 8/10
  - Risk management: 8/10
  - AI/ML depth: 4/10
  - Adaptability: 5/10
  - News/macro awareness: 3/10
  - Autonomy: 6/10
- Overall: **autonomous execution system yang kuat**, belum penuh sebagai "autonomous intelligence" system.

---

## 11. External review – Kimi assessment snapshot (2026-03-12)

**Summary:**
- Confirms the system as a strong **autonomous trading system** with:
  - Modular architecture (data → research → strategies → backtests → risk → execution).
  - Evolutionary research loop (generation + evolution + robustness checks).
  - Vector-backed research memory (Chroma).
  - Multi-layer risk management (per-trade, portfolio DD, daily caps, position limits).
  - Robust orchestration with APScheduler.

**Identified gaps / upgrade axes (Kimi):**
- ML / AI core:
  - Current system is evolutionary rule-based, not ML-driven.
  - Suggested modules:
    - `ml_models/price_predictor.py` – LSTM/Transformer-style forecasting.
    - `ml_models/rl_agent.py` – RL agent (e.g. PPO/SAC) for decision-making / sizing.
    - `ml_models/anomaly_detector.py` – autoencoder or similar for regime/anomaly detection.
    - `ml_models/sentiment_analyzer.py` – NLP for news/social sentiment.
- Explainability & model monitoring:
  - Extend explainability with:
    - SHAP-style feature importance for ML models.
    - Attention visualization if using Transformers.
    - Counterfactual reasoning ("what would have needed to change for this trade to win?").
    - Model drift detection alerts when performance degrades statistically.
- Meta-learning & adaptation:
  - Add meta-learner components:
    - `meta_learner.py` – learn when to switch strategy pools.
    - `online_learning.py` – incremental model updates.
    - `transfer_learning.py` – reuse knowledge across symbols/markets.
- Advanced risk management analytics:
  - Add VaR / CVaR / tail risk analysis.
  - Correlation breakdown detection.
  - Liquidity risk modeling / slippage and market impact modeling.
- Robustness & fault tolerance:
  - Additional infrastructure-level modules:
    - `circuit_breaker.py` – halt trading on abnormal error rates or conditions.
    - `fallback_strategies.py` – simple baseline strategies when AI layer fails.
    - `data_quality_checks.py` – validate OHLCV (outliers, missing data, gaps).
    - `mt5_connection_pool.py` – handle disconnects/reconnects gracefully.

**Priority upgrade suggestions (Kimi):**
- Priority 1 (production-critical):
  - Data quality pipeline before models/decisions.
  - Circuit breakers for anomalies.
  - Model monitoring + drift detection.
- Priority 2 (true AI depth):
  - RL agents and predictive models layered on top of existing rule/evolution framework.
  - Ensemble of RL + ML + rule-based signals with some voting/weighting.
  - Meta-learning for when/how fast to adapt.
- Priority 3 (optimization):
  - Advanced risk metrics (VaR/CVaR, tail risk).
  - Cross-asset correlation and portfolio risk.
  - Richer transaction cost modeling.

**Benchmarking framing (Kimi):**
- Relative to:
  - Hedge fund quant stack.
  - Typical retail auto-trading bots.
- Current system scores high on architecture, research pipeline, and risk; lower on ML/AI core, explainability for ML models, and robustness relative to institutional systems.

---

This file is a parking lot for future improvements. None of these are required for the
current system to function; they are "potensi" upgrades we can revisit when you have
time/energy or when the current setup has run for a while and we want to push it further.
