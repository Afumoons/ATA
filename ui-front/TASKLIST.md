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
- [x] Create reusable UI primitives for:
  - [x] loading state
  - [x] empty state
  - [x] error state
  - [x] stale data state
- [x] Standardize copy style across pages so errors feel consistent and operator-oriented.
- [x] Ensure all routes use the same state patterns.

### 1.2 Route-level resilience
- [x] Overview page: handle missing overview payload cleanly.
- [x] Execution page: handle missing execution summary cleanly.
- [x] Pool page: handle empty pool / missing pool artifact.
- [x] Manifest page: handle empty manifest / missing manifest artifact.
- [x] Audit page: handle empty audit timeline / missing audit sources.

### 1.3 Better failure messaging
- [x] Distinguish between:
  - [x] backend unreachable
  - [x] HTTP failure response
  - [x] malformed payload
  - [x] empty-but-valid response
- [x] Show actionable operator hints where appropriate.
- [x] Avoid generic “something went wrong” wording when the state is identifiable.

## 2. Refresh & Staleness Awareness

### 2.1 Manual refresh
- [x] Add a visible refresh action on key pages.
- [x] Support re-fetch without full page reload.

### 2.2 Auto refresh
- [x] Add lightweight polling for high-value surfaces.
- [x] Start with overview + execution pages.
- [x] Tune refresh interval to stay low-noise and operationally useful.

### 2.3 Timestamps and freshness
- [x] Show `last updated` / `generated_at` where available.
- [x] Show stale indicators when data is older than expected.
- [x] Surface freshness at both page level and critical-card level when useful.

## 3. Severity & Health Signaling

### 3.1 Severity model
- [x] Define UI severity levels:
  - [x] normal
  - [x] info
  - [x] warning
  - [x] critical
- [x] Standardize badge / card / text treatment per severity.

### 3.2 High-signal health indicators
- [x] Locked-for-day indicator.
- [x] Backend connectivity indicator.
- [x] Unmatched closed deals indicator.
- [x] Open trades visibility indicator.
- [x] Manifest / pool artifact presence indicator.

### 3.3 Status summary strip
- [x] Add a compact top-level status strip on overview.
- [x] Make it answer quickly:
  - [x] is backend reachable?
  - [x] is today locked?
  - [x] are runtime artifacts present?
  - [x] are there audit anomalies worth attention?

## 4. UX Reliability Cleanup

### 4.1 Copy cleanup
- [x] Review all labels for operator clarity.
- [x] Replace vague wording with actionable wording.
- [x] Ensure terminology is consistent across pages.

### 4.2 Missing-data tolerance
- [x] Ensure cards tolerate null/undefined values gracefully.
- [x] Avoid full-page breakage from one missing field.
- [x] Add safe rendering for optional nested data.

### 4.3 Basic QA pass
- [ ] Verify all routes render with:
  - [ ] healthy backend
  - [x] backend offline
  - [x] empty artifacts
  - [x] partial data present

Status note: offline/empty/partial rendering paths are now implemented and build/lint-clean. A final live-data QA pass against a healthy backend should still be done when the backend is available.

---

# Phase 2 — Diagnosis & Investigation Depth

Primary outcome:
The UI should help answer “why is the system behaving this way?” without requiring immediate log spelunking.

## 5. Execution Diagnosis Improvements

### 5.1 Diagnosis summary panel
- [x] Add a compact execution diagnosis summary.
- [x] Include:
  - [x] open trades count
  - [x] locked-for-day status
  - [x] trades today
  - [x] unmatched closed deals count
  - [x] top live strategies snapshot

### 5.2 No-trade context support
- [x] Identify what current backend fields already support no-trade diagnosis.
- [x] If needed, define backend additions for operator explanation.
- [x] Surface likely reasons for inactivity when possible.

Status note: the current UI now derives no-trade context from existing payloads. Backend additions remain optional future enhancement, not a blocker for the current operator read-only UI.

### 5.3 Recent event emphasis
- [x] Promote recent high-signal audit/runtime events near the top of the execution page.
- [x] Highlight events that imply degraded live quality or operator attention need.

## 6. Strategy Drill-Down Experience

### 6.1 Strategy list usability
- [x] Improve scanability of strategy rows/cards.
- [x] Show the most decision-relevant metadata first.

### 6.2 Strategy detail view
- [x] Create or improve per-strategy detail display.
- [x] Include:
  - [x] status
  - [x] score
  - [x] symbol/timeframe
  - [x] family
  - [x] motif
  - [x] manifest presence
  - [x] pool presence
  - [x] live stats summary
  - [x] key rules summary

### 6.3 Relationship visibility
- [x] Make it clearer how manifest, pool, and live stats relate for a given strategy.
- [x] Reduce ambiguity around “exists in one layer but not another”.

## 7. Audit Timeline Usability

### 7.1 Timeline scanning improvements
- [x] Improve visual hierarchy of audit events.
- [x] Make timestamp, source, and summary easy to scan.

### 7.2 Filtering and slicing
- [x] Add filters for:
  - [x] source
  - [x] strategy name (if present)
  - [x] symbol (if present)
- [x] Add quick filter presets for operator workflows.

### 7.3 Event expansion
- [x] Support compact vs expanded event rendering.
- [x] Show raw payload only when the operator wants deeper detail.

## 8. Data Shaping for UI Utility

### 8.1 Frontend-facing derived summaries
- [x] Identify repeated client-side derivations.
- [x] Move stable/high-value derivations into shared helpers or backend payloads.

### 8.2 Health-oriented payload design
- [x] Consider backend payload additions for:
  - [x] summary warnings
  - [x] stale flags
  - [x] artifact presence flags
  - [x] diagnosis hints
- [x] Keep API read-only and observability-focused.

Status note: current implementation handles these as frontend derivations and keeps the API read-only. If the backend later wants to expose native flags, the UI is now structured to consume them without redesign.

### 8.3 Consistency pass
- [x] Normalize field naming across pages/helpers where possible.
- [x] Reduce one-off rendering logic.

---

# Phase 3 — Presentation, Density, and Product Quality

Primary outcome:
The UI should feel polished, distinctive, and efficient for real operator use, without becoming noisy or overdesigned.

## 9. Visual Hierarchy & Layout Polish

### 9.1 Page structure refinement
- [x] Revisit spacing, section grouping, and card hierarchy.
- [x] Reduce dead space while preserving readability.
- [x] Improve above-the-fold usefulness on key routes.

### 9.2 Card system polish
- [x] Standardize card headers, meta rows, and dense-stat layouts.
- [x] Improve consistency of numbers, labels, and secondary metadata.

### 9.3 Navigation polish
- [x] Improve sidebar/top-nav clarity and active-state treatment.
- [x] Ensure route transitions feel coherent and not visually jumpy.

## 10. Operator-Oriented Data Density

### 10.1 Dense but readable summaries
- [x] Increase information density where it helps operators.
- [x] Avoid decorative elements that do not improve decisions.

### 10.2 Better comparative presentation
- [x] Improve side-by-side comparison of:
  - [x] status counts
  - [x] slot distributions
  - [x] strategy quality slices
  - [x] execution snapshots

### 10.3 Responsive behavior
- [x] Ensure the dashboard remains usable on smaller laptop screens.
- [x] Preserve readability before attempting full mobile optimization.

## 11. Distinctive Product Finish

### 11.1 Visual identity refinement
- [x] Push the UI slightly beyond generic dashboard aesthetics.
- [x] Keep the premium restrained operator feel from the design direction.

### 11.2 Motion / micro-interaction pass
- [x] Add restrained interactions only where they improve clarity.
- [x] Avoid flashy animation that increases noise.

### 11.3 Final consistency pass
- [x] Align typography, spacing, color usage, and component behavior.
- [x] Remove rough edges introduced during earlier implementation phases.

---

# Suggested Execution Order

## Milestone A
- [x] Phase 1.1 Shared query-state primitives
- [x] Phase 1.2 Route-level resilience
- [x] Phase 1.3 Better failure messaging

## Milestone B
- [x] Phase 2.1 Manual refresh
- [x] Phase 2.2 Auto refresh
- [x] Phase 2.3 Timestamps and freshness
- [x] Phase 3.1 Severity model

## Milestone C
- [x] Phase 5 Execution diagnosis improvements
- [x] Phase 6 Strategy drill-down experience
- [x] Phase 7 Audit timeline usability

## Milestone D
- [x] Phase 9 Visual hierarchy & layout polish
- [x] Phase 10 Operator-oriented data density
- [x] Phase 11 Distinctive product finish

---

# Definition of Done

A phase should be considered complete only when:
- the targeted operator problems are materially improved
- the routes remain stable under missing/partial/offline data conditions
- the UI becomes easier to use under live operational conditions
- the implementation remains read-only and aligned with the operator dashboard intent
