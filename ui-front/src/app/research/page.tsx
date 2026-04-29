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
  ToolbarButton,
} from "@/components/dashboard";
import { useQuery } from "@/hooks/use-query";
import { uiApi } from "@/lib/api";
import { formatDateTime, formatNumber } from "@/lib/format";
import { toneFromMagnitude } from "@/lib/ui-state";

export default function ResearchPage() {
  const researchQuery = useQuery("research-summary", () => uiApi.researchSummary("XAUUSDm", "M15"), {
    refetchIntervalMs: 60_000,
  });

  const { data, error, loading, hasData, refreshing, refresh } = researchQuery;

  if (loading && !hasData) {
    return <LoadingState title="Loading research funnel" description="Collecting family-stage funnel data and top rejection reasons." />;
  }

  if (!data) {
    return <ErrorState error={error} resourceLabel="research summary" />;
  }

  const familyRows = Object.entries(data.families ?? {}).map(([family, payload]) => {
    const row = (payload as Record<string, unknown>) || {};
    const stages = (row.stages as Record<string, number>) || {};
    const skips = (row.skip_reasons as Record<string, number>) || {};
    return [
      family,
      formatNumber(stages.generated),
      formatNumber(stages.cheap_prescreen_pass),
      formatNumber(stages.backtest_pass),
      formatNumber(stages.wf_pass),
      formatNumber(stages.mc_pass),
      formatNumber(stages.accepted),
      Object.keys(skips).length ? Object.entries(skips).sort((a, b) => Number(b[1]) - Number(a[1]))[0]?.[0] ?? "-" : "-",
    ];
  });

  return (
    <div className="dashboard-stack">
      <PageHeader
        title="Research funnel"
        subtitle="Operator view of generation, prescreen, backtest, WF/MC, and acceptance flow by family for the current research stream."
        meta={`Snapshot ${formatDateTime(data.generated_at)} • ${data.symbol} ${data.timeframe}`}
        action={
          <div className="page-toolbar">
            <FreshnessBadge timestamp={data.generated_at} thresholds={{ warningMs: 15 * 60_000, criticalMs: 60 * 60_000 }} />
            <ToolbarButton label="Refresh now" onClick={() => void refresh()} busy={refreshing} tone="info" />
          </div>
        }
      />

      <section className="stats-grid">
        <StatCard label="Generated" value={formatNumber(data.funnel_totals.generated)} hint="Total candidates generated" tone="info" />
        <StatCard label="Cheap prescreen pass" value={formatNumber(data.funnel_totals.cheap_prescreen_pass)} hint="Candidates surviving cheap prescreen" tone="success" />
        <StatCard label="Backtest pass" value={formatNumber(data.funnel_totals.backtest_pass)} hint="Accepted by full evaluation layer" tone="success" />
        <StatCard label="Accepted" value={formatNumber(data.funnel_totals.accepted)} hint="Strategies admitted to pool flow" tone={toneFromMagnitude(Number(data.funnel_totals.accepted ?? 0), 1, 3)} />
      </section>

      <Section title="Funnel totals" description="Aggregate stage counts across all families in the current research artifact.">
        <KeyValueGrid data={data.funnel_totals} emptyTitle="No funnel totals" emptyDescription="The research summary did not provide aggregate stage counts." />
      </Section>

      <Section title="Top rejection reasons" description="Most common reasons strategies are dropping out of the research pipeline.">
        <KeyValueGrid data={data.rejection_totals} emptyTitle="No rejection totals" emptyDescription="The research summary did not provide rejection-reason counts." />
      </Section>

      <Section title="Family funnel table" description="Per-family progress from generated candidates through accepted entries.">
        <DataTable
          columns={["Family", "Generated", "Cheap pass", "Backtest pass", "WF pass", "MC pass", "Accepted", "Top rejection"]}
          rows={familyRows}
          emptyTitle="No family rows"
          emptyDescription="No family-stage rows are available in the current research artifact."
        />
      </Section>

      <Section title="Rejection samples" description="Example rejected strategies to make the funnel more diagnosable.">
        {Object.keys(data.top_rejection_samples ?? {}).length ? (
          <div className="detail-grid-2">
            {Object.entries(data.top_rejection_samples).map(([reason, samples]) => (
              <Section key={reason} title={reason} description="Example sample strategies from this rejection bucket.">
                <DataTable
                  columns={["Sample"]}
                  rows={(samples as string[]).map((sample) => [sample])}
                  emptyTitle="No samples"
                  emptyDescription="No sample strategies were stored for this rejection reason."
                />
              </Section>
            ))}
          </div>
        ) : (
          <EmptyState title="No rejection samples" description="The research artifact did not include sample strategy names for rejection buckets." />
        )}
      </Section>
    </div>
  );
}
