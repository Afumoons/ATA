# Autonomous Trading AI UI Roadmap Tasklist

_Last updated: 2026-04-30_

## Goal
Transform the current Operator UI from a read-only monitoring surface into a decision cockpit for research, execution, governance, and operator review.

---

## Phase U0 — Foundation and Structure

### Done
- [x] Establish Next.js operator UI shell
- [x] Establish Overview / Execution / Pool / Manifest / Audit pages
- [x] Add reusable dashboard primitives (stat cards, tables, timeline, notices)
- [x] Add UI API service layer and typed payload contracts

### Still useful
- [x] Add shared page-level filter primitives (symbol, timeframe, family, date range)
- [x] Add URL state sync for filters and selected rows
- [x] Add empty/loading/error state consistency pass across all pages
- [x] Add stronger responsive behavior for dense operator tables

---

## Phase U1 — Research and Strategy Visibility

### U1A — Existing page upgrades
#### Done
- [x] Add Overview attention queue
- [x] Add Pool family concentration panel
- [x] Add Pool symbol concentration panel
- [x] Enrich Strategy explorer with family / motif context
- [x] Add Strategy detail best/worst regime
- [x] Add Strategy detail best/worst session
- [x] Add Strategy detail routing confidence / specialist score
- [x] Add Strategy detail live-vs-research delta
- [x] Add Strategy detail regime map
- [x] Add Strategy detail session map
- [x] Add Strategy detail research return context

### U1B — Research Funnel page
#### Done
- [x] Add `/research` page
- [x] Add research summary API endpoint
- [x] Surface funnel totals
- [x] Surface family funnel table
- [x] Surface rejection reasons
- [x] Surface rejection samples

### U1C — Research diagnostics improvements
- [x] Add symbol switcher (XAU/BTC/XAG/etc.) to Research page
- [x] Add timeframe switcher to Research page
- [x] Add family filter and sorting controls
- [x] Add funnel visualization cards or stacked bars
- [x] Add batch-to-batch comparison view
- [x] Add “what changed since previous run” summary
- [x] Add skip-reason drilldown with counts + examples per family
- [x] Highlight fragile families with low generated-to-accepted conversion

---

## Phase U2 — Drift and Runtime Reality Check

### U2A — Drift page
#### In progress / built locally
- [x] Add `/drift` page
- [x] Add drift summary API endpoint
- [x] Show attention rows for live-vs-research mismatch
- [x] Show drift leaderboard
- [x] Add navigation entry for Drift page

### U2B — Drift depth improvements
- [x] Commit U2A cleanly as isolated UI commit
- [x] Add symbol / family / status filters to Drift page
- [x] Add severity badges (healthy / watch / drifting / broken)
- [x] Add sparkline for recent PnL sequence
- [x] Add regime mismatch indicator (research best regime vs live observed regime)
- [x] Add repeated decay-warning counter per strategy
- [x] Add unresolved anomaly grouping (unmatched close, missing stats, stale updates)
- [x] Add “needs manual review” queue section
- [x] Add sort presets (highest drift, negative recent avg, most live trades, newest warnings)

---

## Phase U3 — Promotion / Demotion Explainability

### U3A — Decision reason surfaces
- [x] Add “why this strategy is active/candidate/exploratory/disabled” panel
- [x] Surface latest promotion/demotion reason from pool/audit context
- [x] Add operator-readable decision explanation strings
- [x] Add recent status transition history on Strategy detail page

### U3B — Review queue
- [x] Add dedicated review queue page
- [x] Queue strategies that are:
  - [x] almost accepted
  - [x] live-drifting
  - [x] family/regime mismatched
  - [x] stale but still active
  - [x] showing repeated reconciliation anomalies
- [x] Add triage buckets: promote watch, demote watch, inspect, archive

---

## Phase U4 — Execution and Reconciliation Cockpit

### U4A — Execution depth
- [x] Add richer open trade drilldown
- [x] Add per-symbol execution posture card
- [x] Add recent fills / exits summary cards
- [x] Add no-trade diagnosis breakdown by cause

### U4B — Reconciliation tools
- [x] Add unmatched-closed-deal resolution dashboard
- [x] Add pairing confidence explanation
- [x] Add recent trade-context registration failures panel
- [x] Add stale execution artifact warnings

---

## Phase U5 — Strategy Identity and DNA Layer

### U5A — Identity view
- [x] Add Strategy DNA card
- [x] Add “true edge identity” badges
- [x] Add family/regime mismatch warnings
- [x] Add session dependence warnings
- [x] Add fragility markers (exit-rule dependency, ultra-short holding behavior, etc.)

### U5B — Comparison tools
- [x] Add compare-two-strategies view
- [x] Add compare-family view
- [x] Add nearest-neighbor / clone similarity panel
- [x] Add duplicate-risk visibility from semantic similarity / memory veto context

---

## Phase U6 — Governance and Operator Control Layer

### U6A — Governance visibility
- [x] Add governance policy summary page
- [x] Add current pool composition rules and violations
- [x] Add family saturation and diversity indicators
- [x] Add active-vs-disabled inventory imbalance warnings

### U6B — Safe operator actions (only if wanted later)
- [ ] Add read-only simulation of promote/demote effects
- [ ] Add “proposed action” cards before enabling any write action
- [ ] Keep execution-changing actions gated behind explicit confirmation and audit logging

---

## Phase U7 — Visual and UX Polish

### U7A — Information design
- [x] Improve hierarchy for dense data views
- [x] Add better visual grouping of operator attention items
- [x] Reduce generic table feel on key pages
- [x] Add more expressive badges / severity color language
- Note: Review, Execution, Drift, Pool, Overview, Manifest, Research, and Audit now have dedicated hierarchy/dossier passes, and the shared responsive/filter foundations are tightened enough to treat the information-design pass as complete.

### U7B — Frontend design pass
- [x] Apply cohesive design system direction across pages
- [x] Improve empty states so they explain operator meaning, not just absence
- [x] Improve data-rich layout spacing and scannability
- [x] Add subtle transitions and emphasis where it helps understanding

---

## Suggested Execution Order

### Current practical order
1. [x] Finish U2B Drift depth improvements
2. [x] Build U3A Promotion / Demotion Explainability
3. [x] Build U3B Review Queue
4. [x] Expand U1C Research diagnostics controls
5. [x] Add U1C funnel visualization and change summary
6. [x] Expand U4 Execution / Reconciliation cockpit
7. [x] Add remaining U5B duplicate-risk visibility from semantic similarity / memory veto context
8. [x] Build U6A governance visibility surfaces
9. [x] Finish U7 design polish pass

---

## High-Value Milestones

### Milestone M1 — Research cockpit
- [x] U1A complete
- [x] U1B complete
- [x] U1C filter/comparison improvements complete

### Milestone M2 — Drift cockpit
- [x] U2A committed
- [x] U2B complete

### Milestone M3 — Governance cockpit
- [x] U3A complete
- [x] U3B complete

### Milestone M4 — Full decision cockpit
- [x] U4 complete
- [x] U5 complete
- [x] U7 polish complete

---

## Notes
- Keep UI commits isolated from trading/runtime artifact changes.
- Prefer read-only visibility first, then controlled explainability, then optional operator actions.
- The highest-value UI principle remains: show not only what happened, but why the machine took this shape.
