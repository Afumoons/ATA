# UI v1 Backend Tasklist

Status legend:
- done
- in_progress
- pending
- blocked
- deferred

## Goal
Build the read-only operator backend API for v1 (`autonomous_trading_ai`) using FastAPI.

## Hard stop rule
When **all Phase A and Phase B tasks are `done`** and acceptance criteria pass:
1. mark the final line `STATUS: COMPLETE`
2. do not implement further changes in this stream
3. stop the run

If blocked by missing dependency or ambiguous design choice, mark the item `blocked` with a reason and stop.

## Phase A — API foundation
- [done] Create `ui_api/` package layout
- [done] Add FastAPI app entrypoint
- [done] Add `/api/health`
- [done] Add `/api/overview`
- [done] Add backend schemas/models for overview responses
- [done] Add logging/bootstrap for UI API

## Phase B — adapters and endpoints
- [done] Add live-state adapter
- [done] Add pool adapter
- [done] Add manifest/index adapter
- [done] Add execution diagnostics adapter
- [done] Add audit/log adapter
- [done] Add `/api/execution/summary`
- [done] Add `/api/pool/summary`
- [done] Add `/api/manifest`
- [done] Add `/api/strategies`
- [done] Add `/api/strategies/{name}`
- [done] Add `/api/audit/timeline`

## Phase C — verification/docs
- [pending] Add smoke tests for API imports and core endpoints
- [pending] Add minimal README/run instructions for backend UI API
- [pending] Add fixture-based parser tests if needed

## Acceptance criteria
- FastAPI app imports successfully
- `/api/health` works
- `/api/overview` works
- `/api/execution/summary` works
- `/api/pool/summary` works
- `/api/manifest` works
- tests or smoke checks for core endpoints pass
- task statuses updated honestly

STATUS: INCOMPLETE
