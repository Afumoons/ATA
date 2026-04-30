"use client";

import { PageHeader } from "@/components/app-shell";
import {
  AttentionCard,
  DataTable,
  EmptyState,
  ErrorState,
  FreshnessBadge,
  InlineNotice,
  InsightCard,
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
import { formatCurrency, formatDateTime, formatNumber, formatPercent, formatRelativeAge } from "@/lib/format";
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
  const poolStatusEntries = Object.entries(data.pool_status_counts ?? {}).sort((left, right) => Number(right[1]) - Number(left[1]));
  const topPoolStatus = poolStatusEntries[0];
  const liveSlotRows = [...(data.live_slots ?? [])].sort((left, right) => right.count - left.count);
  const topLiveSlot = liveSlotRows[0];
  const secondLiveSlot = liveSlotRows[1];
  const totalLiveSlotCount = liveSlotRows.reduce((sum, slot) => sum + Number(slot.count ?? 0), 0);
  const topLiveSlotShare = totalLiveSlotCount > 0 && topLiveSlot ? topLiveSlot.count / totalLiveSlotCount : 0;
  const diagnostics = coerceRecord(data.diagnostics);
  const manifestFreshness = getFreshnessState(diagnostics.manifest_generated_at, { warningMs: 30 * 60_000, criticalMs: 2 * 60 * 60_000 });
  const executionFreshness = getFreshnessState(executionData?.generated_at, { warningMs: 15 * 60_000, criticalMs: 45 * 60_000 });

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
          <FreshnessBadge timestamp={diagnostics.manifest_generated_at} thresholds={{ warningMs: 30 * 60_000, criticalMs: 2 * 60 * 60_000 }} />
        </div>
      </Section>

      <Section title="Operator briefing" description="A faster narrative read on whether capital posture, deployment readiness, reconciliation, and slot concentration all agree before you open deeper cockpit pages.">
        <div className="insight-grid">
          <InsightCard
            eyebrow="Capital posture"
            title={data.locked_for_day ? "Protected / day locked" : "Capital available"}
            description="Use this card to judge whether inactivity is deliberate, whether the session is carrying profit or damage, and whether trade flow is still alive today."
            tone={data.locked_for_day ? "warning" : data.daily_pnl != null && data.daily_pnl < 0 ? "warning" : "success"}
            badges={
              <>
                <StatusBadge label={freshness.label} tone={freshness.tone} />
                <StatusBadge label={`${formatNumber(data.trades_today)} trades today`} tone={data.trades_today ? "info" : "neutral"} />
              </>
            }
            metrics={[
              { label: "Equity", value: formatCurrency(data.equity_current) },
              { label: "Daily PnL", value: formatCurrency(data.daily_pnl) },
              { label: "Trading day", value: data.locked_for_day ? "Locked" : "Active" },
              { label: "Live date", value: data.live_state_date ?? "Unknown" },
            ]}
            footer={<p>{data.locked_for_day ? "The backend explicitly reports a day lock, so low execution activity may be expected until the next session opens." : data.daily_pnl != null && data.daily_pnl < 0 ? "Capital is still engaged, but the session is carrying damage. Cross-check execution and drift before assuming the posture is healthy." : "No top-level session lock is suppressing activity, so the rest of the UI should be read as a live decision surface rather than a parked snapshot."}</p>}
          />

          <InsightCard
            eyebrow="Deployment readiness"
            title={artifactsReady ? "Manifest and index are shaped" : "Deployment surface is thin"}
            description="Manifest and strategy index presence define whether the pool can be trusted as a real deployment picture or only a partial artifact read."
            tone={artifactsReady ? "success" : "warning"}
            badges={
              <>
                <StatusBadge label={manifestFreshness.label} tone={manifestFreshness.tone} />
                <StatusBadge label={topPoolStatus ? `${topPoolStatus[0]} leads` : "No status mix"} tone={topPoolStatus ? "info" : "warning"} />
              </>
            }
            metrics={[
              { label: "Manifest rows", value: formatNumber(data.manifest_entry_count) },
              { label: "Indexed candidates", value: formatNumber(data.strategy_index_entry_count) },
              { label: "Pool inventory", value: formatNumber(data.pool_total) },
              { label: "Top status", value: topPoolStatus ? `${topPoolStatus[0]} (${formatNumber(Number(topPoolStatus[1]))})` : "None" },
            ]}
            footer={<p>{artifactsReady ? "Core deployment artifacts are present. Use Pool and Manifest to inspect composition, then Drift or Execution to decide whether the current shape still deserves trust." : "One of the core operator artifacts is empty or missing, so any deployment judgement from this snapshot should be treated as provisional."}</p>}
          />

          <InsightCard
            eyebrow="Reconciliation watch"
            title={executionData ? (unmatchedClosedDeals > 0 ? `${formatNumber(unmatchedClosedDeals)} anomaly lane(s)` : "Execution sidecar is coherent") : "Execution sidecar missing"}
            description="This is the quickest read on whether the overview agrees with execution reality or whether the session is hiding unresolved operator work."
            tone={executionData ? (unmatchedClosedDeals >= 5 ? "critical" : unmatchedClosedDeals > 0 ? "warning" : openTrades > 0 ? "info" : "success") : "warning"}
            badges={
              <>
                <StatusBadge label={executionData ? executionFreshness.label : "Execution freshness unknown"} tone={executionData ? executionFreshness.tone : "warning"} />
                <StatusBadge label={executionData ? `${formatNumber(openTrades)} open trades` : "Execution unavailable"} tone={executionData ? (openTrades > 0 ? "info" : "neutral") : "warning"} />
              </>
            }
            metrics={[
              { label: "Unmatched closed deals", value: executionData ? formatNumber(unmatchedClosedDeals) : "Unknown" },
              { label: "Open trades", value: executionData ? formatNumber(openTrades) : "Unknown" },
              { label: "Execution snapshot", value: executionData?.generated_at ? formatRelativeAge(executionData.generated_at) : "Unavailable" },
              { label: "Operator read", value: executionData ? (unmatchedClosedDeals > 0 ? "Review execution" : "No obvious reconciliation break") : "Recover sidecar" },
            ]}
            footer={<p>{executionData ? unmatchedClosedDeals > 0 ? "The overview is already signalling reconciliation debt. Jump into Execution before treating any PnL or inactivity reading as settled truth." : "Execution context is available and currently not surfacing unmatched closed-deal debt at the overview level." : "The core overview loaded without its execution companion, so live posture and anomaly confidence are reduced until the sidecar recovers."}</p>}
          />

          <InsightCard
            eyebrow="Live slot focus"
            title={topLiveSlot ? `${topLiveSlot.symbol} ${topLiveSlot.timeframe}` : "No live slot footprint"}
            description="Slot concentration shows where active allocation is piling up before you inspect single strategies."
            tone={topLiveSlot ? (topLiveSlotShare >= 0.45 ? "warning" : topLiveSlotShare >= 0.25 ? "info" : "success") : "neutral"}
            badges={topLiveSlot ? <StatusBadge label={`${formatPercent(topLiveSlotShare * 100)} of live slots`} tone={topLiveSlotShare >= 0.45 ? "warning" : topLiveSlotShare >= 0.25 ? "info" : "success"} /> : null}
            metrics={[
              { label: "Top slot", value: topLiveSlot ? `${topLiveSlot.symbol} / ${topLiveSlot.timeframe}` : "None" },
              { label: "Second slot", value: secondLiveSlot ? `${secondLiveSlot.symbol} / ${secondLiveSlot.timeframe}` : "None" },
              { label: "Distinct live slots", value: formatNumber(liveSlotRows.length) },
              { label: "Total live allocations", value: formatNumber(totalLiveSlotCount) },
            ]}
            footer={<p>{topLiveSlot ? `${topLiveSlot.symbol} ${topLiveSlot.timeframe} is carrying the heaviest live concentration in this snapshot. Use Drift and Pool to check whether that density reflects genuine edge breadth or repeated slot-level overlap.` : "No live-slot distribution was returned, so the overview cannot tell you where current allocation is clustering."}</p>}
          />
        </div>
      </Section>

      <Section title="Attention queue" description="High-signal operator nudges surfaced from reconciliation, artifact freshness, and runtime posture.">
        {data.attention_queue?.length ? (
          <div className="attention-grid">
            {data.attention_queue.map((item, index) => (
              <AttentionCard
                key={`${item.label}-${item.value ?? index}`}
                label={item.label}
                value={item.value != null ? String(item.value) : "Attention"}
                tone={item.tone ?? "warning"}
                detail={item.detail ?? "This snapshot surfaced an operator nudge without extra detail."}
              />
            ))}
          </div>
        ) : (
          <InlineNotice
            title="No urgent operator nudges"
            description="This snapshot did not surface unmatched deals, artifact timestamp mismatches, or obvious no-position warnings."
            tone="success"
          />
        )}
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
          columns={["Slot", "Allocation", "Operator read"]}
          rows={liveSlotRows.map((slot) => {
            const share = totalLiveSlotCount > 0 ? slot.count / totalLiveSlotCount : 0;
            const tone = share >= 0.45 ? "warning" : share >= 0.25 ? "info" : "success";
            return [
              <div className="table-stack" key={`${slot.symbol}-${slot.timeframe}-slot`}>
                <strong>{slot.symbol}</strong>
                <span>{slot.timeframe}</span>
              </div>,
              <div className="table-stack" key={`${slot.symbol}-${slot.timeframe}-allocation`}>
                <strong>{formatNumber(slot.count)} live slots</strong>
                <span>{formatPercent(share * 100)} of surfaced allocation</span>
              </div>,
              <div className="table-stack" key={`${slot.symbol}-${slot.timeframe}-read`}>
                <StatusBadge label={share >= 0.45 ? "High concentration" : share >= 0.25 ? "Meaningful cluster" : "Distributed"} tone={tone} />
                <span>{share >= 0.45 ? "This slot is dominating current live placement and deserves duplicate-risk and drift checks." : share >= 0.25 ? "This slot is carrying a noticeable share of live attention." : "This slot is present without dominating the deployment surface."}</span>
              </div>,
            ];
          })}
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
