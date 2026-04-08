"use client";

import { PageHeader } from "@/components/app-shell";
import {
  DataTable,
  ErrorState,
  KeyValueGrid,
  LoadingState,
  Section,
  StatCard,
  StatusBadge,
} from "@/components/dashboard";
import { useQuery } from "@/hooks/use-query";
import { uiApi } from "@/lib/api";
import { formatCurrency, formatDateTime, formatNumber } from "@/lib/format";

export default function OverviewPage() {
  const { data, loading, error } = useQuery("overview", uiApi.overview);

  if (loading) return <LoadingState title="Loading overview" />;
  if (error || !data) return <ErrorState message={error ?? "Overview data is unavailable."} />;

  return (
    <div className="dashboard-stack">
      <PageHeader
        title="Overview"
        subtitle="Operator-grade summary of equity posture, pool readiness, manifest pressure, and live slot concentration. Built for fast scanning, not spectacle."
        meta={`Snapshot ${formatDateTime(data.generated_at)}`}
      />

      <section className="stats-grid">
        <StatCard label="Equity" value={formatCurrency(data.equity_current)} hint="Current account equity" tone="info" />
        <StatCard label="Daily PnL" value={formatCurrency(data.daily_pnl)} hint="Realized + floating for the session" tone={(data.daily_pnl ?? 0) >= 0 ? "positive" : "danger"} />
        <StatCard label="Trades today" value={formatNumber(data.trades_today)} hint="Executed trades logged today" />
        <StatCard label="Manifest load" value={formatNumber(data.manifest_entry_count)} hint={`${formatNumber(data.strategy_index_entry_count)} indexed candidates`} tone="warning" />
      </section>

      <Section
        title="Session posture"
        description="Immediate risk posture and daily lock conditions for the active trading date."
        action={<StatusBadge label={data.locked_for_day ? "Day locked" : "Trading enabled"} tone={data.locked_for_day ? "warning" : "positive"} />}
      >
        <div className="badge-row">
          <StatusBadge label={`Live date ${data.live_state_date ?? "unknown"}`} tone="info" />
          <StatusBadge label={`Pool total ${formatNumber(data.pool_total)}`} />
          <StatusBadge label={`Live slots ${formatNumber(data.live_slots.length)}`} tone="positive" />
        </div>
      </Section>

      <Section title="Pool status mix" description="Distribution of inventory state across the current strategy pool.">
        <KeyValueGrid data={data.pool_status_counts} />
      </Section>

      <Section title="Live slot concentration" description="Where current live allocation is clustering by symbol and timeframe.">
        <DataTable
          columns={["Symbol", "Timeframe", "Count"]}
          rows={data.live_slots.map((slot) => [slot.symbol, slot.timeframe, formatNumber(slot.count)])}
        />
      </Section>

      <Section title="Diagnostics extract" description="Backend-provided overview diagnostics surfaced without reinterpretation.">
        <KeyValueGrid data={data.diagnostics} />
      </Section>
    </div>
  );
}
