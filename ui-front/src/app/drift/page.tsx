"use client";

import { PageHeader } from "@/components/app-shell";
import {
  DataTable,
  EmptyState,
  ErrorState,
  FreshnessBadge,
  KeyValueGrid,
  LoadingState,
  Section,
  StatCard,
  StatusBadge,
  ToolbarButton,
} from "@/components/dashboard";
import { useQuery } from "@/hooks/use-query";
import { uiApi } from "@/lib/api";
import { compactValue, formatCurrency, formatDateTime, formatNumber, formatPercent } from "@/lib/format";
import { toneFromSignedNumber } from "@/lib/ui-state";

export default function DriftPage() {
  const driftQuery = useQuery("drift-summary", uiApi.driftSummary, { refetchIntervalMs: 60_000 });
  const { data, error, loading, hasData, refreshing, refresh } = driftQuery;

  if (loading && !hasData) {
    return <LoadingState title="Loading drift diagnostics" description="Collecting live-vs-research mismatch and decay-warning candidates." />;
  }

  if (!data) {
    return <ErrorState error={error} resourceLabel="drift summary" />;
  }

  const rows = data.rows ?? [];
  const topAttention = rows.filter((row) => Boolean(row.decay_warning) || Number(row.recent_avg_pnl ?? 0) < 0).slice(0, 12);

  return (
    <div className="dashboard-stack">
      <PageHeader
        title="Drift"
        subtitle="Live-vs-research mismatch view for spotting decay warnings, negative recent averages, and strategies that deserve operator review."
        meta={`Snapshot ${formatDateTime(data.generated_at)}`}
        action={
          <div className="page-toolbar">
            <FreshnessBadge timestamp={data.generated_at} thresholds={{ warningMs: 15 * 60_000, criticalMs: 60 * 60_000 }} />
            <ToolbarButton label="Refresh now" onClick={() => void refresh()} busy={refreshing} tone="info" />
          </div>
        }
      />

      <section className="stats-grid">
        <StatCard label="Tracked strategies" value={formatNumber(Number(data.summary?.strategy_count ?? 0))} hint="Rows surfaced by drift adapter" tone="info" />
        <StatCard label="Attention rows" value={formatNumber(Number(data.summary?.attention_count ?? 0))} hint="Rows with warning-like signals" tone="warning" />
        <StatCard label="Decay warnings" value={formatNumber(Number(data.summary?.decay_warning_count ?? 0))} hint="Live trades >= 3 and recent average below zero" tone="critical" />
        <StatCard label="Negative recent avg" value={formatNumber(Number(data.summary?.negative_recent_avg_count ?? 0))} hint="Recent PnL average below zero" tone="warning" />
      </section>

      <Section title="Drift summary" description="Compact aggregate statistics for the current drift snapshot.">
        <KeyValueGrid data={data.summary ?? {}} emptyTitle="No drift summary" emptyDescription="The drift endpoint did not return aggregate drift metadata." />
      </Section>

      <Section title="Attention queue" description="Highest-priority rows where live behavior is diverging or degrading.">
        <DataTable
          columns={["Strategy", "Symbol", "Family", "Status", "Research return", "Live PnL", "Recent avg", "Decay", "Best / worst regime"]}
          rows={topAttention.map((row) => [
            compactValue(row.name),
            compactValue(row.symbol),
            compactValue(row.family),
            compactValue(row.status),
            formatPercent(Number(row.research_return_pct ?? 0)),
            formatCurrency(Number(row.live_total_pnl ?? 0)),
            formatCurrency(Number(row.recent_avg_pnl ?? 0)),
            <StatusBadge key={`${String(row.name)}-decay`} label={row.decay_warning ? "Warning" : "Watch"} tone={row.decay_warning ? "critical" : "warning"} />,
            compactValue(`${row.best_regime ?? "?"} / ${row.worst_regime ?? "?"}`),
          ])}
          emptyTitle="No attention rows"
          emptyDescription="The current drift snapshot did not surface rows that crossed the simple warning heuristics."
        />
      </Section>

      <Section title="Drift leaderboard" description="Sorted rows with live-vs-research mismatch context for review and triage.">
        <DataTable
          columns={["Strategy", "Symbol", "Status", "Trades", "Research return", "Research sharpe", "Live PnL", "Recent avg", "Drift score", "Last update"]}
          rows={rows.map((row) => [
            compactValue(row.name),
            compactValue(row.symbol),
            compactValue(row.status),
            formatNumber(Number(row.live_trades ?? 0)),
            formatPercent(Number(row.research_return_pct ?? 0)),
            formatNumber(Number(row.research_sharpe ?? 0)),
            formatCurrency(Number(row.live_total_pnl ?? 0)),
            formatCurrency(Number(row.recent_avg_pnl ?? 0)),
            formatNumber(Number(row.drift_score ?? 0)),
            compactValue(formatDateTime(row.last_update)),
          ])}
          emptyTitle="No drift rows"
          emptyDescription="The drift adapter did not produce any rows for this snapshot."
        />
      </Section>
    </div>
  );
}
