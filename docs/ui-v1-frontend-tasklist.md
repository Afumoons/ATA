# UI v1 Frontend Tasklist

Status legend:
- done
- in_progress
- pending
- blocked
- deferred

## Goal
Rebuild the read-only operator dashboard frontend for v1 (`autonomous_trading_ai`) in the existing Next.js app at:
`C:\Users\afusi\.openclaw\workspace\autonomous_trading_ai\ui-front`

Treat the older React UI in `ui/` as a reference / legacy implementation, not as the active target.

## Design source of truth
Primary reference:
- `C:\laragon\www\awesome-design-md`

Design direction:
- premium
- calm
- high-clarity
- low-noise
- spacious
- typography-first
- operator-dashboard appropriate

You may choose a design direction **better than Apple-like** if it is more suitable for a serious operator dashboard, as long as it remains premium, restrained, and highly legible.

Required visual feature:
- include a **light / dark theme switch** with a coherent palette in both modes

Avoid:
- generic noisy trading-dashboard aesthetics
- cluttered neon crypto-dashboard vibes
- overuse of glassmorphism or decorative motion

## Hard stop rule
When **all Phase A and Phase B tasks are `done`** and acceptance criteria pass:
1. mark the final line `STATUS: COMPLETE`
2. do not implement further changes in this stream
3. stop the run

If blocked by missing dependency/tooling problem, mark the item `blocked` with a reason and stop.

## Phase A — foundation in `ui-front`
- [done] Inspect `C:\laragon\www\awesome-design-md` and extract reusable design cues
- [done] Audit existing Next.js structure in `ui-front`
- [done] Define frontend information architecture and route structure
- [done] Add or confirm styling/token system in `ui-front`
- [done] Add light/dark theme system and switcher
- [done] Add app shell (layout/sidebar/header)
- [done] Add API client helper for backend UI API
- [done] Add Overview page
- [done] Add Execution Diagnostics page

## Phase B — operator views
- [done] Add Pool Overview page
- [done] Add Manifest Viewer page
- [done] Add Audit Timeline page
- [done] Add reusable premium dashboard components (cards, badges, tables, section headers)
- [done] Add loading / error / empty states
- [done] Add build verification
- [done] Add README/run instructions for `ui-front`

## Phase C — optional after MVP
- [pending] Add Strategy Detail page
- [pending] Add restrained charts if clearly useful
- [pending] Add read-only config view

## Acceptance criteria
- Next.js frontend in `ui-front` installs/builds successfully
- overview page renders
- execution diagnostics page renders
- pool overview page renders
- manifest viewer page renders
- audit timeline page renders
- API client points to backend UI API cleanly
- light/dark switch works with coherent palettes
- design clearly reflects `awesome-design-md` cues and premium operator-dashboard quality
- task statuses updated honestly

STATUS: COMPLETE
