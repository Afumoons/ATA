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
  ToolbarButton,
} from "@/components/dashboard";
import { useQuery } from "@/hooks/use-query";
import { uiApi } from "@/lib/api";
import { compactValue, formatCurrency, formatDateTime, formatNumber } from "@/lib/format";
import { getHighSignalExecutionReasons, summarizeEvent, toneFromSignedNumber } from "@/lib/ui-state";

export default function ExecutionPage() {
  const executionQuery = useQuery("execution-summary", uiApi.executionSummary, { refetchIntervalMs: 45_000 });
  const auditQuery = useQuery("execution-audit-context", () => uiApi.auditTimeline(30), { refetchIntervalMs: 60_000 });

  const { data, error, loading, hasData, refreshing, refresh } = executionQuery;

  if (loading && !hasData) {
    return (
      <LoadingState
        title="Loading execution diagnostics"
        description="Collecting live posture, trade traces, reconciliation state, and recent attention events."
      />
    );
  }

  if (!data) {
    return <ErrorState error={error} resourceLabel="execution summary" />;
  }

  const diagnosisItems = getHighSignalExecutionReasons(data);
  const attentionEvents = (auditQuery.data?.events ?? []).filter((event) => {
    const source = String(event.source ?? "").toLowerCase();
    return source.includes("unmatched") || source.includes("trade");
  }).slice(0, 8);

  return (
    <div className="dashboard-stack">
      <PageHeader
        title="Execution diagnostics"
        subtitle="Read-only visibility into live execution state, no-trade context, open positions, reconciliation faults, and the most recent events worth operator attention."
        meta={`Snapshot ${formatDateTime(data.generated_at)}`}
        action={
          <div className="page-toolbar">
            <FreshnessBadge timestamp={data.generated_at} thresholds={{ warningMs: 5 * 60_000, criticalMs: 15 * 60_000 }} />
            <ToolbarButton
              label="Refresh now"
              onClick={() => {
                void Promise.all([refresh(), auditQuery.refresh()]);
              }}
              busy={refreshing || auditQuery.refreshing}
              tone="info"
            />
          </div>
        }
      />

      {auditQuery.error && !auditQuery.data ? (
        <InlineNotice
          tone="warning"
          title="Recent attention events unavailable"
          description="The execution summary loaded, but the companion audit timeline did not. Diagnosis still works, but recent operator-attention events are incomplete for now."
        />
      ) : null}

      <section className="stats-grid">
        <StatCard label="Open trades" value={formatNumber(data.open_trades.count)} hint="Currently open positions" tone="info" />
        <StatCard label="Strategies live" value={formatNumber(data.strategy_live_stats.strategy_count)} hint="Strategies contributing live stats" tone="success" />
        <StatCard label="Trades tracked" value={formatNumber(data.strategy_live_stats.total_trades)} hint="Aggregated strategy trade count" tone="neutral" />
        <StatCard
          label="Realized PnL"
          value={formatCurrency(data.strategy_live_stats.total_realized_pnl)}
          hint="Reported realized PnL"
          tone={toneFromSignedNumber(data.strategy_live_stats.total_realized_pnl)}
        />
      </section>

      <Section
        title="Execution diagnosis summary"
        description="Compact interpretation of the current execution snapshot using existing backend fields only."
        action={
          <StatusBadge
            label={Boolean(data.live_state.locked_for_day) ? "No-trade context: day lock" : "No-trade context: runtime readout"}
            tone={Boolean(data.live_state.locked_for_day) ? "warning" : "info"}
          />
        }
      >
        <div className="diagnosis-grid">
          {diagnosisItems.map((item) => (
            <article key={item.label} className={`panel diagnosis-card tone-${item.tone}`}>
              <StatusBadge label={item.label} tone={item.tone} />
              <p>{item.detail}</p>
            </article>
          ))}
        </div>
      </Section>

      <Section title="Live posture" description="Raw execution-level state from the backend UI API.">
        {Object.keys(data.live_state ?? {}).length ? (
          <KeyValueGrid data={data.live_state} />
        ) : (
          <EmptyState
            title="Live state missing"
            description="The execution endpoint responded, but no live_state object was included. That weakens no-trade diagnosis and backend posture visibility."
          />
        )}
      </Section>

      <Section title="Recent attention events" description="Latest high-signal execution and audit events promoted near the top for operator triage.">
        <DataTable
          columns={["Time", "Source", "Summary", "Symbol / PnL"]}
          rows={attentionEvents.map((event) => [
            formatDateTime(event.recorded_at ?? event.last_update ?? event.timestamp),
            compactValue(event.source),
            summarizeEvent(event),
            compactValue(event.symbol ?? event.profit ?? event.floating_pnl),
          ])}
          emptyTitle="No recent attention events"
          emptyDescription="The recent audit/runtime feed does not currently show unmatched-close or trade-log events that need promotion here."
        />
      </Section>

      <Section title="Top live strategies snapshot" description="Most active live strategies according to the execution summary.">
        <DataTable
          columns={["Strategy", "Trades", "PnL", "Last update", "Recent PnLs"]}
          rows={(data.strategy_live_stats.top_active ?? []).map((item) => [
            compactValue(item.name ?? item.strategy_name),
            compactValue(item.num_trades ?? item.total_trades),
            compactValue(item.total_pnl ?? item.realized_pnl ?? item.pnl),
            compactValue(formatDateTime(item.last_update)),
            compactValue(item.recent_pnls),
          ])}
          emptyTitle="No live strategy rows"
          emptyDescription="The execution summary did not return top_active strategies. Either runtime stats are empty or the backend did not shape them into the payload."
        />
      </Section>

      <Section title="Open trade ledger" description="Current open-trade records returned by the execution summary endpoint.">
        <DataTable
          columns={["Symbol", "Side", "Volume", "Open time", "Floating PnL"]}
          rows={(data.open_trades.trades ?? []).map((trade) => [
            compactValue(trade.symbol),
            compactValue(trade.side ?? trade.direction),
            compactValue(trade.volume ?? trade.lots),
            compactValue(formatDateTime(trade.open_time ?? trade.opened_at)),
            compactValue(trade.floating_pnl ?? trade.pnl ?? trade.profit),
          ])}
          emptyTitle="No open trades"
          emptyDescription="The latest execution snapshot reports zero open positions. If that is unexpected, inspect the diagnosis summary and recent attention events above."
        />
      </Section>

      <Section title="Unmatched closed deals" description="Closed deals that have not been cleanly paired or reconciled.">
        <DataTable
          columns={["Symbol", "Ticket", "Closed at", "Reason", "PnL"]}
          rows={(data.unmatched_closed_deals.recent ?? []).map((deal) => [
            compactValue(deal.symbol),
            compactValue(deal.ticket ?? deal.position_id ?? deal.deal_ticket),
            compactValue(formatDateTime(deal.closed_at ?? deal.recorded_at ?? deal.close_time)),
            compactValue(deal.reason ?? deal.comment),
            compactValue(deal.pnl ?? deal.profit),
          ])}
          emptyTitle="No unmatched closed deals"
          emptyDescription="Closed-deal reconciliation currently looks clean from this route."
        />
      </Section>

      <Section title="Recent trade log" description="Latest execution log entries surfaced directly from the UI API.">
        <DataTable
          columns={["Time", "Strategy", "Event", "Symbol", "Detail"]}
          rows={data.recent_trade_log.map((entry) => [
            compactValue(formatDateTime(entry.timestamp ?? entry.recorded_at ?? entry.time)),
            compactValue(entry.strategy_name ?? entry.strategy),
            compactValue(entry.event ?? entry.type),
            compactValue(entry.symbol),
            compactValue(entry.detail ?? entry.message ?? entry.comment ?? entry.raw),
          ])}
          emptyTitle="Recent trade log is empty"
          emptyDescription="The backend returned no recent trade-log lines for this view."
        />
      </Section>
    </div>
  );
}
