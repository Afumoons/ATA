# UI Roadmap Background Progress Log

## 2026-04-29
- Workstream initialized for autonomous UI roadmap delivery.
- Added U2B Drift sort presets on the Drift page (highest drift, negative recent avg, most live trades, newest warnings).
- Added U2B recent PnL sparkline sequence support through the drift adapter and Drift page tables.
- Updated roadmap/task notes to reflect the completed sparkline slice and next U2B targets.
- Added U2B regime mismatch indicator by deriving live observed regime from live regime buckets and surfacing alignment badges plus summary counts on the Drift page.
- Added U2B repeated decay-warning counters per strategy by folding `pool_audit_trail.json` into the drift adapter and surfacing counts in attention/leaderboard tables.
- Added U2B unresolved anomaly grouping for unmatched closes, missing live stats, and stale updates, plus a Drift manual review queue section for operator triage.
- Marked U2B complete in roadmap notes; next slice is U3A promotion/demotion explainability on Strategy detail.
- Added U3A explainability surfaces on the Pool Strategy detail view, including posture explanation, latest promotion/demotion context, and recent status transition history derived from pool/audit data.
- Verified U3A slice with Python syntax checks for ui_api and a production `npm run build` in `ui-front`.
- Marked U3A complete in roadmap/task notes; next slice is U3B review queue.
- Added dedicated `/review` queue page plus `/api/review/queue` endpoint to bucket strategies into promote watch, demote watch, inspect, and archive triage lanes.
- Review queue now surfaces almost-accepted candidates, live-drifting rows, family/regime mismatches, stale active strategies, and repeated reconciliation anomaly heuristics when present.
- Verified U3B slice with Python compile checks for `ui_api`, production `npm run build` in `ui-front`, and a direct adapter smoke test for `load_review_queue()`.
- Marked U3B complete in roadmap/task notes; next slice is U1C research diagnostics controls.
- Fixed the research summary adapter to read from `tmp/research_family_stage_summaries/`, matching where family-stage artifacts are actually emitted.
- Added U1C research controls on `/research`: symbol switcher, timeframe switcher, family filter, and sort presets for accepted, conversion, generation volume, rejection pressure, and family name.
- The Research page now shows filtered family counts, conversion rate, rejection totals, and top visible family so operator filtering changes are immediately legible.
- Verified the U1C filter-controls slice with Python compile checks for `ui_api`, a direct adapter smoke test for BTC/XAG/XAU summaries, and production `npm run build` in `ui-front`.
- Marked the first U1C control items complete in roadmap/task notes; next slice is funnel visualization plus a change-summary layer.
- Added U1C funnel visualization cards on `/research` so stage throughput is scannable as stacked progress bars instead of only key-value totals.
- Extended `load_research_summary()` with previous-snapshot comparison support by discovering the latest older artifact for the same symbol/timeframe, including the `pre_d4a_baseline` snapshots under `tmp/research_family_stage_summaries/`.
- The Research page now shows batch-to-batch deltas, a “since previous run” summary, and a fragile-family table for low-conversion/high-rejection families.
- Verified the U1C comparison slice with `python -m compileall ui_api`, a package-context smoke test for `load_research_summary('XAUUSDm', 'M15')`, and production `npm run build` in `ui-front`.
- Marked U1C funnel visualization, previous-run comparison, and fragile-family highlighting complete in roadmap/task notes; next slice is per-family skip-reason drilldown with counts and examples.
