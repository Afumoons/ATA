# UI Frontend Tasklist — Phase 1 to Phase 3

Structured improvement plan for the active operator UI in `ui-front/`.

Goal:
- turn the UI from "it renders" into a genuinely useful operator surface
- improve observability first, then diagnosis depth, then presentation polish
- keep the UI read-only and operator-focused

---

## Operating Principles

- Prioritize operator clarity over visual flair.
- Prefer explicit state over hidden assumptions.
- Make failure modes legible.
- Keep the UI fast, calm, and information-dense.
- Do not add live execution controls unless explicitly approved.

---

# Phase 1 — Operator Reliability

Primary outcome:
The UI should feel dependable during real use, especially when the backend is down, data is stale, or artifacts are missing.

## 1. Loading / Empty / Error State System

### 1.1 Shared query-state primitives
- [ ] Create reusable UI primitives for:
  - [ ] loading state
  - [ ] empty state
  - [ ] error state
  - [ ] stale data state
- [ ] Standardize copy style across pages so errors feel consistent and operator-oriented.
- [ ] Ensure all routes use the same state patterns.

### 1.2 Route-level resilience
- [ ] Overview page: handle missing overview payload cleanly.
- [ ] Execution page: handle missing execution summary cleanly.
- [ ] Pool page: handle empty pool / missing pool artifact.
- [ ] Manifest page: handle empty manifest / missing manifest artifact.
- [ ] Audit page: handle empty audit timeline / missing audit sources.

### 1.3 Better failure messaging
- [ ] Distinguish between:
  - [ ] backend unreachable
  - [ ] HTTP failure response
  - [ ] malformed payload
  - [ ] empty-but-valid response
- [ ] Show actionable operator hints where appropriate.
- [ ] Avoid generic “something went wrong” wording when the state is identifiable.

## 2. Refresh & Staleness Awareness

### 2.1 Manual refresh
- [ ] Add a visible refresh action on key pages.
- [ ] Support re-fetch without full page reload.

### 2.2 Auto refresh
- [ ] Add lightweight polling for high-value surfaces.
- [ ] Start with overview + execution pages.
- [ ] Tune refresh interval to stay low-noise and operationally useful.

### 2.3 Timestamps and freshness
- [ ] Show `last updated` / `generated_at` where available.
- [ ] Show stale indicators when data is older than expected.
- [ ] Surface freshness at both page level and critical-card level when useful.

## 3. Severity & Health Signaling

### 3.1 Severity model
- [ ] Define UI severity levels:
  - [ ] normal
  - [ ] info
  - [ ] warning
  - [ ] critical
- [ ] Standardize badge / card / text treatment per severity.

### 3.2 High-signal health indicators
- [ ] Locked-for-day indicator.
- [ ] Backend connectivity indicator.
- [ ] Unmatched closed deals indicator.
- [ ] Open trades visibility indicator.
- [ ] Manifest / pool artifact presence indicator.

### 3.3 Status summary strip
- [ ] Add a compact top-level status strip on overview.
- [ ] Make it answer quickly:
  - [ ] is backend reachable?
  - [ ] is today locked?
  - [ ] are runtime artifacts present?
  - [ ] are there audit anomalies worth attention?

## 4. UX Reliability Cleanup

### 4.1 Copy cleanup
- [ ] Review all labels for operator clarity.
- [ ] Replace vague wording with actionable wording.
- [ ] Ensure terminology is consistent across pages.

### 4.2 Missing-data tolerance
- [ ] Ensure cards tolerate null/undefined values gracefully.
- [ ] Avoid full-page breakage from one missing field.
- [ ] Add safe rendering for optional nested data.

### 4.3 Basic QA pass
- [ ] Verify all routes render with:
  - [ ] healthy backend
  - [ ] backend offline
  - [ ] empty artifacts
  - [ ] partial data present

---

# Phase 2 — Diagnosis & Investigation Depth

Primary outcome:
The UI should help answer “why is the system behaving this way?” without requiring immediate log spelunking.

## 5. Execution Diagnosis Improvements

### 5.1 Diagnosis summary panel
- [ ] Add a compact execution diagnosis summary.
- [ ] Include:
  - [ ] open trades count
  - [ ] locked-for-day status
  - [ ] trades today
  - [ ] unmatched closed deals count
  - [ ] top live strategies snapshot

### 5.2 No-trade context support
- [ ] Identify what current backend fields already support no-trade diagnosis.
- [ ] If needed, define backend additions for operator explanation.
- [ ] Surface likely reasons for inactivity when possible.

### 5.3 Recent event emphasis
- [ ] Promote recent high-signal audit/runtime events near the top of the execution page.
- [ ] Highlight events that imply degraded live quality or operator attention need.

## 6. Strategy Drill-Down Experience

### 6.1 Strategy list usability
- [ ] Improve scanability of strategy rows/cards.
- [ ] Show the most decision-relevant metadata first.

### 6.2 Strategy detail view
- [ ] Create or improve per-strategy detail display.
- [ ] Include:
  - [ ] status
  - [ ] score
  - [ ] symbol/timeframe
  - [ ] family
  - [ ] motif
  - [ ] manifest presence
  - [ ] pool presence
  - [ ] live stats summary
  - [ ] key rules summary

### 6.3 Relationship visibility
- [ ] Make it clearer how manifest, pool, and live stats relate for a given strategy.
- [ ] Reduce ambiguity around “exists in one layer but not another”.

## 7. Audit Timeline Usability

### 7.1 Timeline scanning improvements
- [ ] Improve visual hierarchy of audit events.
- [ ] Make timestamp, source, and summary easy to scan.

### 7.2 Filtering and slicing
- [ ] Add filters for:
  - [ ] source
  - [ ] strategy name (if present)
  - [ ] symbol (if present)
- [ ] Add quick filter presets for operator workflows.

### 7.3 Event expansion
- [ ] Support compact vs expanded event rendering.
- [ ] Show raw payload only when the operator wants deeper detail.

## 8. Data Shaping for UI Utility

### 8.1 Frontend-facing derived summaries
- [ ] Identify repeated client-side derivations.
- [ ] Move stable/high-value derivations into shared helpers or backend payloads.

### 8.2 Health-oriented payload design
- [ ] Consider backend payload additions for:
  - [ ] summary warnings
  - [ ] stale flags
  - [ ] artifact presence flags
  - [ ] diagnosis hints
- [ ] Keep API read-only and observability-focused.

### 8.3 Consistency pass
- [ ] Normalize field naming across pages/helpers where possible.
- [ ] Reduce one-off rendering logic.

---

# Phase 3 — Presentation, Density, and Product Quality

Primary outcome:
The UI should feel polished, distinctive, and efficient for real operator use, without becoming noisy or overdesigned.

## 9. Visual Hierarchy & Layout Polish

### 9.1 Page structure refinement
- [ ] Revisit spacing, section grouping, and card hierarchy.
- [ ] Reduce dead space while preserving readability.
- [ ] Improve above-the-fold usefulness on key routes.

### 9.2 Card system polish
- [ ] Standardize card headers, meta rows, and dense-stat layouts.
- [ ] Improve consistency of numbers, labels, and secondary metadata.

### 9.3 Navigation polish
- [ ] Improve sidebar/top-nav clarity and active-state treatment.
- [ ] Ensure route transitions feel coherent and not visually jumpy.

## 10. Operator-Oriented Data Density

### 10.1 Dense but readable summaries
- [ ] Increase information density where it helps operators.
- [ ] Avoid decorative elements that do not improve decisions.

### 10.2 Better comparative presentation
- [ ] Improve side-by-side comparison of:
  - [ ] status counts
  - [ ] slot distributions
  - [ ] strategy quality slices
  - [ ] execution snapshots

### 10.3 Responsive behavior
- [ ] Ensure the dashboard remains usable on smaller laptop screens.
- [ ] Preserve readability before attempting full mobile optimization.

## 11. Distinctive Product Finish

### 11.1 Visual identity refinement
- [ ] Push the UI slightly beyond generic dashboard aesthetics.
- [ ] Keep the premium restrained operator feel from the design direction.

### 11.2 Motion / micro-interaction pass
- [ ] Add restrained interactions only where they improve clarity.
- [ ] Avoid flashy animation that increases noise.

### 11.3 Final consistency pass
- [ ] Align typography, spacing, color usage, and component behavior.
- [ ] Remove rough edges introduced during earlier implementation phases.

---

# Suggested Execution Order

## Milestone A
- [ ] Phase 1.1 Shared query-state primitives
- [ ] Phase 1.2 Route-level resilience
- [ ] Phase 1.3 Better failure messaging

## Milestone B
- [ ] Phase 2.1 Manual refresh
- [ ] Phase 2.2 Auto refresh
- [ ] Phase 2.3 Timestamps and freshness
- [ ] Phase 3.1 Severity model

## Milestone C
- [ ] Phase 5 Execution diagnosis improvements
- [ ] Phase 6 Strategy drill-down experience
- [ ] Phase 7 Audit timeline usability

## Milestone D
- [ ] Phase 9 Visual hierarchy & layout polish
- [ ] Phase 10 Operator-oriented data density
- [ ] Phase 11 Distinctive product finish

---

# Definition of Done

A phase should be considered complete only when:
- the targeted operator problems are materially improved
- the routes remain stable under missing/partial/offline data conditions
- the UI becomes easier to use under live operational conditions
- the implementation remains read-only and aligned with the operator dashboard intent
