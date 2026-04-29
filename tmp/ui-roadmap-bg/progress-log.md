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
