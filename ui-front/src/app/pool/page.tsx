"use client";

import { PageHeader } from "@/components/app-shell";
import { DataTable, ErrorState, KeyValueGrid, LoadingState, Section, StatCard } from "@/components/dashboard";
import { useQuery } from "@/hooks/use-query";
import { uiApi } from "@/lib/api";
import { formatDateTime, formatNumber } from "@/lib/format";

export default function PoolPage() {
  const { data, loading, error } = useQuery("pool-summary", uiApi.poolSummary);

  if (loading) return <LoadingState title="Loading pool overview" />;
  if (error || !data) return <ErrorState message={error ?? "Pool summary is unavailable."} />;

  return (
    <div className="dashboard-stack">
      <PageHeader
        title="Pool overview"
        subtitle="Inventory depth, slot concentration, and highest-ranked strategy records from the governed strategy pool."
        meta={`Snapshot ${formatDateTime(data.generated_at)}`}
      />

      <section className="stats-grid">
        <StatCard label="Total strategies" value={formatNumber(data.total)} hint="Pool inventory count" tone="info" />
        <StatCard label="Distinct slots" value={formatNumber(data.by_slot.length)} hint="Symbol/timeframe combinations" />
        <StatCard label="Top records" value={formatNumber(data.top_strategies.length)} hint="Returned by summary endpoint" tone="positive" />
        <StatCard label="Status buckets" value={formatNumber(Object.keys(data.status_counts).length)} hint="Current pool status families" tone="warning" />
      </section>

      <Section title="Pool status counts" description="How current pool inventory is distributed across workflow states.">
        <KeyValueGrid data={data.status_counts} />
      </Section>

      <Section title="Slot distribution" description="Volume concentration by symbol and timeframe.">
        <DataTable
          columns={["Symbol", "Timeframe", "Count"]}
          rows={data.by_slot.map((slot) => [slot.symbol, slot.timeframe, formatNumber(slot.count)])}
        />
      </Section>

      <Section title="Top strategy records" description="Best surfaced candidates from the backend summary feed.">
        <DataTable
          columns={["Name", "Symbol", "Timeframe", "Status", "Score"]}
          rows={data.top_strategies.map((strategy) => [
            strategy.name,
            strategy.symbol,
            strategy.timeframe,
            strategy.status,
            formatNumber(strategy.score),
          ])}
        />
      </Section>
    </div>
  );
}
