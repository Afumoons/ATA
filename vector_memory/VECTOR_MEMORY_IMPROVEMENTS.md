--- VECTOR_MEMORY_IMPROVEMENTS.md (原始)


+++ VECTOR_MEMORY_IMPROVEMENTS.md (修改后)
# Vector Memory Improvements - Implementation Summary

## Changes Made (2026-01)

### Problem Statement
The vector memory system was providing **marginal help** with significant limitations:
- Running on empty/sparse data, making high-stakes decisions unreliable
- Confusing semantic similarity with logical/structural similarity
- Creating conservative biases against novel strategies
- Risk of feedback loops reinforcing existing patterns
- Overly aggressive penalties/vetoes with insufficient evidence

### Solution: Conservative, Evidence-Based Memory Usage

#### 1. **Memory Veto (`_memory_is_clearly_bad`)** - HARDENED

**Before:**
- Vetoed if 70% of neighbors were "bad" (sharpe < 0.0, pf < 1.0)
- Required only 5+ bad neighbors out of 10
- No structural similarity check

**After:**
- ✅ Requires **85% bad** neighbors (was 70%)
- ✅ Requires **3+ VERY bad** neighbors (new tier: sharpe < -0.5, pf < 0.7)
- ✅ Requires **1+ structurally similar** bad neighbor (fingerprint match)
- ✅ Minimum **8 neighbors** required (was 5) - disabled with sparse data
- ✅ Stricter "bad" criteria: sharpe < -0.2 (was < 0.0), pf < 0.85 (was < 1.0)

**Impact:** Veto now fires only in extreme cases with strong structural evidence.

---

#### 2. **Dead Zone Penalty (`_memory_dead_zone_penalty`)** - WEAKENED

**Before:**
- Penalty triggered at 55% weak neighbors
- Max penalty ~0.45 (cumulative)
- No structural similarity consideration
- Weak criteria: sharpe < 0.10, pf < 1.02

**After:**
- ✅ Requires **70% weak** AND **30% very_weak** neighbors
- ✅ Max penalty capped at **0.25** (was ~0.45)
- ✅ **Structural similarity check** - reduces penalty by 60% if dissimilar
- ✅ Family penalty only if 75% same-family + 60% structurally similar weak
- ✅ Stricter "weak" criteria: sharpe < 0.0 (was < 0.10), pf < 0.95 (was < 1.02)
- ✅ Challenger families get 50% reduction (was 40%)
- ✅ Minimum **6 neighbors** required - disabled with sparse data

**Impact:** Penalties are weaker, more targeted, and require stronger evidence.

---

#### 3. **Parent Bonus (`_memory_bonus_for_parent`)** - CALIBRATED

**Before:**
- Max bonus ±0.2
- Good criteria: sharpe > 0.3, pf > 1.1, ret_pct > 0.0
- No structural similarity check
- No WF Sharpe requirement

**After:**
- ✅ Max bonus reduced to **±0.12** (was ±0.2)
- ✅ **Stricter "good" criteria**: sharpe > 0.5 (was > 0.3), pf > 1.2 (was > 1.1)
- ✅ Added **WF Sharpe > 0.4** requirement for quality signal
- ✅ **Structural similarity check** - full bonus only if 50%+ structurally similar
- ✅ 50% bonus reduction if structurally dissimilar
- ✅ Additional +0.03 boost for 3+ very good neighbors (sharpe > 0.8, pf > 1.4)
- ✅ Minimum **3 neighbors** required - disabled with sparse data

**Impact:** Bonuses are more conservative and reward only truly excellent, structurally-similar performers.

---

### Key Architectural Improvements

1. **Structural Fingerprint Integration**
   - All three functions now check `_structural_fingerprint()` before applying memory-based adjustments
   - Prevents semantic similarity from misleading decisions about logically-different strategies

2. **Sparse Data Protection**
   - All functions disabled with insufficient neighbors (6-8 minimum)
   - Prevents unreliable decisions when memory is still building up

3. **Tiered Quality Assessment**
   - Added "very_bad" and "very_good" tiers for stronger signal detection
   - Requires multiple tiers of evidence before making decisions

4. **Challenger Family Protection**
   - Reduced penalties/bonuses for challenger families to encourage exploration
   - Prevents memory bias from stifling innovation

5. **Enhanced Logging**
   - Detailed logging of veto/penalty decisions with breakdown metrics
   - Includes structural similarity ratios for debugging

---

### Expected Outcomes

✅ **Reduced false positives** - Novel strategies less likely to be incorrectly vetoed
✅ **Better signal-to-noise** - Only strong, structurally-backed signals affect scoring
✅ **More exploration** - Challenger families and novel structures get fairer evaluation
✅ **Sparser-data safety** - System gracefully degrades when memory is thin
✅ **Auditability** - Clear logs show why decisions were made

---

### Files Modified

- `/workspace/scheduler/main.py`
  - `_memory_is_clearly_bad()` - Lines 545-638
  - `_memory_dead_zone_penalty()` - Lines 703-853
  - `_memory_bonus_for_parent()` - Lines 885-1022

### Testing Recommendations

1. Monitor veto/penalty rates - should decrease significantly
2. Track acceptance rates for challenger families - should increase
3. Watch for structurally-novel strategies passing through - expected increase
4. Review logs for veto/penalty decisions - verify reasoning is sound
5. Compare research cycle throughput - may increase due to fewer rejections

---

### Rollback Plan

If issues arise, the original logic can be restored by:
1. Reverting threshold values to original settings
2. Removing structural fingerprint checks
3. Disabling minimum neighbor requirements

All changes are parameter adjustments - no architectural rewrites.