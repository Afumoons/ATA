# UI v1 Frontend Tasklist

Status legend:
- done
- in_progress
- pending
- blocked
- deferred

## Goal
Build the read-only operator dashboard frontend for v1 (`autonomous_trading_ai`) using React + TypeScript + Vite.

## Design source of truth
Adopt the design language from `C:\laragon\www\awesome-design-md`.
Target aesthetic: Apple-like, calm, premium, minimal, spacious, typography-first, soft depth, and low visual noise.
Avoid generic noisy trading-dashboard aesthetics.

## Hard stop rule
When **all Phase A and Phase B tasks are `done`** and acceptance criteria pass:
1. mark the final line `STATUS: COMPLETE`
2. do not implement further changes in this stream
3. stop the run

If blocked by missing dependency/tooling problem, mark the item `blocked` with a reason and stop.

## Phase A — frontend shell
- [done] Inspect `C:\laragon\www\awesome-design-md` and extract reusable design language cues
- [done] Create frontend app scaffold (recommended: `ui/`)
- [done] Add TypeScript + Vite config
- [done] Add Tailwind or lightweight styling setup
- [done] Add app layout/sidebar/header shell
- [done] Add API client helper
- [done] Add Overview page
- [done] Add Execution Diagnostics page

## Phase B — operator views
- [done] Add Pool Overview page
- [done] Add Manifest Viewer page
- [done] Add Audit Timeline page
- [done] Add reusable status badges/cards/table components
- [done] Add loading/error/empty states
- [done] Add build verification
- [done] Add README/run instructions for frontend UI

## Phase C — optional after MVP
- [pending] Add Strategy Detail page
- [pending] Add charts (only if cheap and useful)
- [pending] Add config view (read-only)

## Acceptance criteria
- frontend installs/builds successfully
- overview page renders
- execution diagnostics page renders
- pool overview page renders
- manifest viewer page renders
- audit timeline page renders
- API client points to backend UI API cleanly
- design clearly reflects `C:\laragon\www\awesome-design-md` cues and Apple-like operator-dashboard aesthetics
- task statuses updated honestly

STATUS: COMPLETE
