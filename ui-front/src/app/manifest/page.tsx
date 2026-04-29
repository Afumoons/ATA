"use client";

import { PageHeader } from "@/components/app-shell";
import {
  DataTable,
  EmptyState,
  ErrorState,
  FreshnessBadge,
  InlineNotice,
  LoadingState,
  Section,
  StatCard,
  StatusBadge,
  ToolbarButton,
} from "@/components/dashboard";
import { useQuery } from "@/hooks/use-query";
import { uiApi } from "@/lib/api";
import { compactValue, formatDateTime, formatNumber } from "@/lib/format";

export default function ManifestPage() {
  const { data, error, loading, hasData, refreshing, refresh } = useQuery("manifest", uiApi.manifest, {
    refetchIntervalMs: 90_000,
  });

  if (loading && !hasData) {
    return <LoadingState title="Loading manifest viewer" description="Reading the live manifest artifact and shaping it for operator inspection." />;
  }

  if (!data) {
    return <ErrorState error={error} resourceLabel="manifest payload" />;
  }

  const manifestLooksThin = !data.entry_count || !data.entries.length;

  return (
    <div className="dashboard-stack">
      <PageHeader
        title="Manifest viewer"
        subtitle="Operator-facing readout of the current manifest source, schema, artifact freshness, and the entries composing the active deployment set."
        meta={`Snapshot ${formatDateTime(data.generated_at)}`}
        action={
          <div className="page-toolbar">
            <FreshnessBadge timestamp={data.generated_at} thresholds={{ warningMs: 30 * 60_000, criticalMs: 2 * 60 * 60_000 }} />
            <ToolbarButton label="Refresh now" onClick={() => void refresh()} busy={refreshing} tone="info" />
          </div>
        }
      />

      {manifestLooksThin ? (
        <InlineNotice
          tone="warning"
          title="Manifest artifact is empty or missing"
          description="The route responded, but it does not currently expose a meaningful manifest entry set. Treat downstream deployment visibility as incomplete until the artifact repopulates."
        />
      ) : null}

      <section className="stats-grid">
        <StatCard label="Entries" value={formatNumber(data.entry_count)} hint="Manifest entry count" tone={data.entry_count ? "info" : "warning"} />
        <StatCard label="Schema version" value={formatNumber(data.schema_version)} hint="Declared manifest schema" tone="neutral" />
        <StatCard label="Source" value={data.source} hint="Manifest origin" tone="success" />
        <StatCard label="Preview rows" value={formatNumber(data.entries.length)} hint="Rows returned in this response" tone={data.entries.length ? "success" : "warning"} />
      </section>

      <Section
        title="Manifest context"
        description="Top-level manifest metadata for quick operator verification."
        action={<StatusBadge label={`Schema v${data.schema_version}`} tone="info" />}
      >
        <div className="badge-row">
          <StatusBadge label={`Source ${data.source}`} />
          <StatusBadge label={`Generated ${formatDateTime(data.generated_at)}`} tone="success" />
          <StatusBadge label={manifestLooksThin ? "Artifact thin" : "Artifact populated"} tone={manifestLooksThin ? "warning" : "success"} />
        </div>
      </Section>

      <Section title="Manifest entries" description="Read-only view of the returned manifest entries with operator-relevant fields placed first.">
        {data.entries.length ? (
          <DataTable
            columns={["Name", "Symbol", "Timeframe", "Status", "Family / motif", "Weight / score"]}
            rows={data.entries.map((entry) => [
              compactValue(entry.strategy_name ?? entry.name),
              compactValue(entry.symbol),
              compactValue(entry.timeframe),
              compactValue(entry.status ?? entry.live_status),
              compactValue(`${entry.family ?? "—"} / ${entry.motif ?? "—"}`),
              compactValue(entry.weight ?? entry.score ?? entry.rank),
            ])}
          />
        ) : (
          <EmptyState
            title="Manifest is empty"
            description="No manifest entries are currently available from the backend. This usually means the manifest artifact is missing, not rebuilt, or currently has zero deployable strategies."
            tone="warning"
            eyebrow="Deployment surface missing"
            meaning="Operators cannot trust this page as a representation of deployable strategies until the manifest repopulates."
            nextStep="Check whether the manifest artifact was rebuilt recently and whether the backend is pointing at the expected source file."
          />
        )}
      </Section>
    </div>
  );
}
