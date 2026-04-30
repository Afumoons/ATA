"use client";

import { PageHeader } from "@/components/app-shell";
import {
  DataTable,
  EmptyState,
  ErrorState,
  FreshnessBadge,
  InlineNotice,
  InsightCard,
  LoadingState,
  Section,
  StatCard,
  StatusBadge,
  ToolbarButton,
} from "@/components/dashboard";
import { useQuery } from "@/hooks/use-query";
import { uiApi } from "@/lib/api";
import { compactValue, formatDateTime, formatNumber, formatPercent } from "@/lib/format";

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
  const countBy = (resolver: (entry: Record<string, unknown>) => string) => {
    const counts = new Map<string, number>();
    for (const entry of data.entries) {
      const normalized = resolver(entry);
      counts.set(normalized, (counts.get(normalized) ?? 0) + 1);
    }
    return [...counts.entries()].sort((left, right) => right[1] - left[1]);
  };
  const statusCounts = countBy((entry) => {
    const rawValue = entry.status ?? entry.live_status;
    return typeof rawValue === "string" && rawValue.trim() ? rawValue.trim() : "Unknown";
  });
  const symbolCounts = countBy((entry) => {
    const rawValue = entry.symbol;
    return typeof rawValue === "string" && rawValue.trim() ? rawValue.trim() : "Unknown";
  });
  const familyCounts = countBy((entry) => {
    const rawValue = entry.family;
    return typeof rawValue === "string" && rawValue.trim() ? rawValue.trim() : "Unknown";
  });
  const slotCounts = countBy((entry) => {
    const symbol = typeof entry.symbol === "string" && entry.symbol.trim() ? entry.symbol.trim() : "Unknown";
    const timeframe = typeof entry.timeframe === "string" && entry.timeframe.trim() ? entry.timeframe.trim() : "Unknown";
    return `${symbol} / ${timeframe}`;
  });
  const topStatus = statusCounts[0];
  const topSymbol = symbolCounts[0];
  const topFamily = familyCounts[0];
  const topSlot = slotCounts[0];
  const secondSlot = slotCounts[1];
  const topStatusShare = data.entry_count > 0 && topStatus ? Number(topStatus[1]) / data.entry_count : 0;
  const topSymbolShare = data.entry_count > 0 && topSymbol ? Number(topSymbol[1]) / data.entry_count : 0;
  const topFamilyShare = data.entry_count > 0 && topFamily ? Number(topFamily[1]) / data.entry_count : 0;
  const topSlotShare = data.entry_count > 0 && topSlot ? Number(topSlot[1]) / data.entry_count : 0;

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

      <Section title="Deployment dossier" description="A faster read on whether the manifest looks usable, concentrated, and internally coherent before you scan the raw rows.">
        <div className="insight-grid">
          <InsightCard
            eyebrow="Artifact health"
            title={manifestLooksThin ? "Manifest visibility is thin" : "Manifest snapshot is populated"}
            description="This card tells you whether the manifest is acting like a real deployment surface or just a placeholder artifact read."
            tone={manifestLooksThin ? "warning" : "success"}
            badges={
              <>
                <StatusBadge label={`Schema v${data.schema_version}`} tone="info" />
                <StatusBadge label={`${formatNumber(data.entries.length)} preview rows`} tone={data.entries.length ? "success" : "warning"} />
              </>
            }
            metrics={[
              { label: "Entries", value: formatNumber(data.entry_count) },
              { label: "Returned rows", value: formatNumber(data.entries.length) },
              { label: "Source", value: data.source },
              { label: "Snapshot", value: formatDateTime(data.generated_at) },
            ]}
            footer={<p>{manifestLooksThin ? "The backend responded, but the manifest is too thin to trust as a deployment picture. Rebuild or repoint the artifact before using this page as truth." : "The manifest is populated enough to support composition checks here, then deeper strategy inspection on Pool and Drift."}</p>}
          />

          <InsightCard
            eyebrow="Workflow mix"
            title={topStatus ? `${topStatus[0]} leads the manifest` : "No status mix visible"}
            description="Status concentration shows whether deployment inventory is balanced across active lanes or quietly stacking into one posture."
            tone={topStatusShare >= 0.6 ? "warning" : topStatusShare >= 0.35 ? "info" : "success"}
            badges={topStatus ? <StatusBadge label={`${formatPercent(topStatusShare * 100)} of entries`} tone={topStatusShare >= 0.6 ? "warning" : topStatusShare >= 0.35 ? "info" : "success"} /> : null}
            metrics={[
              { label: "Top status", value: topStatus ? `${topStatus[0]} (${formatNumber(Number(topStatus[1]))})` : "None" },
              { label: "Distinct statuses", value: formatNumber(statusCounts.length) },
              { label: "Top symbol", value: topSymbol ? `${topSymbol[0]} (${formatNumber(Number(topSymbol[1]))})` : "None" },
              { label: "Top family", value: topFamily ? `${topFamily[0]} (${formatNumber(Number(topFamily[1]))})` : "None" },
            ]}
            footer={<p>{topStatus ? `${topStatus[0]} currently defines the manifest mood. If that lane is overcrowded, confirm on Pool and Governance whether the broader inventory is still balanced.` : "The current response does not expose a meaningful status mix for the manifest."}</p>}
          />

          <InsightCard
            eyebrow="Symbol focus"
            title={topSlot ? topSlot[0] : "No slot footprint"}
            description="Slot and symbol clustering make it obvious where the deployment set is leaning hardest before you inspect individual strategy rows."
            tone={topSlotShare >= 0.4 ? "warning" : topSlotShare >= 0.25 ? "info" : "success"}
            badges={topSlot ? <StatusBadge label={`${formatPercent(topSlotShare * 100)} of entries`} tone={topSlotShare >= 0.4 ? "warning" : topSlotShare >= 0.25 ? "info" : "success"} /> : null}
            metrics={[
              { label: "Top slot", value: topSlot ? `${topSlot[0]} (${formatNumber(Number(topSlot[1]))})` : "None" },
              { label: "Second slot", value: secondSlot ? `${secondSlot[0]} (${formatNumber(Number(secondSlot[1]))})` : "None" },
              { label: "Distinct symbols", value: formatNumber(symbolCounts.length) },
              { label: "Distinct slots", value: formatNumber(slotCounts.length) },
            ]}
            footer={<p>{topSlot ? `${topSlot[0]} is the heaviest deployment slot in the visible manifest rows. Cross-check Drift and Pool to make sure this density is intentional rather than silent overlap.` : "No symbol/timeframe mix was available to characterize deployment concentration."}</p>}
          />

          <InsightCard
            eyebrow="Family footprint"
            title={topFamily ? topFamily[0] : "No family signal"}
            description="Lineage concentration tells you whether the active deployment set is genuinely diversified or mostly repeating one research family."
            tone={topFamilyShare >= 0.35 ? "warning" : topFamilyShare >= 0.2 ? "info" : "success"}
            badges={topFamily ? <StatusBadge label={`${formatPercent(topFamilyShare * 100)} of entries`} tone={topFamilyShare >= 0.35 ? "warning" : topFamilyShare >= 0.2 ? "info" : "success"} /> : null}
            metrics={[
              { label: "Top family", value: topFamily ? `${topFamily[0]} (${formatNumber(Number(topFamily[1]))})` : "None" },
              { label: "Distinct families", value: formatNumber(familyCounts.length) },
              { label: "Top symbol share", value: topSymbol ? formatPercent(topSymbolShare * 100) : "—" },
              { label: "Operator read", value: topFamilyShare >= 0.35 ? "Watch duplication" : "Breadth still visible" },
            ]}
            footer={<p>{topFamily ? `${topFamily[0]} is the strongest lineage in the visible deployment set. If this footprint also dominates one symbol or slot, duplicate-risk pressure compounds quickly.` : "Family information is too thin to assess lineage concentration from this snapshot."}</p>}
          />
        </div>
      </Section>

      <Section title="Manifest entries" description="Read-only view of the returned manifest entries with operator-relevant fields grouped into more scannable deployment dossiers.">
        {data.entries.length ? (
          <DataTable
            columns={["Strategy", "Deployment lane", "Lineage", "Weight / score"]}
            rows={data.entries.map((entry) => {
              const strategyName = compactValue(entry.strategy_name ?? entry.name);
              const symbol = compactValue(entry.symbol);
              const timeframe = compactValue(entry.timeframe);
              const status = compactValue(entry.status ?? entry.live_status);
              const family = compactValue(entry.family);
              const motif = compactValue(entry.motif);
              const weight = compactValue(entry.weight ?? entry.score ?? entry.rank);
              return [
                <div className="table-stack" key={`${strategyName}-strategy`}>
                  <strong>{strategyName}</strong>
                  <span>{symbol} · {timeframe}</span>
                </div>,
                <div className="table-stack" key={`${strategyName}-lane`}>
                  <StatusBadge label={status} tone={status.toLowerCase().includes("active") ? "success" : status.toLowerCase().includes("disable") ? "warning" : "info"} />
                  <span>{symbol} deployment slot with {timeframe} timing.</span>
                </div>,
                <div className="table-stack" key={`${strategyName}-lineage`}>
                  <strong>{family}</strong>
                  <span>Motif {motif}</span>
                </div>,
                <div className="table-stack" key={`${strategyName}-weight`}>
                  <strong>{weight}</strong>
                  <span>{compactValue(entry.weight != null ? "Manifest weight" : entry.score != null ? "Strategy score" : "Rank hint")}</span>
                </div>,
              ];
            })}
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
