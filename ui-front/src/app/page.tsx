"use client";

import { PageHeader } from "@/components/app-shell";
import {
  DataTable,
  EmptyState,
  ErrorState,
  FreshnessBadge,
  InlineNotice,
  KeyValueGrid,
  LoadingState,
  Section,
  StatCard,
  StatusBadge,
  StatusStrip,
  ToolbarButton,
} from "@/components/dashboard";
import { useQuery } from "@/hooks/use-query";
import { uiApi } from "@/lib/api";
import { formatCurrency, formatDateTime, formatNumber } from "@/lib/format";
import { coerceRecord, getFreshnessState, toneFromBoolean, toneFromSignedNumber } from "@/lib/ui-state";

export default function OverviewPage() {
  const overviewQuery = useQuery("overview", uiApi.overview, { refetchIntervalMs: 45_000 });
  const executionQuery = useQuery("overview-execution-summary", uiApi.executionSummary, {
    refetchIntervalMs: 60_000,
  });

  const { data, error, loading, hasData, refreshing, refresh } = overviewQuery;
  const executionData = executionQuery.data;

  if (loading && !hasData) {
    return <LoadingState title="Loading overview" description="Building the operator overview snapshot and runtime health strip." />;
  }

  if (!data) {
    return <ErrorState error={error} resourceLabel="overview payload" />;
  }

  const freshness = getFreshnessState(data.generated_at, { warningMs: 10 * 60_000, criticalMs: 30 * 60_000 });
  const unmatchedClosedDeals = Number(executionData?.unmatched_closed_deals?.count ?? 0);
  const openTrades = Number(executionData?.open_trades?.count ?? 0);
  const artifactsReady = data.manifest_entry_count > 0 && data.strategy_index_entry_count > 0;

  return (
    <div className="dashboard-stack">
      <PageHeader
        title="Overview"
        subtitle="Fast operator scan of backend reachability, daily lock posture, artifact presence, pool readiness, and where live allocation is concentrating."
        meta={`Snapshot ${formatDateTime(data.generated_at)}`}
        action={
          <div className="page-toolbar">
            <FreshnessBadge timestamp={data.generated_at} thresholds={{ warningMs: 10 * 60_000, criticalMs: 30 * 60_000 }} />
            <ToolbarButton
              label="Refresh now"
              onClick={() => {
                void Promise.all([refresh(), executionQuery.refresh()]);
              }}
              busy={refreshing || executionQuery.refreshing}
              tone="info"
            />
          </div>
        }
      />

      {freshness.isStale ? (
        <InlineNotice
          tone={freshness.tone}
          title="Overview snapshot is aging"
          description={`${freshness.description}. The route still renders, but some operator decisions may now depend on stale state.`}
        />
      ) : null}

      {executionQuery.error && !executionData ? (
        <InlineNotice
          tone="warning"
          title="Execution sidecar unavailable"
          description="The overview loaded, but the auxiliary execution summary did not. The status strip below may be missing open-trade and anomaly context until the next refresh succeeds."
        />
      ) : null}

      <StatusStrip
        items={[
          {
            label: "Backend reachability",
            value: "Reachable",
            tone: "success",
            detail: "The overview endpoint responded and the operator UI has a usable payload.",
          },
          {
            label: "Trading day",
            value: data.locked_for_day ? "Locked" : "Active",
            tone: toneFromBoolean(Boolean(data.locked_for_day), false),
            detail: data.locked_for_day
              ? "locked_for_day=true. Inactivity may be intentional."
              : `Live state date ${data.live_state_date ?? "unknown"}`,
          },
          {
            label: "Runtime artifacts",
            value: artifactsReady ? "Present" : "Missing / thin",
            tone: artifactsReady ? "success" : "warning",
            detail: `${formatNumber(data.manifest_entry_count)} manifest entries · ${formatNumber(data.strategy_index_entry_count)} index entries`,
          },
          {
            label: "Open trades",
            value: executionData ? formatNumber(openTrades) : "Unknown",
            tone: executionData ? (openTrades > 0 ? "info" : "neutral") : "warning",
            detail: executionData
              ? openTrades > 0
                ? "Live positions are currently visible in the execution summary."
                : "No live positions were reported in the latest execution snapshot."
              : "Execution summary sidecar is unavailable right now.",
          },
          {
            label: "Audit attention",
            value: executionData ? (unmatchedClosedDeals > 0 ? "Attention" : "Quiet") : "Unknown",
            tone: executionData
              ? unmatchedClosedDeals > 0
                ? unmatchedClosedDeals >= 5
                  ? "critical"
                  : "warning"
                : "success"
              : "warning",
            detail: executionData
              ? unmatchedClosedDeals > 0
                ? `${formatNumber(unmatchedClosedDeals)} unmatched closed deals need operator review.`
                : "No unmatched closed deals were surfaced by the execution summary."
              : "Audit attention cannot be assessed until the execution sidecar returns.",
          },
        ]}
      />

      <section className="stats-grid">
        <StatCard label="Equity" value={formatCurrency(data.equity_current)} hint="Current account equity" tone="info" />
        <StatCard
          label="Daily PnL"
          value={formatCurrency(data.daily_pnl)}
          hint="Realized + floating for the session"
          tone={toneFromSignedNumber(data.daily_pnl)}
        />
        <StatCard label="Trades today" value={formatNumber(data.trades_today)} hint="Executed trades logged today" tone="neutral" />
        <StatCard
          label="Manifest load"
          value={formatNumber(data.manifest_entry_count)}
          hint={`${formatNumber(data.strategy_index_entry_count)} indexed candidates`}
          tone={artifactsReady ? "success" : "warning"}
        />
      </section>

      <Section
        title="Session posture"
        description="Immediate risk posture and daily lock conditions for the active trading date."
        action={<StatusBadge label={data.locked_for_day ? "Day locked" : "Trading enabled"} tone={data.locked_for_day ? "warning" : "success"} />}
      >
        <div className="badge-row">
          <StatusBadge label={`Live date ${data.live_state_date ?? "unknown"}`} tone="info" />
          <StatusBadge label={`Pool total ${formatNumber(data.pool_total)}`} />
          <StatusBadge label={`Live slots ${formatNumber(data.live_slots.length)}`} tone={data.live_slots.length ? "success" : "warning"} />
          <FreshnessBadge timestamp={coerceRecord(data.diagnostics).manifest_generated_at} thresholds={{ warningMs: 30 * 60_000, criticalMs: 2 * 60 * 60_000 }} />
        </div>
      </Section>

      <Section title="Pool status mix" description="Distribution of inventory state across the current strategy pool.">
        {Object.keys(data.pool_status_counts ?? {}).length ? (
          <KeyValueGrid data={data.pool_status_counts} />
        ) : (
          <EmptyState
            title="Pool summary is empty"
            description="The overview payload returned no pool status buckets. That usually means the pool artifact is missing, empty, or the backend returned a stripped snapshot."
          />
        )}
      </Section>

      <Section title="Live slot concentration" description="Where current live allocation is clustering by symbol and timeframe.">
        <DataTable
          columns={["Symbol", "Timeframe", "Count"]}
          rows={data.live_slots.map((slot) => [slot.symbol, slot.timeframe, formatNumber(slot.count)])}
          emptyTitle="No live-slot rows"
          emptyDescription="The overview returned no manifest slot distribution. The manifest may be empty or unavailable."
        />
      </Section>

      <Section title="Diagnostics extract" description="Backend-provided overview diagnostics surfaced without reinterpretation.">
        <KeyValueGrid
          data={data.diagnostics}
          emptyTitle="No diagnostics"
          emptyDescription="The overview route responded, but it did not provide extra diagnostic metadata for this snapshot."
        />
      </Section>
    </div>
  );
}
