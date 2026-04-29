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
- U2B repeated decay counter, unresolved anomaly grouping, and manual review queue added on Drift page in current workstream
- U3A explainability surfaces added on Strategy detail in current workstream
- U3B review queue page added in current workstream
- U1C research filters added on Research page in current workstream
- U4A richer open trade drilldown added on Execution page in current workstream
- U5A strategy identity / DNA card added on Strategy detail in current workstream
- U5B compare-two-strategies view added on Pool page in current workstream
- U5B compare-family view added on Pool page in current workstream
- U5B nearest-neighbor / clone similarity panel added on Strategy detail in current workstream
- U5B duplicate-risk visibility from semantic similarity / memory veto context added on Strategy detail in current workstream

## Milestone Order
1. Commit roadmap tasklist doc cleanly
2. Advance U3 Promotion / Demotion Explainability
3. Advance U1C Research diagnostics improvements
4. Continue through remaining roadmap items in priority order

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
- U2B drift depth is now complete
- U3A explainability on Strategy detail is now complete
- U3B review queue is now complete
- U1C research filters are now complete for symbol, timeframe, and family/sort controls
- U1C research diagnostics is now complete, including skip-reason drilldown with counts and examples per family
- U1C funnel visualization, previous-run comparison, and fragile-family highlighting are now complete
- U4A richer open trade drilldown is now complete, including per-symbol posture rollups, protection coverage, hold-age context, and per-position review flags
- U4A per-symbol execution posture cards are now complete, adding operator-readable symbol cards for protection gaps, stale updates, trade balance, and log/live-stat alignment
- U4A recent fills / exits summary cards are now complete, combining trades.log fill traces with trade-context journal exits on the Execution page
- U4A no-trade diagnosis breakdown by cause is now complete, adding a backend-shaped cause matrix plus operator-facing breakdown cards/table on the Execution page
- U4B unmatched-closed-deal resolution dashboard is now complete, adding recovery-lane summaries, symbol/reason clustering, and enriched unresolved-deal evidence on the Execution page
- U4B pairing confidence explanation is now complete, including confidence buckets, evidence-signal explanations, and per-row confidence detail on the Execution page
- U4B recent trade-context registration failures panel is now complete, adding system-log exception parsing plus operator-facing cause/strategy tables and traceback hints on the Execution page
- U4B stale execution artifact warnings are now complete, adding core artifact freshness diagnostics and operator-readable impact warnings on the Execution page
- U5A strategy identity layer is now complete, including DNA summary, true-edge badges, family/regime mismatch warnings, session dependence warnings, and fragility markers on Strategy detail
- U5B compare-two-strategies view is now complete, including head-to-head posture, DNA, regime/session contrast, and warning comparison on Pool
- U5B nearest-neighbor / clone similarity panel is now complete, adding semantic-neighbor ranking, same-slot clone pressure, structural clone detection, and novelty cues on Strategy detail
- U5B duplicate-risk visibility from semantic similarity / memory veto context is now complete, adding latest research-family semantic-duplicate and memory-veto pressure alongside the Strategy detail similarity panel
- Next highest-value slice is U6A governance policy summary page
- User explicitly wants progress reports, not approval questions
