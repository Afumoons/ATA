# Autonomous Trading AI UI Roadmap Tasklist

_Last updated: 2026-04-29_

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
- [ ] Add shared page-level filter primitives (symbol, timeframe, family, date range)
- [ ] Add URL state sync for filters and selected rows
- [ ] Add empty/loading/error state consistency pass across all pages
- [ ] Add stronger responsive behavior for dense operator tables

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
- [ ] Add symbol switcher (XAU/BTC/XAG/etc.) to Research page
- [ ] Add timeframe switcher to Research page
- [ ] Add family filter and sorting controls
- [ ] Add funnel visualization cards or stacked bars
- [ ] Add batch-to-batch comparison view
- [ ] Add “what changed since previous run” summary
- [ ] Add skip-reason drilldown with counts + examples per family
- [ ] Highlight fragile families with low generated-to-accepted conversion

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
- [ ] Add “why this strategy is active/candidate/exploratory/disabled” panel
- [ ] Surface latest promotion/demotion reason from pool/audit context
- [ ] Add operator-readable decision explanation strings
- [ ] Add recent status transition history on Strategy detail page

### U3B — Review queue
- [ ] Add dedicated review queue page
- [ ] Queue strategies that are:
  - [ ] almost accepted
  - [ ] live-drifting
  - [ ] family/regime mismatched
  - [ ] stale but still active
  - [ ] showing repeated reconciliation anomalies
- [ ] Add triage buckets: promote watch, demote watch, inspect, archive

---

## Phase U4 — Execution and Reconciliation Cockpit

### U4A — Execution depth
- [ ] Add richer open trade drilldown
- [ ] Add per-symbol execution posture card
- [ ] Add recent fills / exits summary cards
- [ ] Add no-trade diagnosis breakdown by cause

### U4B — Reconciliation tools
- [ ] Add unmatched-closed-deal resolution dashboard
- [ ] Add pairing confidence explanation
- [ ] Add recent trade-context registration failures panel
- [ ] Add stale execution artifact warnings

---

## Phase U5 — Strategy Identity and DNA Layer

### U5A — Identity view
- [ ] Add Strategy DNA card
- [ ] Add “true edge identity” badges
- [ ] Add family/regime mismatch warnings
- [ ] Add session dependence warnings
- [ ] Add fragility markers (exit-rule dependency, ultra-short holding behavior, etc.)

### U5B — Comparison tools
- [ ] Add compare-two-strategies view
- [ ] Add compare-family view
- [ ] Add nearest-neighbor / clone similarity panel
- [ ] Add duplicate-risk visibility from semantic similarity / memory veto context

---

## Phase U6 — Governance and Operator Control Layer

### U6A — Governance visibility
- [ ] Add governance policy summary page
- [ ] Add current pool composition rules and violations
- [ ] Add family saturation and diversity indicators
- [ ] Add active-vs-disabled inventory imbalance warnings

### U6B — Safe operator actions (only if wanted later)
- [ ] Add read-only simulation of promote/demote effects
- [ ] Add “proposed action” cards before enabling any write action
- [ ] Keep execution-changing actions gated behind explicit confirmation and audit logging

---

## Phase U7 — Visual and UX Polish

### U7A — Information design
- [ ] Improve hierarchy for dense data views
- [ ] Add better visual grouping of operator attention items
- [ ] Reduce generic table feel on key pages
- [ ] Add more expressive badges / severity color language

### U7B — Frontend design pass
- [ ] Apply cohesive design system direction across pages
- [ ] Improve empty states so they explain operator meaning, not just absence
- [ ] Improve data-rich layout spacing and scannability
- [ ] Add subtle transitions and emphasis where it helps understanding

---

## Suggested Execution Order

### Current practical order
1. [x] Finish U2B Drift depth improvements
2. [ ] Build U3A Promotion / Demotion Explainability
3. [ ] Build U3B Review Queue
4. [ ] Expand U1C Research diagnostics controls
5. [ ] Expand U4 Execution / Reconciliation cockpit
6. [ ] Add U5 Strategy DNA comparison tools
7. [ ] Finish U7 design polish pass

---

## High-Value Milestones

### Milestone M1 — Research cockpit
- [x] U1A complete
- [x] U1B complete
- [ ] U1C filter/comparison improvements complete

### Milestone M2 — Drift cockpit
- [x] U2A committed
- [x] U2B complete

### Milestone M3 — Governance cockpit
- [ ] U3A complete
- [ ] U3B complete

### Milestone M4 — Full decision cockpit
- [ ] U4 complete
- [ ] U5 complete
- [ ] U7 polish complete

---

## Notes
- Keep UI commits isolated from trading/runtime artifact changes.
- Prefer read-only visibility first, then controlled explainability, then optional operator actions.
- The highest-value UI principle remains: show not only what happened, but why the machine took this shape.
