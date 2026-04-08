"use client";

import { PageHeader } from "@/components/app-shell";
import { ErrorState, LoadingState, Section, StatCard, Timeline } from "@/components/dashboard";
import { useQuery } from "@/hooks/use-query";
import { uiApi } from "@/lib/api";
import { formatDateTime, formatNumber } from "@/lib/format";

export default function AuditPage() {
  const { data, loading, error } = useQuery("audit-timeline", () => uiApi.auditTimeline(120));

  if (loading) return <LoadingState title="Loading audit timeline" />;
  if (error || !data) return <ErrorState message={error ?? "Audit timeline is unavailable."} />;

  return (
    <div className="dashboard-stack">
      <PageHeader
        title="Audit timeline"
        subtitle="Chronological merged event feed for operator review, intended for fast anomaly scanning and trace reconstruction."
        meta={`Snapshot ${formatDateTime(data.generated_at)}`}
      />

      <section className="stats-grid">
        <StatCard label="Events" value={formatNumber(data.events.length)} hint="Timeline records returned" tone="info" />
        <StatCard label="Window" value="120" hint="Requested timeline limit" />
        <StatCard label="Latest snapshot" value={formatDateTime(data.generated_at)} hint="Server generation time" tone="positive" />
        <StatCard label="Feed mode" value="Merged" hint="Combined audit stream" tone="warning" />
      </section>

      <Section title="Timeline" description="Event-by-event audit feed with the most recent records first.">
        <Timeline items={data.events} />
      </Section>
    </div>
  );
}
