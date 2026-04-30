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
- U6A governance policy summary page added in current workstream
- U7A operator attention grouping pass added on Drift, Review, and Execution pages in current workstream
- U7A review queue dossier / hierarchy pass added in current workstream
- U7A execution hierarchy / de-genericization pass added in current workstream
- U7A drift dossier / severity-language pass added in current workstream
- U7A/U7B Overview and Manifest hierarchy / scannability pass added in current workstream
- U0 shared page-level filter primitives added in current workstream

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
- U6A governance visibility is now complete, including governance policy heuristics, pool-composition violations, family saturation/diversity indicators, and active-vs-disabled imbalance warnings on a dedicated Governance page
- U7A operator attention grouping is now complete on the key triage-heavy pages, adding visual attention lanes and stronger severity framing on Drift, Review, and Execution
- U7A review queue dossier hierarchy pass is now complete, replacing the dense full-queue-first read with operator dossiers that foreground priority, categories, metric tiles, and review rationale while keeping the raw table as a secondary ledger
- Verified the U7A review dossier slice with `python -m compileall ui_api` and a production `npm run build` in `ui-front`
- U7A execution hierarchy / de-genericization pass is now complete for the Execution page, adding incident cards for no-trade and registration failures plus reconciliation dossiers for unresolved closed deals
- Verified the U7A Execution-page hierarchy slice with a production `npm run build` in `ui-front`
- U7A Drift-page dossier / severity-language pass is now complete for the highest-priority readouts, replacing the top attention and manual-review tables with operator dossiers and a stronger severity legend while keeping the full leaderboard ledger below
- Verified the U7A Drift-page dossier / severity-language slice with a production `npm run build` in `ui-front`
- U7B empty-state/operator-meaning pass is now complete across Research, Governance, Manifest, and Pool, adding clearer operator meaning plus next-read guidance when data is absent or incomplete
- Verified the U7B empty-state/operator-meaning slice with a production `npm run build` in `ui-front`
- U7A/U7B Pool-page hierarchy and scannability pass is now complete, adding a top-level posture dossier with workflow, family, symbol, and slot concentration cards while keeping the raw ledgers below
- Verified the Pool-page hierarchy/scannability slice with a production `npm run build` in `ui-front`
- U7A/U7B Overview and Manifest hierarchy/scannability pass is now complete, adding operator briefing / deployment dossier cards and reducing generic table feel on the remaining passive pages
- Verified the Overview/Manifest hierarchy-scannability slice with a production `npm run build` in `ui-front`
- URL state sync for filters and selected rows is now complete across Research, Drift, Review, Audit, and Pool, including shareable query params plus Suspense-safe restore on App Router pages
- Next highest-value slice is continuing the remaining unchecked polish foundations, especially consistent loading/error state treatment and restrained transitions
- U0 shared page-level filter primitives are now complete, including reusable filter toolbar/select primitives across Research, Drift, Review, and Audit plus an Audit date-range control
- U0 stronger responsive behavior for dense operator tables is now complete, including a shared mobile card-stack treatment for DataTable so dense ledgers collapse into labeled operator cards on narrow screens instead of only relying on horizontal scroll
- Verified the shared filter-primitives slice with a production `npm run build` in `ui-front`
- Verified the responsive dense-table slice with a production `npm run build` in `ui-front`
- User explicitly wants progress reports, not approval questions
