"use client";

import { useMemo, useState } from "react";
import { PageHeader } from "@/components/app-shell";
import {
  DataTable,
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
import type { DriftSummaryRow, StatusTone } from "@/lib/types";

const severityTone: Record<string, StatusTone> = {
  healthy: "success",
  watch: "warning",
  drifting: "warning",
  broken: "critical",
};

const severityRank: Record<string, number> = {
  healthy: 0,
  watch: 1,
  drifting: 2,
  broken: 3,
};

const sortPresetOptions = [
  { value: "highest-drift", label: "Highest drift" },
  { value: "negative-recent-avg", label: "Negative recent avg" },
  { value: "most-live-trades", label: "Most live trades" },
  { value: "newest-warnings", label: "Newest warnings" },
] as const;

function normalizeFilterValue(value: string) {
  return value === "__all__" ? "" : value;
}

function severityBadge(value: string | null | undefined) {
  const label = value ? value[0].toUpperCase() + value.slice(1) : "Unknown";
  return <StatusBadge label={label} tone={severityTone[value ?? ""] ?? "neutral"} />;
}

function lastUpdateTimestamp(value: string | null | undefined) {
  if (!value) return 0;
  const parsed = Date.parse(value);
  return Number.isFinite(parsed) ? parsed : 0;
}

function RecentPnlSparkline({ values }: { values?: number[] | null }) {
  const sequence = (values ?? []).filter((value) => Number.isFinite(value));

  if (!sequence.length) {
    return <span className="text-xs text-muted-foreground">No recent sequence</span>;
  }

  if (sequence.length === 1) {
    const tone: StatusTone = sequence[0] >= 0 ? "success" : "critical";
    return <StatusBadge label={formatCurrency(sequence[0])} tone={tone} />;
  }

  const width = 120;
  const height = 36;
  const padding = 4;
  const minValue = Math.min(...sequence, 0);
  const maxValue = Math.max(...sequence, 0);
  const range = maxValue - minValue || 1;
  const zeroY = padding + ((maxValue - 0) / range) * (height - padding * 2);
  const points = sequence.map((value, index) => {
    const x = padding + (index / (sequence.length - 1)) * (width - padding * 2);
    const y = padding + ((maxValue - value) / range) * (height - padding * 2);
    return `${x},${y}`;
  }).join(" ");
  const stroke = sequence.at(-1)! >= 0 ? "var(--success)" : "var(--critical)";

  return (
    <div className="flex flex-col gap-1 min-w-[120px]">
      <svg viewBox={`0 0 ${width} ${height}`} className="h-9 w-[120px] overflow-visible">
        <line x1={padding} y1={zeroY} x2={width - padding} y2={zeroY} stroke="rgba(148, 163, 184, 0.35)" strokeDasharray="3 3" strokeWidth="1" />
        <polyline fill="none" points={points} stroke={stroke} strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
      <span className="text-[0.68rem] uppercase tracking-[0.14em] text-muted-foreground">
        {formatCurrency(sequence[0])} to {formatCurrency(sequence.at(-1))}
      </span>
    </div>
  );
}

export default function DriftPage() {
  const driftQuery = useQuery("drift-summary", uiApi.driftSummary, { refetchIntervalMs: 60_000 });
  const { data, error, loading, hasData, refreshing, refresh } = driftQuery;
  const [symbolFilter, setSymbolFilter] = useState("");
  const [familyFilter, setFamilyFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [severityFilter, setSeverityFilter] = useState("");
  const [sortPreset, setSortPreset] = useState<(typeof sortPresetOptions)[number]["value"]>("highest-drift");

  const filteredRows = useMemo(() => {
    return (data?.rows ?? []).filter((row) => {
      if (symbolFilter && row.symbol !== symbolFilter) return false;
      if (familyFilter && row.family !== familyFilter) return false;
      if (statusFilter && row.status !== statusFilter) return false;
      if (severityFilter && row.severity !== severityFilter) return false;
      return true;
    });
  }, [data?.rows, symbolFilter, familyFilter, statusFilter, severityFilter]);

  const sortedRows = useMemo(() => {
    const nextRows = [...filteredRows];
    nextRows.sort((left, right) => {
      if (sortPreset === "negative-recent-avg") {
        return Number(left.recent_avg_pnl ?? 0) - Number(right.recent_avg_pnl ?? 0) || Number(right.drift_score ?? 0) - Number(left.drift_score ?? 0);
      }
      if (sortPreset === "most-live-trades") {
        return Number(right.live_trades ?? 0) - Number(left.live_trades ?? 0) || Number(right.drift_score ?? 0) - Number(left.drift_score ?? 0);
      }
      if (sortPreset === "newest-warnings") {
        return (
          Number(Boolean(right.decay_warning)) - Number(Boolean(left.decay_warning)) ||
          (severityRank[right.severity ?? ""] ?? 0) - (severityRank[left.severity ?? ""] ?? 0) ||
          lastUpdateTimestamp(right.last_update) - lastUpdateTimestamp(left.last_update) ||
          Number(right.drift_score ?? 0) - Number(left.drift_score ?? 0)
        );
      }
      return (
        Number(right.drift_score ?? 0) - Number(left.drift_score ?? 0) ||
        (severityRank[right.severity ?? ""] ?? 0) - (severityRank[left.severity ?? ""] ?? 0) ||
        Number(right.live_trades ?? 0) - Number(left.live_trades ?? 0)
      );
    });
    return nextRows;
  }, [filteredRows, sortPreset]);

  if (loading && !hasData) {
    return <LoadingState title="Loading drift diagnostics" description="Collecting live-vs-research mismatch and decay-warning candidates." />;
  }

  if (!data) {
    return <ErrorState error={error} resourceLabel="drift summary" />;
  }

  const filterOptions = data.summary?.available_filters ?? {};
  const topAttention = sortedRows.filter((row) => row.severity === "drifting" || row.severity === "broken" || Boolean(row.decay_warning)).slice(0, 12);
  const severityCounts = data.summary?.severity_counts ?? {};

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
        <StatCard label="Visible rows" value={formatNumber(filteredRows.length)} hint="Rows after current filters" tone="info" />
        <StatCard label="Broken" value={formatNumber(Number(severityCounts.broken ?? 0))} hint="Highest-risk drift severity" tone="critical" />
        <StatCard label="Drifting" value={formatNumber(Number(severityCounts.drifting ?? 0))} hint="Negative or widening mismatch" tone="warning" />
      </section>

      <Section title="Drift filters" description="Slice the drift snapshot by symbol, family, lifecycle status, severity, and triage sort preset.">
        <div className="flex flex-wrap gap-3">
          <select className="rounded-md border bg-background px-3 py-2 text-sm" value={symbolFilter || "__all__"} onChange={(event) => setSymbolFilter(normalizeFilterValue(event.target.value))}>
            <option value="__all__">All symbols</option>
            {(filterOptions.symbols ?? []).map((value) => <option key={value} value={value}>{value}</option>)}
          </select>
          <select className="rounded-md border bg-background px-3 py-2 text-sm" value={familyFilter || "__all__"} onChange={(event) => setFamilyFilter(normalizeFilterValue(event.target.value))}>
            <option value="__all__">All families</option>
            {(filterOptions.families ?? []).map((value) => <option key={value} value={value}>{value}</option>)}
          </select>
          <select className="rounded-md border bg-background px-3 py-2 text-sm" value={statusFilter || "__all__"} onChange={(event) => setStatusFilter(normalizeFilterValue(event.target.value))}>
            <option value="__all__">All statuses</option>
            {(filterOptions.statuses ?? []).map((value) => <option key={value} value={value}>{value}</option>)}
          </select>
          <select className="rounded-md border bg-background px-3 py-2 text-sm" value={severityFilter || "__all__"} onChange={(event) => setSeverityFilter(normalizeFilterValue(event.target.value))}>
            <option value="__all__">All severities</option>
            {(filterOptions.severities ?? []).map((value) => <option key={value} value={value}>{value}</option>)}
          </select>
          <select className="rounded-md border bg-background px-3 py-2 text-sm" value={sortPreset} onChange={(event) => setSortPreset(event.target.value as (typeof sortPresetOptions)[number]["value"])}>
            {sortPresetOptions.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
          </select>
          <ToolbarButton
            label="Reset filters"
            onClick={() => {
              setSymbolFilter("");
              setFamilyFilter("");
              setStatusFilter("");
              setSeverityFilter("");
              setSortPreset("highest-drift");
            }}
            tone="neutral"
          />
        </div>
      </Section>

      <Section title="Drift summary" description="Compact aggregate statistics for the current drift snapshot.">
        <KeyValueGrid data={data.summary ?? {}} emptyTitle="No drift summary" emptyDescription="The drift endpoint did not return aggregate drift metadata." />
      </Section>

      <Section title="Attention queue" description="Highest-priority rows where live behavior is diverging or degrading.">
        <DataTable
          columns={["Strategy", "Symbol", "Family", "Status", "Severity", "Research return", "Live PnL", "Recent avg", "Recent sequence", "Decay", "Best / worst regime"]}
          rows={topAttention.map((row: DriftSummaryRow) => [
            compactValue(row.name),
            compactValue(row.symbol),
            compactValue(row.family),
            compactValue(row.status),
            severityBadge(row.severity),
            formatPercent(Number(row.research_return_pct ?? 0)),
            formatCurrency(Number(row.live_total_pnl ?? 0)),
            formatCurrency(Number(row.recent_avg_pnl ?? 0)),
            <RecentPnlSparkline key={`${String(row.name)}-attention-sequence`} values={row.recent_pnls} />,
            <StatusBadge key={`${String(row.name)}-decay`} label={row.decay_warning ? "Warning" : "Stable"} tone={row.decay_warning ? "critical" : "success"} />,
            compactValue(`${row.best_regime ?? "?"} / ${row.worst_regime ?? "?"}`),
          ])}
          emptyTitle="No attention rows"
          emptyDescription="No filtered rows currently cross the drift attention heuristics."
        />
      </Section>

      <Section title="Drift leaderboard" description="Sorted rows with live-vs-research mismatch context for review and triage.">
        <DataTable
          columns={["Strategy", "Symbol", "Family", "Status", "Severity", "Trades", "Research return", "Research sharpe", "Live PnL", "Recent avg", "Recent sequence", "Drift score", "Last update"]}
          rows={sortedRows.map((row: DriftSummaryRow) => [
            compactValue(row.name),
            compactValue(row.symbol),
            compactValue(row.family),
            compactValue(row.status),
            severityBadge(row.severity),
            formatNumber(Number(row.live_trades ?? 0)),
            formatPercent(Number(row.research_return_pct ?? 0)),
            formatNumber(Number(row.research_sharpe ?? 0)),
            formatCurrency(Number(row.live_total_pnl ?? 0)),
            formatCurrency(Number(row.recent_avg_pnl ?? 0)),
            <RecentPnlSparkline key={`${String(row.name)}-leaderboard-sequence`} values={row.recent_pnls} />,
            formatNumber(Number(row.drift_score ?? 0)),
            compactValue(formatDateTime(row.last_update)),
          ])}
          emptyTitle="No drift rows"
          emptyDescription="No rows match the current filter selection."
        />
      </Section>
    </div>
  );
}
