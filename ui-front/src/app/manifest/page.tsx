"use client";

import { PageHeader } from "@/components/app-shell";
import { DataTable, ErrorState, LoadingState, Section, StatCard, StatusBadge } from "@/components/dashboard";
import { useQuery } from "@/hooks/use-query";
import { uiApi } from "@/lib/api";
import { compactValue, formatDateTime, formatNumber } from "@/lib/format";

export default function ManifestPage() {
  const { data, loading, error } = useQuery("manifest", uiApi.manifest);

  if (loading) return <LoadingState title="Loading manifest viewer" />;
  if (error || !data) return <ErrorState message={error ?? "Manifest data is unavailable."} />;

  return (
    <div className="dashboard-stack">
      <PageHeader
        title="Manifest viewer"
        subtitle="Operator-facing readout of the current manifest source, schema, and selected entries composing the active deployment set."
        meta={`Snapshot ${formatDateTime(data.generated_at)}`}
      />

      <section className="stats-grid">
        <StatCard label="Entries" value={formatNumber(data.entry_count)} hint="Manifest entry count" tone="info" />
        <StatCard label="Schema version" value={formatNumber(data.schema_version)} hint="Declared manifest schema" />
        <StatCard label="Source" value={data.source} hint="Manifest origin" tone="positive" />
        <StatCard label="Preview rows" value={formatNumber(data.entries.length)} hint="Rows returned in this response" tone="warning" />
      </section>

      <Section
        title="Manifest context"
        description="Top-level manifest metadata for quick operator verification."
        action={<StatusBadge label={`Schema v${data.schema_version}`} tone="info" />}
      >
        <div className="badge-row">
          <StatusBadge label={`Source ${data.source}`} />
          <StatusBadge label={`Generated ${formatDateTime(data.generated_at)}`} tone="positive" />
        </div>
      </Section>

      <Section title="Manifest entries" description="Read-only view of the returned manifest entries with the most operator-relevant fields first.">
        <DataTable
          columns={["Name", "Symbol", "Timeframe", "Status", "Weight / score", "Notes"]}
          rows={data.entries.map((entry) => [
            compactValue(entry.strategy_name ?? entry.name),
            compactValue(entry.symbol),
            compactValue(entry.timeframe),
            compactValue(entry.status ?? entry.live_status),
            compactValue(entry.weight ?? entry.score ?? entry.rank),
            compactValue(entry.notes ?? entry.reason ?? entry.comment),
          ])}
        />
      </Section>
    </div>
  );
}
