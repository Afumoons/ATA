# DEV_NOTES - UI Roadmap Background Workstream

## Objective
Implement and advance `docs/ui-roadmap-tasklist.md` until the tasklist is fully completed.

## Delivery Contract
- Progress updates should be reported back to Afu in the main chat.
- Commit every clean completed change set without waiting for reminders.
- Keep UI commits isolated from trading/runtime artifacts.
- If every roadmap item is complete, stop/remove the cron/background loop without asking.

## Editable Scope
- `autonomous_trading_ai/ui-front/**`
- `autonomous_trading_ai/ui_api/**`
- `autonomous_trading_ai/docs/**`
- `autonomous_trading_ai/DEV_NOTES.md`
- `autonomous_trading_ai/tmp/ui-roadmap-bg/**`

## Do Not Touch In This Workstream
- trading/runtime logic outside UI/API support unless directly required by roadmap item
- live trading execution behavior
- `strategies/pool_state.json` and backup artifacts
- unrelated repo areas

## Current Status
- U1A complete and committed
- U1B complete and committed
- U2 Drift Page committed as `fb9fd25`
- UI roadmap tasklist documented in `docs/ui-roadmap-tasklist.md`
- U2B sort presets added on Drift page and committed as `937e9ef`
- U2B recent PnL sparkline added on Drift page in current workstream
- U2B regime mismatch indicator added on Drift page in current workstream

## Milestone Order
1. Commit roadmap tasklist doc cleanly
2. Advance U2B drift depth improvements
3. Advance U3 Promotion / Demotion Explainability
4. Advance U3B Review Queue
5. Continue through remaining roadmap items in priority order

## Operating Loop
For each autonomous run:
1. Read `docs/ui-roadmap-tasklist.md`, this file, and files under `tmp/ui-roadmap-bg/`
2. Pick the highest-value next unchecked item
3. Implement only a clean, bounded slice
4. Verify the slice
5. Update notes/checkpoints
6. Commit if the slice is clean
7. Report progress to Afu
8. If tasklist fully complete, note completion and stop/remove the cron/background loop

## Rules For Commits
- Commit after every clean finished slice
- Keep UI/API/docs commits separated when practical
- Never include runtime/state artifacts like `strategies/pool_state.json`

## Working Notes
- Drift page shipped in commit `fb9fd25`
- Drift filters and severity are already present, next U2B depth slices are anomaly grouping, repeated decay counting, and manual review queue
- User explicitly wants progress reports, not approval questions
