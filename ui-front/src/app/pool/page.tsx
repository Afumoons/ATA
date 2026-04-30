"use client";

import { Suspense, useEffect, useMemo } from "react";
import { PageHeader } from "@/components/app-shell";
import {
  DataTable,
  EmptyState,
  ErrorState,
  FreshnessBadge,
  InlineNotice,
  InsightCard,
  KeyValueGrid,
  LoadingState,
  QueryStateNotice,
  Section,
  StatCard,
  StatusBadge,
  ToolbarButton,
} from "@/components/dashboard";
import { useQuery } from "@/hooks/use-query";
import { useUrlState } from "@/hooks/use-url-state";
import { uiApi } from "@/lib/api";
import { compactValue, formatCurrency, formatDateTime, formatNumber, formatPercent } from "@/lib/format";
import {
  coerceRecord,
  getStrategyRelationshipState,
  pickFirstNumber,
  pickFirstString,
  toneFromMagnitude,
  toneFromSignedNumber,
} from "@/lib/ui-state";

function normalizeDetailRows(value: unknown) {
  if (!Array.isArray(value)) return [] as Array<Record<string, unknown>>;
  return value.filter((item): item is Record<string, unknown> => Boolean(item) && typeof item === "object" && !Array.isArray(item));
}

function toneFromBadgeTone(value: unknown) {
  switch (value) {
    case "success":
    case "info":
    case "warning":
    case "critical":
      return value;
    default:
      return "neutral" as const;
  }
}

const EMPTY_STRATEGY_ROWS: Awaited<ReturnType<typeof uiApi.strategies>> = [];
type StrategyDetailData = Awaited<ReturnType<typeof uiApi.strategyDetail>>;
type PoolSummaryData = Awaited<ReturnType<typeof uiApi.poolSummary>>;

function humanizeDecisionReason(value: unknown) {
  if (typeof value !== "string" || !value.trim()) return "No explicit reason recorded";
  const text = value.replace(/_/g, " ");
  return text.charAt(0).toUpperCase() + text.slice(1);
}

function toneFromStrategyStatus(status: string | null) {
  switch (status) {
    case "active":
      return "success" as const;
    case "candidate":
      return "info" as const;
    case "exploratory":
      return "warning" as const;
    case "disabled":
    case "retired":
      return "critical" as const;
    default:
      return "neutral" as const;
  }
}

function detailSummary(detail: StrategyDetailData | null | undefined) {
  const manifest = coerceRecord(detail?.manifest_entry);
  const indexEntry = coerceRecord(detail?.index_entry);
  const pool = coerceRecord(detail?.pool_record);
  const live = coerceRecord(detail?.live_stats);
  const derived = coerceRecord(detail?.derived);
  const decision = coerceRecord(derived.decision_context);
  const identity = coerceRecord(derived.strategy_identity);

  return {
    name: detail?.name ?? "Unknown",
    symbol: pickFirstString(manifest.symbol, indexEntry.symbol, pool.symbol),
    timeframe: pickFirstString(manifest.timeframe, indexEntry.timeframe, pool.timeframe),
    family: pickFirstString(manifest.family, indexEntry.family, pool.family),
    motif: pickFirstString(manifest.motif, indexEntry.motif, pool.motif),
    status: pickFirstString(decision.current_status, manifest.status, indexEntry.status, pool.status),
    tier: pickFirstString(decision.current_tier, indexEntry.tier, pool.tier, manifest.tier),
    score: pickFirstNumber(manifest.score, indexEntry.score, pool.score, pool.pool_score),
    manifestRank: pickFirstNumber(decision.manifest_rank, manifest.manifest_rank, indexEntry.last_manifest_rank),
    livePnl: pickFirstNumber(live.total_pnl, live.realized_pnl),
    liveTrades: pickFirstNumber(live.num_trades, live.total_trades),
    researchReturnPct: pickFirstNumber(derived.research_return_pct),
    researchSharpe: pickFirstNumber(derived.research_sharpe),
    liveVsResearchDelta: pickFirstNumber(derived.live_vs_research_delta),
    routingConfidence: pickFirstNumber(derived.routing_confidence),
    specialistScore: pickFirstNumber(derived.specialist_score),
    bestRegime: pickFirstString(derived.best_regime),
    bestSession: pickFirstString(derived.best_session),
    archetype: pickFirstString(identity.archetype),
    identitySummary: pickFirstString(identity.summary),
    decayWarningCount: pickFirstNumber(decision.decay_warning_count),
    warningCount: normalizeDetailRows(identity.warnings).length,
    fragilityCount: normalizeDetailRows(identity.fragility_markers).length,
    badges: normalizeDetailRows(identity.edge_badges),
    warnings: normalizeDetailRows(identity.warnings),
    fragilityMarkers: normalizeDetailRows(identity.fragility_markers),
  };
}

function compareEdgeLabel(primary: number | null | undefined, secondary: number | null | undefined, format: (value: number | null | undefined) => string) {
  if (primary == null && secondary == null) return "No data";
  if (primary == null) return `Edge ${format(secondary)} on compare`;
  if (secondary == null) return `Edge ${format(primary)} on primary`;
  if (primary === secondary) return "Even";
  return primary > secondary ? `Primary +${format(primary - secondary)}` : `Compare +${format(secondary - primary)}`;
}

function renderMapComparisonRows(left: Record<string, unknown>, right: Record<string, unknown>) {
  const keys = Array.from(new Set([...Object.keys(left), ...Object.keys(right)])).sort((a, b) => a.localeCompare(b));
  return keys.map((key) => [key, compactValue(left[key]), compactValue(right[key])]);
}

function familyRowLabel(row: Record<string, unknown> | null | undefined) {
  const record = coerceRecord(row);
  return pickFirstString(record.label, record.family) ?? "Unknown family";
}

function familyComparisonRows(data: PoolSummaryData | null | undefined) {
  const rows = Array.isArray(data?.family_comparison?.rows)
    ? data.family_comparison.rows.filter((item): item is Record<string, unknown> => Boolean(item) && typeof item === "object" && !Array.isArray(item))
    : [];
  return rows;
}

function PoolPageContent() {
  const poolUrlDefaults = useMemo(() => ({
    search: "",
    tier: "all",
    strategy: "",
    compare: "",
  }), []);
  const { state: poolUrlState, setState: setPoolUrlState } = useUrlState(poolUrlDefaults);
  const search = poolUrlState.search;
  const tierFilter = poolUrlState.tier;
  const selectedStrategy = poolUrlState.strategy;
  const compareStrategy = poolUrlState.compare;

  const poolQuery = useQuery("pool-summary", uiApi.poolSummary, { refetchIntervalMs: 60_000 });
  const strategiesQuery = useQuery("strategies-summary", uiApi.strategies, { refetchIntervalMs: 90_000 });

  const { data, error, loading, hasData, refreshing, refresh, lastSuccessAt } = poolQuery;
  const strategyRows = strategiesQuery.data ?? EMPTY_STRATEGY_ROWS;

  const filteredStrategies = useMemo(() => {
    return [...strategyRows]
      .sort((left, right) => {
        const manifestRankDelta = Number(Boolean(right.in_manifest)) - Number(Boolean(left.in_manifest));
        if (manifestRankDelta !== 0) return manifestRankDelta;
        return Number(right.score ?? -Infinity) - Number(left.score ?? -Infinity);
      })
      .filter((row) => {
        if (tierFilter !== "all" && String(row.tier ?? "unknown") !== tierFilter) return false;

        if (!search.trim()) return true;
        const haystack = [row.name, row.symbol, row.timeframe, row.status, row.family, row.motif, row.tier]
          .filter(Boolean)
          .join(" ")
          .toLowerCase();
        return haystack.includes(search.trim().toLowerCase());
      });
  }, [search, strategyRows, tierFilter]);

  const resolvedSelectedStrategy = useMemo(() => {
    if (!filteredStrategies.length) return "";
    if (selectedStrategy && filteredStrategies.some((row) => row.name === selectedStrategy)) {
      return selectedStrategy;
    }
    return filteredStrategies[0].name;
  }, [filteredStrategies, selectedStrategy]);

  const comparisonCandidates = useMemo(
    () => filteredStrategies.filter((row) => row.name !== resolvedSelectedStrategy),
    [filteredStrategies, resolvedSelectedStrategy],
  );

  const resolvedCompareStrategy = useMemo(() => {
    if (!comparisonCandidates.length) return "";
    if (compareStrategy && comparisonCandidates.some((row) => row.name === compareStrategy)) {
      return compareStrategy;
    }
    return comparisonCandidates[0]?.name ?? "";
  }, [compareStrategy, comparisonCandidates]);

  useEffect(() => {
    if (resolvedSelectedStrategy !== selectedStrategy || resolvedCompareStrategy !== compareStrategy) {
      setPoolUrlState({
        strategy: resolvedSelectedStrategy,
        compare: resolvedCompareStrategy,
      });
    }
  }, [compareStrategy, resolvedCompareStrategy, resolvedSelectedStrategy, selectedStrategy, setPoolUrlState]);

  const detailQuery = useQuery(
    `strategy-detail:${resolvedSelectedStrategy}`,
    () => uiApi.strategyDetail(resolvedSelectedStrategy),
    { enabled: Boolean(resolvedSelectedStrategy) },
  );
  const compareDetailQuery = useQuery(
    `strategy-compare:${resolvedCompareStrategy}`,
    () => uiApi.strategyDetail(resolvedCompareStrategy),
    { enabled: Boolean(resolvedCompareStrategy) },
  );

  if (loading && !hasData) {
    return <LoadingState title="Loading pool overview" description="Collecting pool inventory, slot distribution, and strategy-layer relationship data." />;
  }

  if (!data) {
    return <ErrorState error={error} resourceLabel="pool summary" />;
  }

  const selectedDetail = detailQuery.data;
  const selectedManifest = coerceRecord(selectedDetail?.manifest_entry);
  const selectedIndex = coerceRecord(selectedDetail?.index_entry);
  const selectedPool = coerceRecord(selectedDetail?.pool_record);
  const selectedLiveStats = coerceRecord(selectedDetail?.live_stats);
  const selectedDerived = coerceRecord(selectedDetail?.derived);
  const strategyIdentity = coerceRecord(selectedDerived.strategy_identity);
  const identityMetrics = coerceRecord(strategyIdentity.metrics);
  const identityBadges = normalizeDetailRows(strategyIdentity.edge_badges);
  const identityWarnings = normalizeDetailRows(strategyIdentity.warnings);
  const fragilityMarkers = normalizeDetailRows(strategyIdentity.fragility_markers);
  const decisionContext = coerceRecord(selectedDerived.decision_context);
  const similarityPanel = coerceRecord(selectedDerived.similarity_panel);
  const duplicateRiskContext = coerceRecord(selectedDerived.duplicate_risk_context);
  const similarityTarget = coerceRecord(similarityPanel.target);
  const similarityNearest = coerceRecord(similarityPanel.nearest_neighbor);
  const similarityNeighbors = normalizeDetailRows(similarityPanel.neighbors);
  const duplicateRiskReasons = normalizeDetailRows(duplicateRiskContext.reasons);
  const transitionHistory = Array.isArray(decisionContext.transition_history)
    ? decisionContext.transition_history.filter((item): item is Record<string, unknown> => Boolean(item) && typeof item === "object" && !Array.isArray(item))
    : [];
  const latestTransition = coerceRecord(decisionContext.latest_transition);
  const relationship = getStrategyRelationshipState({
    manifest_entry: selectedDetail?.manifest_entry,
    index_entry: selectedDetail?.index_entry,
    pool_record: selectedDetail?.pool_record,
    live_stats: selectedDetail?.live_stats,
  });

  const livePnl = pickFirstNumber(selectedLiveStats.total_pnl, selectedLiveStats.realized_pnl);
  const liveTrades = pickFirstNumber(selectedLiveStats.num_trades, selectedLiveStats.total_trades);
  const liveLastUpdate = pickFirstString(selectedLiveStats.last_update);
  const liveVsResearchDelta = pickFirstNumber(selectedDerived.live_vs_research_delta);
  const ruleSource = Object.keys(selectedManifest).length ? selectedManifest : selectedPool;
  const compareDetail = compareDetailQuery.data;
  const primaryComparisonSummary = detailSummary(selectedDetail);
  const secondaryComparisonSummary = detailSummary(compareDetail);
  const compareRegimeRows = renderMapComparisonRows(
    coerceRecord(selectedDerived.regime_pnl),
    coerceRecord(coerceRecord(compareDetail?.derived).regime_pnl),
  );
  const compareSessionRows = renderMapComparisonRows(
    coerceRecord(selectedDerived.session_pnl),
    coerceRecord(coerceRecord(compareDetail?.derived).session_pnl),
  );

  const tierOptions = Array.from(new Set(strategyRows.map((row) => String(row.tier ?? "unknown")))).sort();
  const familyCompareRows = familyComparisonRows(data);
  const familyCountEntries = Object.entries(data.family_counts ?? {}).sort((left, right) => Number(right[1] ?? 0) - Number(left[1] ?? 0));
  const symbolCountEntries = Object.entries(data.symbol_counts ?? {}).sort((left, right) => Number(right[1] ?? 0) - Number(left[1] ?? 0));
  const slotRows = [...data.by_slot].sort((left, right) => right.count - left.count);
  const dominantFamily = familyCountEntries[0];
  const secondFamily = familyCountEntries[1];
  const dominantSymbol = symbolCountEntries[0];
  const secondSymbol = symbolCountEntries[1];
  const dominantSlot = slotRows[0];
  const activeStatusCount = Number(data.status_counts?.active ?? 0);
  const disabledStatusCount = Number(data.status_counts?.disabled ?? 0);
  const dominantFamilyShare = data.total > 0 && dominantFamily ? Number(dominantFamily[1] ?? 0) / data.total : 0;
  const dominantSymbolShare = data.total > 0 && dominantSymbol ? Number(dominantSymbol[1] ?? 0) / data.total : 0;
  const familyCompareSummary = coerceRecord(data.family_comparison?.summary);
  const strongestResearchFamily = coerceRecord(familyCompareSummary.strongest_research_family);
  const strongestLiveFamily = coerceRecord(familyCompareSummary.strongest_live_family);
  const deepestManifestFamily = coerceRecord(familyCompareSummary.deepest_manifest_family);
  const highestWarningDensityFamily = coerceRecord(familyCompareSummary.highest_warning_density_family);
  const manualBucketCount = pickFirstNumber(familyCompareSummary.manual_bucket_count) ?? 0;
  const manualTradeCount = pickFirstNumber(familyCompareSummary.manual_total_trades) ?? 0;
  const manualRealizedPnl = pickFirstNumber(familyCompareSummary.manual_total_realized_pnl) ?? 0;
  const manualExclusionNote = pickFirstString(familyCompareSummary.manual_exclusion_note);

  return (
    <div className="dashboard-stack">
      <PageHeader
        title="Pool overview"
        subtitle="Inventory depth, slot concentration, and cross-layer strategy drill-down so operators can see whether a strategy exists in the index, pool, manifest, and live stats at the same time."
        meta={`Snapshot ${formatDateTime(data.generated_at)}`}
        action={
          <div className="page-toolbar">
            <FreshnessBadge timestamp={data.generated_at} thresholds={{ warningMs: 15 * 60_000, criticalMs: 60 * 60_000 }} />
            <ToolbarButton
              label="Refresh now"
              onClick={() => {
                void Promise.all([refresh(), strategiesQuery.refresh(), detailQuery.refresh(), compareDetailQuery.refresh()]);
              }}
              busy={refreshing || strategiesQuery.refreshing || detailQuery.refreshing || compareDetailQuery.refreshing}
              tone="info"
            />
          </div>
        }
      />

      <QueryStateNotice error={error} refreshing={refreshing} hasData={hasData} resourceLabel="pool summary" lastSuccessAt={lastSuccessAt} />

      {manualBucketCount > 0 ? (
        <InlineNotice
          tone="warning"
          title={`Manual-user buckets excluded from family attribution (${formatNumber(manualBucketCount)})`}
          description={`${manualExclusionNote || "manual_user buckets stay outside the autonomous family scoreboard."} Current manual buckets carry ${formatNumber(manualTradeCount)} trades and ${formatCurrency(manualRealizedPnl)} realized PnL without changing research-family or live-vs-research comparisons below.`}
        />
      ) : null}

      <section className="stats-grid">
        <StatCard label="Total strategies" value={formatNumber(data.total)} hint="Pool inventory count" tone="info" />
        <StatCard label="Distinct slots" value={formatNumber(data.by_slot.length)} hint="Symbol/timeframe combinations" tone="neutral" />
        <StatCard label="Top records" value={formatNumber(data.top_strategies.length)} hint="Returned by summary endpoint" tone="success" />
        <StatCard label="Status buckets" value={formatNumber(Object.keys(data.status_counts).length)} hint="Current pool status families" tone="warning" />
      </section>

      <Section title="Pool posture dossier" description="A faster read on whether the inventory is balanced across statuses, families, symbols, and slots before you dive into the raw ledgers.">
        <div className="insight-grid">
          <InsightCard
            eyebrow="Workflow mix"
            title={`${formatNumber(activeStatusCount)} active, ${formatNumber(disabledStatusCount)} disabled`}
            description="Status distribution shows whether the pool is still deployable or quietly drifting into parked inventory and candidate backlog."
            tone={disabledStatusCount > activeStatusCount ? "warning" : activeStatusCount > 0 ? "success" : "critical"}
            badges={
              <>
                <StatusBadge label={`${formatNumber(Object.keys(data.status_counts ?? {}).length)} status lanes`} tone="info" />
                <StatusBadge label={`${formatNumber(data.top_strategies.length)} surfaced leaders`} tone="neutral" />
              </>
            }
            metrics={[
              { label: "Candidate", value: formatNumber(Number(data.status_counts?.candidate ?? 0)) },
              { label: "Exploratory", value: formatNumber(Number(data.status_counts?.exploratory ?? 0)) },
              { label: "Disabled/active", value: activeStatusCount > 0 ? `${formatNumber(disabledStatusCount / activeStatusCount)}x` : "No baseline" },
              { label: "Distinct slots", value: formatNumber(data.by_slot.length) },
            ]}
            footer={<p>{disabledStatusCount > activeStatusCount ? "Parked inventory is outweighing active inventory, so pruning or promotion flow likely deserves attention." : "Active inventory still outweighs parked inventory, so the pool remains shaped more like a deployment surface than a graveyard."}</p>}
          />

          <InsightCard
            eyebrow="Family concentration"
            title={dominantFamily ? compactValue(dominantFamily[0]) : "No family mix"}
            description="The top family defines how much of the pool is really diversified versus repeated inside one research lineage."
            tone={dominantFamilyShare >= 0.45 ? "warning" : dominantFamilyShare >= 0.3 ? "info" : "success"}
            badges={dominantFamily ? <StatusBadge label={`${formatPercent(dominantFamilyShare)} of pool`} tone={dominantFamilyShare >= 0.45 ? "warning" : dominantFamilyShare >= 0.3 ? "info" : "success"} /> : null}
            metrics={[
              { label: "Top family count", value: formatNumber(Number(dominantFamily?.[1] ?? 0)) },
              { label: "Runner-up", value: secondFamily ? `${secondFamily[0]} (${formatNumber(Number(secondFamily[1] ?? 0))})` : "None" },
              { label: "Distinct families", value: formatNumber(familyCountEntries.length) },
              { label: "Family spread", value: familyCountEntries.length >= 4 ? "Broad" : familyCountEntries.length >= 2 ? "Narrow" : "Single-lineage" },
            ]}
            footer={<p>{dominantFamily ? `${dominantFamily[0]} is the biggest lineage in the current pool. Compare it against the family scoreboard below before assuming inventory breadth equals idea breadth.` : "Family concentration data is unavailable in this snapshot."}</p>}
          />

          <InsightCard
            eyebrow="Symbol concentration"
            title={dominantSymbol ? compactValue(dominantSymbol[0]) : "No symbol mix"}
            description="Symbol skew tells you where exposure and research attention are clustering, even before execution or governance pages add more context."
            tone={dominantSymbolShare >= 0.45 ? "warning" : dominantSymbolShare >= 0.3 ? "info" : "success"}
            badges={dominantSymbol ? <StatusBadge label={`${formatPercent(dominantSymbolShare)} of pool`} tone={dominantSymbolShare >= 0.45 ? "warning" : dominantSymbolShare >= 0.3 ? "info" : "success"} /> : null}
            metrics={[
              { label: "Top symbol count", value: formatNumber(Number(dominantSymbol?.[1] ?? 0)) },
              { label: "Runner-up", value: secondSymbol ? `${secondSymbol[0]} (${formatNumber(Number(secondSymbol[1] ?? 0))})` : "None" },
              { label: "Distinct symbols", value: formatNumber(symbolCountEntries.length) },
              { label: "Explorer visible", value: formatNumber(filteredStrategies.length) },
            ]}
            footer={<p>{dominantSymbol ? `${dominantSymbol[0]} is carrying the heaviest inventory load right now, so any family concentration inside that symbol compounds slot-level exposure.` : "Symbol concentration data is unavailable in this snapshot."}</p>}
          />

          <InsightCard
            eyebrow="Slot pressure"
            title={dominantSlot ? `${dominantSlot.symbol} ${dominantSlot.timeframe}` : "No slot rows"}
            description="Slot distribution makes repeated symbol and timeframe clustering obvious before you inspect single strategies one by one."
            tone={dominantSlot && dominantSlot.count >= 4 ? "warning" : dominantSlot ? "info" : "neutral"}
            badges={dominantSlot ? <StatusBadge label={`${formatNumber(dominantSlot.count)} strategies`} tone={dominantSlot.count >= 4 ? "warning" : "info"} /> : null}
            metrics={[
              { label: "Top slot", value: dominantSlot ? `${dominantSlot.symbol} / ${dominantSlot.timeframe}` : "None" },
              { label: "Second slot", value: slotRows[1] ? `${slotRows[1].symbol} / ${slotRows[1].timeframe}` : "None" },
              { label: "Top-3 slot load", value: formatNumber(slotRows.slice(0, 3).reduce((sum, slot) => sum + slot.count, 0)) },
              { label: "Distinct slots", value: formatNumber(slotRows.length) },
            ]}
            footer={<p>{dominantSlot ? `The heaviest slot is ${dominantSlot.symbol} ${dominantSlot.timeframe}. Use the explorer and compare views below to check whether that density represents genuine variation or slot-level clones.` : "Slot distribution data is unavailable in this snapshot."}</p>}
          />
        </div>
      </Section>

      <Section title="Pool status counts" description="How current pool inventory is distributed across workflow states.">
        {Object.keys(data.status_counts ?? {}).length ? (
          <KeyValueGrid data={data.status_counts} />
        ) : (
          <EmptyState title="Pool artifact looks empty" description="No status buckets were returned. The pool state may be missing or empty." />
        )}
      </Section>

      <div className="detail-grid-2">
        <Section title="Family concentration ledger" description="Raw family counts stay visible here after the operator dossier above frames the dominant lineage story.">
          <KeyValueGrid data={data.family_counts ?? {}} emptyTitle="No family mix" emptyDescription="Family concentration was not returned by the backend." />
        </Section>
        <Section title="Symbol concentration ledger" description="Raw symbol counts for the same inventory, kept as a ledger after the higher-level concentration read.">
          <KeyValueGrid data={data.symbol_counts ?? {}} emptyTitle="No symbol mix" emptyDescription="Symbol concentration was not returned by the backend." />
        </Section>
      </div>

      <Section title="Slot distribution ledger" description="Volume concentration by symbol and timeframe, kept sortable as the raw ledger below the slot-pressure dossier.">
        <DataTable
          columns={["Symbol", "Timeframe", "Count"]}
          rows={slotRows.map((slot) => [slot.symbol, slot.timeframe, formatNumber(slot.count)])}
          emptyTitle="No slot distribution"
          emptyDescription="No symbol/timeframe distribution was returned for the pool snapshot."
        />
      </Section>

      <Section title="Strategy explorer" description="Searchable strategy list with quick selection into per-strategy relationship detail.">
        <div className="filter-toolbar panel">
          <label className="filter-field">
            <span>Search</span>
            <input
              className="filter-input"
              value={search}
              onChange={(event) => setPoolUrlState({ search: event.target.value })}
              placeholder="name, symbol, family, motif"
            />
          </label>
          <label className="filter-field">
            <span>Tier</span>
            <select className="filter-input" value={tierFilter} onChange={(event) => setPoolUrlState({ tier: event.target.value })}>
              <option value="all">All tiers</option>
              {tierOptions.map((tier) => (
                <option key={tier} value={tier}>
                  {tier}
                </option>
              ))}
            </select>
          </label>
          <div className="filter-summary">
            <span className="eyebrow">Visible</span>
            <strong>{formatNumber(filteredStrategies.length)}</strong>
          </div>
        </div>

        <DataTable
          columns={["Strategy", "Symbol", "Timeframe", "Tier", "Family", "Motif", "Status", "Manifest", "Score"]}
          rows={filteredStrategies.slice(0, 32).map((strategy) => [
            <button
              key={strategy.name}
              type="button"
              className={`table-link-button${resolvedSelectedStrategy === strategy.name ? " is-active" : ""}`}
              onClick={() => setPoolUrlState({ strategy: strategy.name })}
            >
              {strategy.name}
            </button>,
            compactValue(strategy.symbol),
            compactValue(strategy.timeframe),
            compactValue(strategy.tier),
            compactValue(strategy.family),
            compactValue(strategy.motif),
            compactValue(strategy.status),
            <StatusBadge
              key={`${strategy.name}-manifest`}
              label={strategy.in_manifest ? "Present" : "Absent"}
              tone={strategy.in_manifest ? "success" : "warning"}
            />,
            formatNumber(strategy.score),
          ])}
          emptyTitle="No strategies match the current filters"
          emptyDescription="Adjust the search text or tier filter to widen the visible strategy set."
        />
      </Section>

      <Section
        title="Strategy detail"
        description="Cross-layer view showing whether the selected strategy exists in the manifest, index, pool record, and live stats at the same time."
        action={resolvedSelectedStrategy ? <StatusBadge label={resolvedSelectedStrategy} tone="info" /> : null}
      >
        <QueryStateNotice
          error={detailQuery.error}
          refreshing={detailQuery.refreshing}
          hasData={Boolean(selectedDetail)}
          resourceLabel={`strategy detail for ${resolvedSelectedStrategy}`}
          lastSuccessAt={detailQuery.lastSuccessAt}
        />

        {!resolvedSelectedStrategy ? (
          <EmptyState
            title="No strategy selected"
            description="Choose a strategy from the explorer table above to inspect its layer relationships."
            tone="info"
            eyebrow="Detail view awaiting focus"
            meaning="The explorer is populated, but the operator has not anchored the lower dossier on any single strategy yet."
            nextStep="Pick one row from the explorer to open its cross-layer status, DNA, and clone-risk context."
          />
        ) : detailQuery.loading && !selectedDetail ? (
          <LoadingState title="Loading strategy detail" description="Pulling manifest, index, pool, and live-stat context for the selected strategy." />
        ) : detailQuery.error && !selectedDetail ? (
          <ErrorState error={detailQuery.error} resourceLabel={`strategy detail for ${resolvedSelectedStrategy}`} />
        ) : !selectedDetail ? (
          <EmptyState
            title="No strategy detail returned"
            description="The selected strategy could not be resolved into any layer detail payload."
            tone="warning"
            eyebrow="Cross-layer lookup incomplete"
            meaning="This row exists in the explorer view, but the backend could not assemble its deeper manifest, pool, or live-stat dossier."
            nextStep="Try a different strategy to confirm whether this is strategy-specific drift or a broader detail endpoint gap."
          />
        ) : (
          <div className="dashboard-stack">
            <div className="badge-row">
              {relationship.relationshipBadges.map((badge) => (
                <StatusBadge key={badge.label} label={badge.label} tone={badge.tone} />
              ))}
            </div>

            <section className="stats-grid">
              <StatCard
                label="Decision posture"
                value={compactValue(decisionContext.current_status ?? pickFirstString(selectedManifest.status, selectedIndex.status, selectedPool.status))}
                hint={compactValue(decisionContext.current_tier ?? selectedIndex.tier)}
                tone={toneFromStrategyStatus(pickFirstString(decisionContext.current_status, selectedManifest.status, selectedIndex.status, selectedPool.status))}
              />
              <StatCard
                label="Latest status reason"
                value={compactValue(decisionContext.latest_reason)}
                hint={decisionContext.latest_reason_at ? `Logged ${formatDateTime(decisionContext.latest_reason_at)}` : "Heuristic snapshot context"}
                tone={toneFromStrategyStatus(pickFirstString(decisionContext.current_status, selectedManifest.status, selectedIndex.status, selectedPool.status))}
              />
              <StatCard
                label="Manifest posture"
                value={decisionContext.in_manifest ? "Live manifest" : "Not in manifest"}
                hint={decisionContext.manifest_rank ? `Rank #${compactValue(decisionContext.manifest_rank)}` : "No live rank"}
                tone={decisionContext.in_manifest ? "success" : "warning"}
              />
              <StatCard
                label="Transition events"
                value={formatNumber(transitionHistory.length)}
                hint={compactValue(decisionContext.latest_reason_source)}
                tone={transitionHistory.length ? "info" : "neutral"}
              />
            </section>

            <Section
              title="Why this strategy has this posture"
              description="Operator-readable explanation of why the strategy is currently active, candidate, exploratory, or disabled."
              action={
                <StatusBadge
                  label={compactValue(decisionContext.decision_label ?? decisionContext.current_status ?? selectedPool.status)}
                  tone={toneFromStrategyStatus(pickFirstString(decisionContext.current_status, selectedManifest.status, selectedIndex.status, selectedPool.status))}
                />
              }
            >
              <div className="dashboard-stack">
                <div className="panel">
                  <p>{compactValue(decisionContext.decision_explanation)}</p>
                </div>
                <div className="detail-grid-2">
                  <Section title="Latest promotion / demotion context" description="Most recent audit or snapshot signal that explains the current status posture.">
                    <KeyValueGrid
                      data={{
                        source: decisionContext.latest_reason_source,
                        reason: humanizeDecisionReason(decisionContext.latest_reason),
                        at: decisionContext.latest_reason_at,
                        from_status: latestTransition.from_status,
                        to_status: latestTransition.to_status,
                      }}
                      emptyTitle="No decision context"
                      emptyDescription="The backend did not return any transition or heuristic context for this strategy yet."
                    />
                  </Section>
                  <Section title="Recent status transition history" description="Explicit transition events recovered from audit data, newest first.">
                    <DataTable
                      columns={["Time", "Transition", "Event", "Reason", "Source"]}
                      rows={transitionHistory.map((item) => [
                        formatDateTime(item.recorded_at),
                        compactValue(item.summary ?? `${compactValue(item.from_status)} → ${compactValue(item.to_status)}`),
                        compactValue(item.event),
                        humanizeDecisionReason(item.reason),
                        compactValue(item.source),
                      ])}
                      emptyTitle="No transition history yet"
                      emptyDescription="The current audit trail does not include explicit promotion or demotion rows for this strategy yet, but the posture panel above still explains the current state from snapshot context."
                    />
                  </Section>
                </div>
              </div>
            </Section>

            <Section
              title="Strategy DNA"
              description="Identity layer that turns research metadata into an operator-readable edge profile, mismatch warnings, session dependence, and fragility markers."
              action={strategyIdentity.archetype ? <StatusBadge label={compactValue(strategyIdentity.archetype)} tone="info" /> : null}
            >
              <div className="dashboard-stack">
                <div className="panel">
                  <p>{compactValue(strategyIdentity.summary)}</p>
                </div>

                <section className="stats-grid">
                  <StatCard
                    label="Archetype"
                    value={compactValue(strategyIdentity.archetype)}
                    hint="True edge identity"
                    tone="info"
                  />
                  <StatCard
                    label="Session concentration"
                    value={formatPercent(pickFirstNumber(identityMetrics.strongest_session_share))}
                    hint="Share of positive session return from the top session"
                    tone={toneFromMagnitude(pickFirstNumber(identityMetrics.strongest_session_share), 0.45, 0.6)}
                  />
                  <StatCard
                    label="Regime concentration"
                    value={formatPercent(pickFirstNumber(identityMetrics.strongest_regime_share))}
                    hint="Share of positive regime return from the top regime"
                    tone={toneFromMagnitude(pickFirstNumber(identityMetrics.strongest_regime_share), 0.45, 0.6)}
                  />
                  <StatCard
                    label="Fragility markers"
                    value={formatNumber(fragilityMarkers.length)}
                    hint={compactValue(`${identityWarnings.length} mismatch / dependence warnings`)}
                    tone={fragilityMarkers.length ? "warning" : "success"}
                  />
                </section>

                <Section title="True edge identity badges" description="Concise badges describing how the strategy actually wins, not just what family named it.">
                  {identityBadges.length ? (
                    <div className="dashboard-stack">
                      <div className="badge-row">
                        {identityBadges.map((item, index) => (
                          <StatusBadge key={`${item.label ?? "identity"}-${index}`} label={compactValue(item.label)} tone={toneFromBadgeTone(item.tone)} />
                        ))}
                      </div>
                      <DataTable
                        columns={["Badge", "Detail"]}
                        rows={identityBadges.map((item, index) => [
                          <StatusBadge key={`${item.label ?? "identity-row"}-${index}`} label={compactValue(item.label)} tone={toneFromBadgeTone(item.tone)} />,
                          compactValue(item.detail),
                        ])}
                      />
                    </div>
                  ) : (
                    <EmptyState
                      title="No identity badges yet"
                      description="The backend did not produce any distilled DNA labels for this strategy."
                      tone="info"
                      eyebrow="Identity layer still raw"
                      meaning="The strategy can still be inspected, but its edge has not been distilled into concise operator labels."
                      nextStep="Use the mismatch warnings, fragility markers, and raw detail cards below until a richer research explain payload is available."
                    />
                  )}
                </Section>

                <div className="detail-grid-2">
                  <Section title="Mismatch and dependence warnings" description="Warnings when family naming, regime fit, or session dependence create operator risk.">
                    <DataTable
                      columns={["Warning", "Detail"]}
                      rows={identityWarnings.map((item, index) => [
                        <StatusBadge key={`${item.label ?? "warning"}-${index}`} label={compactValue(item.label)} tone={toneFromBadgeTone(item.tone)} />,
                        compactValue(item.detail),
                      ])}
                      emptyTitle="No mismatch warnings"
                      emptyDescription="This strategy currently has no surfaced family/regime conflict or severe session dependence warning."
                    />
                  </Section>
                  <Section title="Fragility markers" description="Execution or research traits that can make the edge brittle in live routing.">
                    <DataTable
                      columns={["Marker", "Detail"]}
                      rows={fragilityMarkers.map((item, index) => [
                        <StatusBadge key={`${item.label ?? "fragility"}-${index}`} label={compactValue(item.label)} tone={toneFromBadgeTone(item.tone)} />,
                        compactValue(item.detail),
                      ])}
                      emptyTitle="No fragility markers"
                      emptyDescription="No brittle edge markers were detected from the current research explain and live decay payloads."
                    />
                  </Section>
                </div>
              </div>
            </Section>

            <Section
              title="Nearest-neighbor / clone similarity"
              description="Semantic-neighbor panel for spotting clone pressure, same-slot overlap, and low-novelty strategies before the pool quietly over-concentrates around one idea."
              action={similarityPanel.duplicate_risk ? <StatusBadge label={`Duplicate risk: ${compactValue(similarityPanel.duplicate_risk)}`} tone={toneFromBadgeTone(similarityPanel.tone)} /> : null}
            >
              {!similarityNeighbors.length && !duplicateRiskReasons.length && !Object.keys(duplicateRiskContext).length ? (
                <EmptyState
                  title="No similarity panel yet"
                  description="The backend could not recover enough strategy-rule payloads to compute nearest neighbors for this strategy."
                  tone="warning"
                  eyebrow="Clone-pressure signal unavailable"
                  meaning="You cannot yet tell whether this strategy is unique or quietly overlapping with near-duplicates in the same family slot."
                  nextStep="Rely on duplicate-risk context and family comparison until rule payload coverage is restored for similarity scoring."
                />
              ) : (
                <div className="dashboard-stack">
                  <div className="panel">
                    <p>{compactValue(similarityPanel.summary ?? similarityPanel.headline ?? duplicateRiskContext.summary)}</p>
                  </div>

                  <section className="stats-grid">
                    <StatCard
                      label="Nearest similarity"
                      value={formatPercent(pickFirstNumber(similarityNearest.similarity, similarityTarget.research_nearest_similarity))}
                      hint={compactValue(similarityNearest.name ?? "Research nearest snapshot")}
                      tone={toneFromBadgeTone(similarityPanel.tone)}
                    />
                    <StatCard
                      label="Novelty score"
                      value={formatNumber(pickFirstNumber(similarityTarget.research_novelty_score))}
                      hint="Higher is less clone-like"
                      tone={(() => {
                        const novelty = pickFirstNumber(similarityTarget.research_novelty_score);
                        if (novelty == null) return "neutral" as const;
                        if (novelty <= 0.08) return "critical" as const;
                        if (novelty <= 0.12) return "warning" as const;
                        return "success" as const;
                      })()}
                    />
                    <StatCard
                      label="High-sim neighbors"
                      value={formatNumber(pickFirstNumber(similarityPanel.high_similarity_count))}
                      hint=">= 85% semantic similarity"
                      tone={toneFromMagnitude(pickFirstNumber(similarityPanel.high_similarity_count), 1, 3)}
                    />
                    <StatCard
                      label="Structural clones"
                      value={formatNumber(pickFirstNumber(similarityPanel.structural_clone_count))}
                      hint="Exact core-rule matches"
                      tone={pickFirstNumber(similarityPanel.structural_clone_count) ? "critical" : "success"}
                    />
                  </section>

                  <section className="stats-grid">
                    <StatCard
                      label="Semantic duplicate skips"
                      value={formatNumber(pickFirstNumber(duplicateRiskContext.semantic_duplicate_count))}
                      hint={compactValue(duplicateRiskContext.generated_at ? `Latest research run ${formatDateTime(duplicateRiskContext.generated_at)}` : "Latest research-family snapshot")}
                      tone={pickFirstNumber(duplicateRiskContext.semantic_duplicate_count) ? "warning" : "success"}
                    />
                    <StatCard
                      label="Memory veto skips"
                      value={formatNumber(pickFirstNumber(duplicateRiskContext.memory_veto_count))}
                      hint="Candidates rejected because similar historical neighbors looked structurally bad"
                      tone={pickFirstNumber(duplicateRiskContext.memory_veto_count) ? "critical" : "success"}
                    />
                    <StatCard
                      label="Family generated / accepted"
                      value={compactValue(`${formatNumber(pickFirstNumber(duplicateRiskContext.family_generated))} / ${formatNumber(pickFirstNumber(duplicateRiskContext.family_accepted))}`)}
                      hint={compactValue(duplicateRiskContext.family ? `${duplicateRiskContext.family} in latest slot research` : "Family throughput")}
                      tone="info"
                    />
                    <StatCard
                      label="Veto pressure"
                      value={compactValue(duplicateRiskContext.risk_label)}
                      hint={compactValue(duplicateRiskContext.symbol && duplicateRiskContext.timeframe ? `${duplicateRiskContext.symbol} ${duplicateRiskContext.timeframe} research context` : "Research veto context")}
                      tone={toneFromBadgeTone(duplicateRiskContext.tone)}
                    />
                  </section>

                  {duplicateRiskReasons.length ? (
                    <DataTable
                      columns={["Veto lane", "Count", "Example candidates", "Reading"]}
                      rows={duplicateRiskReasons.map((item, index) => [
                        <StatusBadge key={`duplicate-risk-reason-${index}`} label={compactValue(item.label ?? item.reason)} tone={toneFromBadgeTone(item.tone)} />,
                        formatNumber(pickFirstNumber(item.count)),
                        compactValue(Array.isArray(item.samples) ? item.samples.join(", ") : item.samples),
                        compactValue(item.reading),
                      ])}
                      emptyTitle="No duplicate-risk veto rows"
                      emptyDescription="The latest research-family snapshot did not log semantic-duplicate or memory-veto skips for this strategy family."
                    />
                  ) : null}

                  <DataTable
                    columns={["Neighbor", "Similarity", "Relationship", "Status", "Research / live", "Novelty", "Risk"]}
                    rows={similarityNeighbors.map((item, index) => [
                      <div key={`neighbor-${index}`}>
                        <strong>{compactValue(item.name)}</strong>
                        <div className="table-subtext">{compactValue(`${item.symbol ?? "?"} / ${item.timeframe ?? "?"} · ${item.family ?? "unknown"}`)}</div>
                      </div>,
                      formatPercent(pickFirstNumber(item.similarity)),
                      compactValue(item.relationship),
                      <StatusBadge key={`neighbor-status-${index}`} label={compactValue(item.status)} tone={toneFromStrategyStatus(pickFirstString(item.status))} />,
                      `${formatPercent(pickFirstNumber(item.research_return_pct))} · ${formatCurrency(pickFirstNumber(item.live_total_pnl))}`,
                      formatNumber(pickFirstNumber(item.research_novelty_score)),
                      <StatusBadge key={`neighbor-risk-${index}`} label={compactValue(item.risk_label)} tone={toneFromBadgeTone(item.risk_tone)} />,
                    ])}
                    emptyTitle="No comparable neighbors"
                    emptyDescription="The current pool did not surface any comparable strategy rules for this selection."
                  />

                  <div className="detail-grid-2">
                    <Section title="Nearest neighbor reading" description="Why the top neighbor matters operationally.">
                      <div className="panel">
                        <p>
                          {compactValue(similarityPanel.headline)} Same-slot high-similarity neighbors: {formatNumber(pickFirstNumber(similarityPanel.same_slot_high_similarity_count))}. Use this panel to see whether the pool is gaining true diversity or just adding variants of the same playbook.
                        </p>
                      </div>
                    </Section>
                    <Section title="Research veto context" description="How recent research runs are already pushing back on duplicate shapes in this slot.">
                      <div className="panel">
                        <p>{compactValue(duplicateRiskContext.summary ?? "No recent semantic-duplicate or memory-veto context was found for this strategy family.")}</p>
                      </div>
                    </Section>
                  </div>

                  <div className="detail-grid-2">
                    <Section title="Operator cue" description="What to do with high similarity.">
                      <div className="panel">
                        <p>
                          When similarity is high but novelty stays low, extra strategies may add concentration more than coverage. The strongest risk is a same-slot structural clone that can make the pool look broader than it really is.
                        </p>
                      </div>
                    </Section>
                  </div>
                </div>
              )}
            </Section>

            <section className="stats-grid">
              <StatCard
                label="Status"
                value={compactValue(pickFirstString(selectedManifest.status, selectedIndex.status, selectedPool.status))}
                hint={compactValue(pickFirstString(selectedIndex.tier, selectedPool.tier, selectedManifest.tier))}
                tone={relationship.inManifest ? "success" : "warning"}
              />
              <StatCard
                label="Score"
                value={formatNumber(pickFirstNumber(selectedManifest.score, selectedIndex.score, selectedPool.score, selectedPool.pool_score))}
                hint={compactValue(pickFirstString(selectedManifest.symbol, selectedIndex.symbol, selectedPool.symbol))}
                tone="info"
              />
              <StatCard
                label="Family / motif"
                value={compactValue(
                  `${pickFirstString(selectedManifest.family, selectedIndex.family, selectedPool.family) ?? "unknown"} / ${pickFirstString(selectedManifest.motif, selectedIndex.motif, selectedPool.motif) ?? "unknown"}`,
                )}
                hint={compactValue(pickFirstString(selectedManifest.timeframe, selectedIndex.timeframe, selectedPool.timeframe))}
                tone="neutral"
              />
              <StatCard
                label="Live stats"
                value={formatNumber(liveTrades)}
                hint={liveLastUpdate ? `Last update ${formatDateTime(liveLastUpdate)}` : "No live-stat timestamp"}
                tone={toneFromSignedNumber(livePnl)}
              />
            </section>

            <section className="stats-grid">
              <StatCard
                label="Best / worst regime"
                value={compactValue(`${pickFirstString(selectedDerived.best_regime) ?? "unknown"} / ${pickFirstString(selectedDerived.worst_regime) ?? "unknown"}`)}
                hint="Research explain meta"
                tone="info"
              />
              <StatCard
                label="Best / worst session"
                value={compactValue(`${pickFirstString(selectedDerived.best_session) ?? "unknown"} / ${pickFirstString(selectedDerived.worst_session) ?? "unknown"}`)}
                hint="Session edge profile"
                tone="neutral"
              />
              <StatCard
                label="Routing / specialist"
                value={compactValue(`${formatNumber(pickFirstNumber(selectedDerived.routing_confidence))} / ${formatNumber(pickFirstNumber(selectedDerived.specialist_score))}`)}
                hint="Routing confidence / specialist score"
                tone="success"
              />
              <StatCard
                label="Live vs research delta"
                value={formatNumber(liveVsResearchDelta)}
                hint="live_total_pnl - research_return_pct"
                tone={toneFromMagnitude(liveVsResearchDelta, 50, 200)}
              />
            </section>

            <Section title="Key rules summary" description="Entry and exit logic surfaced from the strongest available strategy source.">
              <div className="rule-grid panel">
                <div className="rule-card">
                  <span className="kv-key">Long entry</span>
                  <strong>{compactValue(ruleSource.long_entry_rule)}</strong>
                </div>
                <div className="rule-card">
                  <span className="kv-key">Short entry</span>
                  <strong>{compactValue(ruleSource.short_entry_rule)}</strong>
                </div>
                <div className="rule-card">
                  <span className="kv-key">Exit rule</span>
                  <strong>{compactValue(ruleSource.exit_rule)}</strong>
                </div>
                <div className="rule-card">
                  <span className="kv-key">Risk framing</span>
                  <strong>
                    SL {compactValue(ruleSource.sl_atr_mult ?? ruleSource.stop_loss_pips)} / TP {compactValue(ruleSource.tp_atr_mult ?? ruleSource.take_profit_pips)}
                  </strong>
                </div>
              </div>
            </Section>

            <div className="detail-grid-2">
              <Section title="Regime map" description="Where the strategy actually makes or loses money across detected market regimes.">
                <KeyValueGrid data={coerceRecord(selectedDerived.regime_pnl)} emptyTitle="No regime map" emptyDescription="Research explain did not return regime-level PnL details for this strategy." />
              </Section>
              <Section title="Session map" description="Which sessions contribute most to edge or drag.">
                <KeyValueGrid data={coerceRecord(selectedDerived.session_pnl)} emptyTitle="No session map" emptyDescription="Research explain did not return session-level PnL details for this strategy." />
              </Section>
            </div>

            <Section title="Live stats summary" description="Compact live trading statistics for the selected strategy, when available.">
              <section className="stats-grid">
                <StatCard label="Live trades" value={formatNumber(liveTrades)} hint="num_trades from live stats" tone="info" />
                <StatCard label="Live PnL" value={formatCurrency(livePnl)} hint="total_pnl from live stats" tone={toneFromSignedNumber(livePnl)} />
                <StatCard label="Manifest rank" value={formatNumber(pickFirstNumber(selectedManifest.manifest_rank, selectedIndex.last_manifest_rank))} hint="Last known manifest placement" tone="neutral" />
                <StatCard label="Research return" value={formatPercent(pickFirstNumber(selectedDerived.research_return_pct))} hint="Backtest return pct" tone="success" />
                <StatCard label="Payload health" value={relationship.inManifest || relationship.inPool ? "Shaped" : "Thin"} hint="Whether a strategy payload is available in surfaced layers" tone={relationship.inManifest || relationship.inPool ? "success" : "warning"} />
              </section>
            </Section>

            <div className="detail-grid-2">
              <Section title="Manifest layer" description="Live manifest-facing record for the selected strategy.">
                <KeyValueGrid data={selectedManifest} emptyTitle="Manifest record absent" emptyDescription="This strategy is not currently present in the manifest layer." />
              </Section>
              <Section title="Index layer" description="Strategy index representation used for broader inventory visibility.">
                <KeyValueGrid data={selectedIndex} emptyTitle="Index record absent" emptyDescription="This strategy is not present in the strategy index payload." />
              </Section>
              <Section title="Pool layer" description="Pool record for the selected strategy.">
                <KeyValueGrid data={selectedPool} emptyTitle="Pool record absent" emptyDescription="This strategy is not currently recoverable from the pool record set." />
              </Section>
              <Section title="Live-stat layer" description="Runtime performance counters for the selected strategy.">
                <KeyValueGrid data={selectedLiveStats} emptyTitle="Live stats absent" emptyDescription="The runtime stats file currently has no entry for this strategy." />
              </Section>
            </div>
          </div>
        )}
      </Section>

      <Section title="Top strategy records" description="Highest-ranked strategies from the pool summary endpoint.">
        <DataTable
          columns={["Name", "Symbol", "Timeframe", "Status", "Score"]}
          rows={data.top_strategies.map((strategy) => [
            strategy.name,
            strategy.symbol,
            strategy.timeframe,
            strategy.status,
            formatNumber(strategy.score),
          ])}
          emptyTitle="No top strategy rows"
          emptyDescription="The pool summary returned no top-ranked strategies for this snapshot."
        />
      </Section>

      <Section
        title="Compare families"
        description="Family-level scoreboard so operators can see which research lineage owns manifest depth, live traction, and the highest DNA risk density."
        action={familyCompareRows.length ? <StatusBadge label={`${formatNumber(familyCompareRows.length)} families`} tone="info" /> : null}
      >
        {!familyCompareRows.length ? (
          <EmptyState title="No family comparison available" description="The backend did not return any aggregated family comparison rows for this pool snapshot." />
        ) : (
          <div className="dashboard-stack">
            <section className="stats-grid">
              <StatCard
                label="Strongest research family"
                value={familyRowLabel(strongestResearchFamily)}
                hint={formatPercent(pickFirstNumber(strongestResearchFamily.avg_research_return_pct))}
                tone="success"
              />
              <StatCard
                label="Strongest live family"
                value={familyRowLabel(strongestLiveFamily)}
                hint={formatCurrency(pickFirstNumber(strongestLiveFamily.live_total_pnl))}
                tone="info"
              />
              <StatCard
                label="Deepest manifest family"
                value={familyRowLabel(deepestManifestFamily)}
                hint={`${formatNumber(pickFirstNumber(deepestManifestFamily.manifest_count))} manifest strategies`}
                tone="neutral"
              />
              <StatCard
                label="Highest warning density"
                value={familyRowLabel(highestWarningDensityFamily)}
                hint={formatPercent(pickFirstNumber(highestWarningDensityFamily.warning_density))}
                tone="warning"
              />
            </section>

            <DataTable
              columns={[
                "Family",
                "Inventory",
                "Manifest / live",
                "Status mix",
                "Avg score",
                "Research return",
                "Live PnL / trades",
                "Delta",
                "DNA risk",
                "Dominant posture",
              ]}
              rows={familyCompareRows.map((row) => {
                const record = coerceRecord(row);
                const strategyCount = pickFirstNumber(record.strategy_count);
                const manifestCount = pickFirstNumber(record.manifest_count);
                const liveCount = pickFirstNumber(record.live_count);
                const activeCount = pickFirstNumber(record.active_count);
                const candidateCount = pickFirstNumber(record.candidate_count);
                const exploratoryCount = pickFirstNumber(record.exploratory_count);
                const disabledCount = pickFirstNumber(record.disabled_count);
                const avgScore = pickFirstNumber(record.avg_score);
                const avgResearchReturnPct = pickFirstNumber(record.avg_research_return_pct);
                const avgResearchSharpe = pickFirstNumber(record.avg_research_sharpe);
                const liveTotalPnl = pickFirstNumber(record.live_total_pnl);
                const liveTradesTotal = pickFirstNumber(record.live_trades_total);
                const avgLiveVsResearchDelta = pickFirstNumber(record.avg_live_vs_research_delta);
                const warningDensity = pickFirstNumber(record.warning_density);
                const fragilityDensity = pickFirstNumber(record.fragility_density);
                return [
                  <div key={`family-${compactValue(record.family)}`}>
                    <strong>{familyRowLabel(record)}</strong>
                    <div className="table-subtext">{compactValue(record.family)}</div>
                  </div>,
                  formatNumber(strategyCount),
                  `${formatNumber(manifestCount)} / ${formatNumber(liveCount)}`,
                  `A ${formatNumber(activeCount)} · C ${formatNumber(candidateCount)} · E ${formatNumber(exploratoryCount)} · D ${formatNumber(disabledCount)}`,
                  formatNumber(avgScore),
                  `${formatPercent(avgResearchReturnPct)} · Sharpe ${formatNumber(avgResearchSharpe)}`,
                  `${formatCurrency(liveTotalPnl)} · ${formatNumber(liveTradesTotal)}`,
                  formatNumber(avgLiveVsResearchDelta),
                  `${formatPercent(warningDensity)} warn · ${formatPercent(fragilityDensity)} fragile`,
                  `${compactValue(record.dominant_archetype)} · ${compactValue(record.top_regime)} / ${compactValue(record.top_session)}`,
                ];
              })}
              emptyTitle="No family rows"
              emptyDescription="No family-level aggregates could be formed from the current pool snapshot."
            />

            <div className="detail-grid-2">
              <Section title="Family operator reading" description="Quick synthesis of the current family pecking order.">
                <div className="panel">
                  <p>
                    {familyRowLabel(strongestResearchFamily)} currently leads research return, while {familyRowLabel(strongestLiveFamily)} carries the strongest live PnL. Use the manifest-depth and DNA-risk columns to decide whether the same family deserves more exposure or tighter review.
                  </p>
                </div>
              </Section>
              <Section title="Why this matters" description="Family comparison helps separate a single standout strategy from a repeatable lineage.">
                <div className="panel">
                  <p>
                    When one family owns both manifest depth and live traction, the pool is leaning into a clear research lineage. If warning density rises at the same time, that concentration can become a governance risk instead of a strength.
                  </p>
                </div>
              </Section>
            </div>
          </div>
        )}
      </Section>

      <Section
        title="Compare two strategies"
        description="Head-to-head view for DNA, live posture, research edge, and mismatch risk before deciding which strategy deserves operator attention."
        action={resolvedCompareStrategy ? <StatusBadge label={`${resolvedSelectedStrategy} vs ${resolvedCompareStrategy}`} tone="info" /> : null}
      >
        <QueryStateNotice
          error={compareDetailQuery.error}
          refreshing={compareDetailQuery.refreshing}
          hasData={Boolean(compareDetail)}
          resourceLabel={`comparison detail for ${resolvedCompareStrategy}`}
          lastSuccessAt={compareDetailQuery.lastSuccessAt}
        />

        {!resolvedSelectedStrategy ? (
          <EmptyState title="No primary strategy selected" description="Choose the first strategy from the explorer before opening a head-to-head comparison." />
        ) : !comparisonCandidates.length ? (
          <EmptyState title="No second strategy available" description="Widen the filters or choose a broader slice of the inventory to compare against another strategy." />
        ) : (
          <div className="dashboard-stack">
            <div className="filter-toolbar panel compare-toolbar">
              <label className="filter-field">
                <span>Primary</span>
                <select className="filter-input" value={resolvedSelectedStrategy} onChange={(event) => setPoolUrlState({ strategy: event.target.value })}>
                  {filteredStrategies.map((strategy) => (
                    <option key={`primary-${strategy.name}`} value={strategy.name}>
                      {strategy.name}
                    </option>
                  ))}
                </select>
              </label>
              <label className="filter-field">
                <span>Compare against</span>
                <select className="filter-input" value={resolvedCompareStrategy} onChange={(event) => setPoolUrlState({ compare: event.target.value })}>
                  {comparisonCandidates.map((strategy) => (
                    <option key={`compare-${strategy.name}`} value={strategy.name}>
                      {strategy.name}
                    </option>
                  ))}
                </select>
              </label>
              <div className="filter-summary">
                <span className="eyebrow">Shared slot</span>
                <strong>
                  {primaryComparisonSummary.symbol === secondaryComparisonSummary.symbol && primaryComparisonSummary.timeframe === secondaryComparisonSummary.timeframe
                    ? `${compactValue(primaryComparisonSummary.symbol)} / ${compactValue(primaryComparisonSummary.timeframe)}`
                    : "Cross-slot compare"}
                </strong>
              </div>
              <div className="filter-summary">
                <span className="eyebrow">DNA contrast</span>
                <strong>{compareEdgeLabel(primaryComparisonSummary.warningCount, secondaryComparisonSummary.warningCount, formatNumber)}</strong>
              </div>
            </div>

            {compareDetailQuery.loading && !compareDetail ? (
              <LoadingState title="Loading comparison detail" description="Pulling a second strategy payload for head-to-head operator review." />
            ) : compareDetailQuery.error && !compareDetail ? (
              <ErrorState error={compareDetailQuery.error} resourceLabel={`comparison detail for ${resolvedCompareStrategy}`} />
            ) : !compareDetail ? (
              <EmptyState title="No comparison detail returned" description="The second strategy could not be resolved into a detail payload." />
            ) : (
              <>
                <section className="stats-grid">
                  <StatCard
                    label="Primary posture"
                    value={compactValue(primaryComparisonSummary.status)}
                    hint={compactValue(`${primaryComparisonSummary.name} · ${primaryComparisonSummary.tier ?? "unknown tier"}`)}
                    tone={toneFromStrategyStatus(primaryComparisonSummary.status ?? null)}
                  />
                  <StatCard
                    label="Compare posture"
                    value={compactValue(secondaryComparisonSummary.status)}
                    hint={compactValue(`${secondaryComparisonSummary.name} · ${secondaryComparisonSummary.tier ?? "unknown tier"}`)}
                    tone={toneFromStrategyStatus(secondaryComparisonSummary.status ?? null)}
                  />
                  <StatCard
                    label="Research return edge"
                    value={compareEdgeLabel(primaryComparisonSummary.researchReturnPct, secondaryComparisonSummary.researchReturnPct, (value) => formatPercent(value))}
                    hint="Backtest return pct gap"
                    tone={toneFromSignedNumber((primaryComparisonSummary.researchReturnPct ?? 0) - (secondaryComparisonSummary.researchReturnPct ?? 0))}
                  />
                  <StatCard
                    label="Live PnL edge"
                    value={compareEdgeLabel(primaryComparisonSummary.livePnl, secondaryComparisonSummary.livePnl, (value) => formatCurrency(value))}
                    hint="Current runtime PnL gap"
                    tone={toneFromSignedNumber((primaryComparisonSummary.livePnl ?? 0) - (secondaryComparisonSummary.livePnl ?? 0))}
                  />
                </section>

                <div className="detail-grid-2">
                  <Section title={primaryComparisonSummary.name} description="Primary strategy snapshot for the current comparison.">
                    <div className="dashboard-stack">
                      <div className="panel">
                        <p>{compactValue(primaryComparisonSummary.identitySummary)}</p>
                      </div>
                      <div className="badge-row">
                        {primaryComparisonSummary.badges.map((item, index) => (
                          <StatusBadge key={`primary-badge-${index}`} label={compactValue(item.label)} tone={toneFromBadgeTone(item.tone)} />
                        ))}
                      </div>
                    </div>
                  </Section>
                  <Section title={secondaryComparisonSummary.name} description="Secondary strategy snapshot for the current comparison.">
                    <div className="dashboard-stack">
                      <div className="panel">
                        <p>{compactValue(secondaryComparisonSummary.identitySummary)}</p>
                      </div>
                      <div className="badge-row">
                        {secondaryComparisonSummary.badges.map((item, index) => (
                          <StatusBadge key={`secondary-badge-${index}`} label={compactValue(item.label)} tone={toneFromBadgeTone(item.tone)} />
                        ))}
                      </div>
                    </div>
                  </Section>
                </div>

                <Section title="Head-to-head matrix" description="Fast operator comparison of posture, routing quality, DNA risk, and live-vs-research fit.">
                  <DataTable
                    columns={["Dimension", primaryComparisonSummary.name, secondaryComparisonSummary.name, "Edge"]}
                    rows={[
                      ["Symbol / timeframe", compactValue(`${primaryComparisonSummary.symbol ?? "unknown"} / ${primaryComparisonSummary.timeframe ?? "unknown"}`), compactValue(`${secondaryComparisonSummary.symbol ?? "unknown"} / ${secondaryComparisonSummary.timeframe ?? "unknown"}`), primaryComparisonSummary.symbol === secondaryComparisonSummary.symbol && primaryComparisonSummary.timeframe === secondaryComparisonSummary.timeframe ? "Same slot" : "Different slot"],
                      ["Family / motif", compactValue(`${primaryComparisonSummary.family ?? "unknown"} / ${primaryComparisonSummary.motif ?? "unknown"}`), compactValue(`${secondaryComparisonSummary.family ?? "unknown"} / ${secondaryComparisonSummary.motif ?? "unknown"}`), primaryComparisonSummary.family === secondaryComparisonSummary.family ? "Same family" : "Different family"],
                      ["Score", formatNumber(primaryComparisonSummary.score), formatNumber(secondaryComparisonSummary.score), compareEdgeLabel(primaryComparisonSummary.score, secondaryComparisonSummary.score, formatNumber)],
                      ["Manifest rank", formatNumber(primaryComparisonSummary.manifestRank), formatNumber(secondaryComparisonSummary.manifestRank), compareEdgeLabel(secondaryComparisonSummary.manifestRank != null ? -secondaryComparisonSummary.manifestRank : null, primaryComparisonSummary.manifestRank != null ? -primaryComparisonSummary.manifestRank : null, (value) => formatNumber(Math.abs(value ?? 0)))],
                      ["Research return", formatPercent(primaryComparisonSummary.researchReturnPct), formatPercent(secondaryComparisonSummary.researchReturnPct), compareEdgeLabel(primaryComparisonSummary.researchReturnPct, secondaryComparisonSummary.researchReturnPct, formatPercent)],
                      ["Research sharpe", formatNumber(primaryComparisonSummary.researchSharpe), formatNumber(secondaryComparisonSummary.researchSharpe), compareEdgeLabel(primaryComparisonSummary.researchSharpe, secondaryComparisonSummary.researchSharpe, formatNumber)],
                      ["Live PnL", formatCurrency(primaryComparisonSummary.livePnl), formatCurrency(secondaryComparisonSummary.livePnl), compareEdgeLabel(primaryComparisonSummary.livePnl, secondaryComparisonSummary.livePnl, formatCurrency)],
                      ["Live trades", formatNumber(primaryComparisonSummary.liveTrades), formatNumber(secondaryComparisonSummary.liveTrades), compareEdgeLabel(primaryComparisonSummary.liveTrades, secondaryComparisonSummary.liveTrades, formatNumber)],
                      ["Live vs research delta", formatNumber(primaryComparisonSummary.liveVsResearchDelta), formatNumber(secondaryComparisonSummary.liveVsResearchDelta), compareEdgeLabel(primaryComparisonSummary.liveVsResearchDelta != null ? -Math.abs(primaryComparisonSummary.liveVsResearchDelta) : null, secondaryComparisonSummary.liveVsResearchDelta != null ? -Math.abs(secondaryComparisonSummary.liveVsResearchDelta) : null, (value) => formatNumber(Math.abs(value ?? 0)))],
                      ["Routing confidence", formatNumber(primaryComparisonSummary.routingConfidence), formatNumber(secondaryComparisonSummary.routingConfidence), compareEdgeLabel(primaryComparisonSummary.routingConfidence, secondaryComparisonSummary.routingConfidence, formatNumber)],
                      ["Specialist score", formatNumber(primaryComparisonSummary.specialistScore), formatNumber(secondaryComparisonSummary.specialistScore), compareEdgeLabel(primaryComparisonSummary.specialistScore, secondaryComparisonSummary.specialistScore, formatNumber)],
                      ["Best regime", compactValue(primaryComparisonSummary.bestRegime), compactValue(secondaryComparisonSummary.bestRegime), primaryComparisonSummary.bestRegime === secondaryComparisonSummary.bestRegime ? "Shared best regime" : "Different regime edge"],
                      ["Best session", compactValue(primaryComparisonSummary.bestSession), compactValue(secondaryComparisonSummary.bestSession), primaryComparisonSummary.bestSession === secondaryComparisonSummary.bestSession ? "Shared best session" : "Different session edge"],
                      ["Archetype", compactValue(primaryComparisonSummary.archetype), compactValue(secondaryComparisonSummary.archetype), primaryComparisonSummary.archetype === secondaryComparisonSummary.archetype ? "Shared DNA" : "Different DNA"],
                      ["DNA warnings", formatNumber(primaryComparisonSummary.warningCount), formatNumber(secondaryComparisonSummary.warningCount), compareEdgeLabel(secondaryComparisonSummary.warningCount != null ? -secondaryComparisonSummary.warningCount : null, primaryComparisonSummary.warningCount != null ? -primaryComparisonSummary.warningCount : null, (value) => formatNumber(Math.abs(value ?? 0)))],
                      ["Fragility markers", formatNumber(primaryComparisonSummary.fragilityCount), formatNumber(secondaryComparisonSummary.fragilityCount), compareEdgeLabel(secondaryComparisonSummary.fragilityCount != null ? -secondaryComparisonSummary.fragilityCount : null, primaryComparisonSummary.fragilityCount != null ? -primaryComparisonSummary.fragilityCount : null, (value) => formatNumber(Math.abs(value ?? 0)))],
                      ["Decay warnings", formatNumber(primaryComparisonSummary.decayWarningCount), formatNumber(secondaryComparisonSummary.decayWarningCount), compareEdgeLabel(secondaryComparisonSummary.decayWarningCount != null ? -secondaryComparisonSummary.decayWarningCount : null, primaryComparisonSummary.decayWarningCount != null ? -primaryComparisonSummary.decayWarningCount : null, (value) => formatNumber(Math.abs(value ?? 0)))],
                    ]}
                  />
                </Section>

                <div className="detail-grid-2">
                  <Section title="Regime map contrast" description="Research regime distribution for both strategies in one table.">
                    <DataTable
                      columns={["Regime", primaryComparisonSummary.name, secondaryComparisonSummary.name]}
                      rows={compareRegimeRows}
                      emptyTitle="No regime comparison"
                      emptyDescription="One or both strategies did not expose regime-level research context."
                    />
                  </Section>
                  <Section title="Session map contrast" description="Session edge concentration side by side.">
                    <DataTable
                      columns={["Session", primaryComparisonSummary.name, secondaryComparisonSummary.name]}
                      rows={compareSessionRows}
                      emptyTitle="No session comparison"
                      emptyDescription="One or both strategies did not expose session-level research context."
                    />
                  </Section>
                </div>

                <div className="detail-grid-2">
                  <Section title="Warning contrast" description="Mismatch, dependence, and operator-risk warnings surfaced by the DNA layer.">
                    <DataTable
                      columns={["Strategy", "Warnings", "Fragility markers"]}
                      rows={[
                        [
                          primaryComparisonSummary.name,
                          primaryComparisonSummary.warnings.length
                            ? primaryComparisonSummary.warnings.map((item) => compactValue(item.label)).join(", ")
                            : "None",
                          primaryComparisonSummary.fragilityMarkers.length
                            ? primaryComparisonSummary.fragilityMarkers.map((item) => compactValue(item.label)).join(", ")
                            : "None",
                        ],
                        [
                          secondaryComparisonSummary.name,
                          secondaryComparisonSummary.warnings.length
                            ? secondaryComparisonSummary.warnings.map((item) => compactValue(item.label)).join(", ")
                            : "None",
                          secondaryComparisonSummary.fragilityMarkers.length
                            ? secondaryComparisonSummary.fragilityMarkers.map((item) => compactValue(item.label)).join(", ")
                            : "None",
                        ],
                      ]}
                    />
                  </Section>
                  <Section title="Operator reading" description="Quick synthesis of what the head-to-head actually means.">
                    <div className="panel">
                      <p>
                        {primaryComparisonSummary.name} leads on research return {formatPercent(primaryComparisonSummary.researchReturnPct)} versus {formatPercent(secondaryComparisonSummary.researchReturnPct)}, while live PnL currently sits at {formatCurrency(primaryComparisonSummary.livePnl)} versus {formatCurrency(secondaryComparisonSummary.livePnl)}. Use the matrix above to decide whether the stronger research profile is also the safer live operator candidate.
                      </p>
                    </div>
                  </Section>
                </div>
              </>
            )}
          </div>
        )}
      </Section>
    </div>
  );
}

export default function PoolPage() {
  return (
    <Suspense fallback={<LoadingState title="Loading pool overview" description="Restoring URL-driven strategy selection." />}>
      <PoolPageContent />
    </Suspense>
  );
}
