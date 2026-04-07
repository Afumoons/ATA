# 19 - Live vs Backtest Gap Audit and Patch (2026-04-07)

Date: 2026-04-07
Owner: Clio Nova
Status: patch batch landed, governance/status hardening landed, runtime validation pending

## Objective

Reduce the current live-vs-backtest gap by addressing the highest-confidence issues observed from current evidence:

1. closed-deal attribution leakage (`ticket_map_miss` / unmatched buckets)
2. repeated correlated live entries on the same symbol/direction cluster
3. status/governance drift causing brittle pool distribution and status-consumer failures
4. weak operator visibility into why live losers can diverge from backtest winners

---

## Evidence summary

### 1) Attribution leakage is real

Observed in `execution/unmatched_closed_deals.json`:
- multiple `ticket_map_miss` records
- repeated unmatched `XAUUSDc` closes
- manual unmatched bucket accumulation such as `manual_unmatched_XAUUSDM`
- large unmatched losses were present, including examples like:
  - `-4151.10`
  - `-322.53`

Implication:
- some realized live PnL was not being attached cleanly to the originating strategy
- therefore live strategy rankings were partially distorted

### 2) Correlated repeated entries are real

Observed in `execution/trades.log`:
- repeated same-direction executions for the same symbol
- same strategy families and same symbol often fired in clusters
- examples were especially visible in BTC short bursts and XAU repeated same-side firing

Implication:
- backtest may still look diversified enough, while live execution can behave like stacked correlated bets
- that widens drawdown and makes live expectancy worse than isolated-candidate backtest expectancy

### 3) Some live losers are genuine, not only bookkeeping noise

Observed in `execution/strategy_live_stats.json`:
- several BTC strategies had materially negative realized stats
- this confirms the problem is not purely attribution; some promoted strategies remain tail-fragile live

Implication:
- acceptance logic still needs future live-aware hardening beyond the patch in this batch

---

## Patch batch

### A) Attribution hardening in `execution/live_monitor.py`

Landed:
- canonical symbol is now captured on unmatched closed deals
- heuristic fallback attempts to recover a strategy from the persisted ticket map when direct ticket lookup misses
- unmatched audit rows now preserve candidate heuristic matches for operator review

Intent:
- reduce silent leakage into manual unmatched buckets
- preserve better evidence when attribution still fails

Important note:
- this is a conservative recovery patch, not a claim of perfect attribution
- true zero-miss attribution still depends on stable MT5 ticket lineage and mapping persistence

### B) Correlation gate in `execution/signals.py`

Landed:
- per-direction live signal cap
- per-family per-direction live signal cap
- recent-overlap guard based on recent `trades.log` history
- active-position-aware exposure guard so already-open stack is counted before allowing more entries

Intent:
- stop the execution layer from firing too many same-direction / same-family correlated trades on the same symbol
- reduce clustered live exposure without globally disabling the strategy pool

Current conservative caps:
- max 2 signals per direction per batch
- max 2 signals per family+direction per batch
- block when recent overlap for same symbol+direction already hit the lookback threshold

This is intentionally conservative and should be tuned from live evidence later.

### C) Governance/status hardening in `scheduler/main.py` and `strategies/pool.py`

Landed:
- unknown or malformed statuses are normalized safely instead of leaking brittle values downstream
- research fallback tier now defaults weak/non-promoted entries to `candidate` instead of collapsing them directly into `disabled`
- status summaries now explicitly include `disabled` / `retired` without assuming only a narrower status set
- scheduler now logs post-research status distribution explicitly

Intent:
- reduce status-pipeline brittleness
- stop the research loop from over-producing `disabled` as the default sink tier
- improve operator visibility when pool distribution drifts into unhealthy shapes

---

## What this batch does **not** claim to solve

This batch does not yet solve:
- weak strategy quality itself
- Monte Carlo tail fragility
- exit-logic mismatch between backtest and live
- broker-side fill/slippage realism gaps
- family overlap that happens through different names but similar economics outside the current family labels

Those remain real next-step candidates.

---

## Expected effect

If the patch behaves as intended:
- fewer closed deals should fall into unmatched manual buckets
- live strategy PnL attribution should become more trustworthy
- repeated clustered entries should decline
- live exposure should become less stack-heavy and less correlated

This should improve the *truthfulness* of live monitoring first, and live performance second.

---

## Next recommended validation

1. run a fresh live cycle / paper-live cycle
2. inspect whether `ticket_map_miss` frequency declines
3. inspect whether same-symbol same-direction bursts decline in `trades.log`
4. compare whether live losers are now cleaner to attribute per strategy
5. only then decide whether to harden promotion / acceptance filters further

---

## Recommended next patch after validation

If this batch works, the next high-value patch should be:
- add a live-aware overlap penalty into execution selection / promotion
- penalize strategies whose live overlap profile is highly redundant even if their standalone backtest metrics look good
