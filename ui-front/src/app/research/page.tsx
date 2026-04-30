"use client";

import { Suspense, useEffect, useMemo } from "react";
import { PageHeader } from "@/components/app-shell";
import {
  DataTable,
  EmptyState,
  ErrorState,
  FilterField,
  FilterSelect,
  FilterToolbar,
  FreshnessBadge,
  KeyValueGrid,
  LoadingState,
  QueryStateNotice,
  Section,
  StatCard,
  ToolbarButton,
} from "@/components/dashboard";
import { useQuery } from "@/hooks/use-query";
import { useUrlState } from "@/hooks/use-url-state";
import { uiApi } from "@/lib/api";
import { compactValue, formatDateTime, formatNumber, formatPercent } from "@/lib/format";
import { toneFromMagnitude } from "@/lib/ui-state";

const researchSortOptions = [
  { value: "accepted-desc", label: "Accepted highest" },
  { value: "conversion-desc", label: "Best conversion" },
  { value: "generated-desc", label: "Most generated" },
  { value: "rejections-desc", label: "Most rejected" },
  { value: "family-asc", label: "Family A-Z" },
] as const;

const funnelStageOrder = ["generated", "cheap_prescreen_pass", "backtest_pass", "wf_pass", "mc_pass", "accepted"] as const;

const funnelStageLabels: Record<(typeof funnelStageOrder)[number], string> = {
  generated: "Generated",
  cheap_prescreen_pass: "Cheap pass",
  backtest_pass: "Backtest pass",
  wf_pass: "WF pass",
  mc_pass: "MC pass",
  accepted: "Accepted",
};

function normalizeFilterValue(value: string) {
  return value === "__all__" ? "" : value;
}

function coerceNumber(value: unknown) {
  return typeof value === "number" ? value : Number(value ?? 0);
}

function formatDelta(value: number, suffix = "") {
  if (!Number.isFinite(value)) return `0${suffix}`;
  const rounded = Math.abs(value) >= 10 ? Math.round(value) : Math.round(value * 100) / 100;
  if (rounded === 0) return `0${suffix}`;
  return `${rounded > 0 ? "+" : ""}${rounded}${suffix}`;
}

type FamilyRow = {
  family: string;
  generated: number;
  cheapPass: number;
  backtestPass: number;
  wfPass: number;
  mcPass: number;
  accepted: number;
  rejectionCount: number;
  conversionPct: number;
  topRejection: string;
};

type ComparisonFamilyDelta = {
  family: string;
  generated_delta: number;
  accepted_delta: number;
  rejection_delta: number;
  conversion_pct_delta: number;
  current_conversion_pct: number;
  previous_conversion_pct: number;
  current_top_rejection: string;
  previous_top_rejection: string;
};

type FamilySkipReason = {
  reason: string;
  count: number;
  samples: string[];
};

type FamilySkipDrilldown = {
  family: string;
  generated: number;
  accepted: number;
  rejection_count: number;
  conversion_pct: number;
  top_rejection: string;
  reasons: FamilySkipReason[];
};

function ResearchPageContent() {
  const researchUrlDefaults = useMemo(() => ({
    symbol: "XAUUSDm",
    timeframe: "M15",
    family: "",
    sort: "accepted-desc",
  }), []);
  const { state: researchUrlState, setState: setResearchUrlState, resetState: resetResearchUrlState } = useUrlState(researchUrlDefaults);
  const symbol = researchUrlState.symbol;
  const timeframe = researchUrlState.timeframe;
  const familyFilter = researchUrlState.family;
  const sortPreset = researchUrlState.sort as (typeof researchSortOptions)[number]["value"];

  const researchQuery = useQuery(`research-summary:${symbol}:${timeframe}`, () => uiApi.researchSummary(symbol, timeframe), {
    refetchIntervalMs: 60_000,
  });

  const { data, error, loading, hasData, refreshing, refresh, lastSuccessAt } = researchQuery;
  const timeframesBySymbol = data?.available_filters?.timeframes_by_symbol ?? {};

  const availableTimeframes = useMemo(() => {
    const symbolSpecific = timeframesBySymbol[symbol] ?? [];
    return symbolSpecific.length ? symbolSpecific : (data?.available_filters?.timeframes ?? []);
  }, [data?.available_filters, symbol, timeframesBySymbol]);

  useEffect(() => {
    if (!availableTimeframes.length) return;
    if (!availableTimeframes.includes(timeframe)) {
      setResearchUrlState({ timeframe: availableTimeframes[0] });
    }
  }, [availableTimeframes, timeframe]);

  const familyRows = useMemo<FamilyRow[]>(() => {
    return Object.entries(data?.families ?? {}).map(([family, payload]) => {
      const row = (payload as Record<string, unknown>) || {};
      const stages = (row.stages as Record<string, number>) || {};
      const skips = (row.skip_reasons as Record<string, number>) || {};
      const generated = Number(stages.generated ?? 0);
      const accepted = Number(stages.accepted ?? 0);
      const rejectionCount = Object.values(skips).reduce((sum, value) => sum + Number(value ?? 0), 0);
      const conversionPct = generated > 0 ? (accepted / generated) * 100 : 0;
      return {
        family,
        generated,
        cheapPass: Number(stages.cheap_prescreen_pass ?? 0),
        backtestPass: Number(stages.backtest_pass ?? 0),
        wfPass: Number(stages.wf_pass ?? 0),
        mcPass: Number(stages.mc_pass ?? 0),
        accepted,
        rejectionCount,
        conversionPct,
        topRejection: Object.keys(skips).length ? Object.entries(skips).sort((a, b) => Number(b[1]) - Number(a[1]))[0]?.[0] ?? "-" : "-",
      };
    });
  }, [data?.families]);

  const familyOptions = useMemo(() => familyRows.map((row) => row.family).sort((left, right) => left.localeCompare(right)), [familyRows]);

  const filteredRows = useMemo(() => {
    return familyRows.filter((row) => (familyFilter ? row.family === familyFilter : true));
  }, [familyFilter, familyRows]);

  const sortedRows = useMemo(() => {
    const nextRows = [...filteredRows];
    nextRows.sort((left, right) => {
      if (sortPreset === "conversion-desc") {
        return right.conversionPct - left.conversionPct || right.accepted - left.accepted || right.generated - left.generated;
      }
      if (sortPreset === "generated-desc") {
        return right.generated - left.generated || right.accepted - left.accepted;
      }
      if (sortPreset === "rejections-desc") {
        return right.rejectionCount - left.rejectionCount || right.generated - left.generated;
      }
      if (sortPreset === "family-asc") {
        return left.family.localeCompare(right.family);
      }
      return right.accepted - left.accepted || right.conversionPct - left.conversionPct || right.generated - left.generated;
    });
    return nextRows;
  }, [filteredRows, sortPreset]);

  if (loading && !hasData) {
    return <LoadingState title="Loading research funnel" description="Collecting family-stage funnel data and top rejection reasons." />;
  }

  if (!data) {
    return <ErrorState error={error} resourceLabel="research summary" />;
  }

  const visibleGenerated = filteredRows.reduce((sum, row) => sum + row.generated, 0);
  const visibleAccepted = filteredRows.reduce((sum, row) => sum + row.accepted, 0);
  const visibleRejections = filteredRows.reduce((sum, row) => sum + row.rejectionCount, 0);
  const visibleConversionPct = visibleGenerated > 0 ? (visibleAccepted / visibleGenerated) * 100 : 0;
  const bestVisibleFamily = sortedRows[0]?.family ?? "—";
  const totalGenerated = coerceNumber(data.funnel_totals?.generated);
  const totalAccepted = coerceNumber(data.funnel_totals?.accepted);
  const totalConversionPct = totalGenerated > 0 ? (totalAccepted / totalGenerated) * 100 : 0;
  const maxVisibleStage = Math.max(...funnelStageOrder.map((stage) => coerceNumber(data.funnel_totals?.[stage])), 1);
  const comparison = (data.comparison as Record<string, unknown> | undefined) ?? {};
  const comparisonSummary = (comparison.summary as Record<string, unknown> | undefined) ?? {};
  const comparisonFamilyDeltas = ((comparison.family_deltas as ComparisonFamilyDelta[] | undefined) ?? []).filter((row) => {
    if (!familyFilter) return true;
    return row.family === familyFilter;
  });
  const familySkipDrilldown = ((data.family_skip_drilldown as FamilySkipDrilldown[] | undefined) ?? []).filter((row) => {
    if (!familyFilter) return true;
    return row.family === familyFilter;
  });
  const fragileFamilies = filteredRows
    .filter((row) => row.generated >= 3 && (row.accepted === 0 || row.conversionPct < 5 || row.rejectionCount >= row.generated))
    .sort((left, right) => left.conversionPct - right.conversionPct || right.generated - left.generated)
    .slice(0, 5);

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

      <QueryStateNotice error={error} refreshing={refreshing} hasData={hasData} resourceLabel="research summary" lastSuccessAt={lastSuccessAt} />

      <section className="stats-grid">
        <StatCard label="Generated" value={formatNumber(data.funnel_totals.generated)} hint="Total candidates generated" tone="info" />
        <StatCard label="Cheap prescreen pass" value={formatNumber(data.funnel_totals.cheap_prescreen_pass)} hint="Candidates surviving cheap prescreen" tone="success" />
        <StatCard label="Backtest pass" value={formatNumber(data.funnel_totals.backtest_pass)} hint="Accepted by full evaluation layer" tone="success" />
        <StatCard label="Accepted" value={formatNumber(data.funnel_totals.accepted)} hint="Strategies admitted to pool flow" tone={toneFromMagnitude(Number(data.funnel_totals.accepted ?? 0), 1, 3)} />
        <StatCard label="Visible families" value={formatNumber(filteredRows.length)} hint="Families after current filter" tone="info" />
        <StatCard label="Visible conversion" value={formatPercent(visibleConversionPct)} hint="Accepted ÷ generated for filtered rows" tone={toneFromMagnitude(visibleConversionPct, 5, 20)} />
        <StatCard label="Visible rejections" value={formatNumber(visibleRejections)} hint="Skipped or rejected rows inside current family filter" tone="warning" />
        <StatCard label="Top visible family" value={compactValue(bestVisibleFamily)} hint="Leading family under current sort" tone="info" />
      </section>

      <Section title="Research filters" description="Switch symbol/timeframe artifacts, narrow to one family, and reorder the funnel table by the most useful operator lens.">
        <FilterToolbar>
          <FilterField label="Symbol">
            <FilterSelect
            value={symbol}
            onChange={(event) => {
              const nextSymbol = event.target.value;
              const nextTimeframes = timeframesBySymbol[nextSymbol] ?? [];
              setResearchUrlState({
                symbol: nextSymbol,
                timeframe: nextTimeframes.length && !nextTimeframes.includes(timeframe) ? nextTimeframes[0] : timeframe,
              });
            }}
            >
              {(data.available_filters?.symbols ?? [symbol]).map((value) => <option key={value} value={value}>{value}</option>)}
            </FilterSelect>
          </FilterField>
          <FilterField label="Timeframe">
            <FilterSelect value={timeframe} onChange={(event) => setResearchUrlState({ timeframe: event.target.value })}>
              {(availableTimeframes.length ? availableTimeframes : [timeframe]).map((value) => <option key={value} value={value}>{value}</option>)}
            </FilterSelect>
          </FilterField>
          <FilterField label="Family">
            <FilterSelect value={familyFilter || "__all__"} onChange={(event) => setResearchUrlState({ family: normalizeFilterValue(event.target.value) })}>
              <option value="__all__">All families</option>
              {familyOptions.map((value) => <option key={value} value={value}>{value}</option>)}
            </FilterSelect>
          </FilterField>
          <FilterField label="Sort view">
            <FilterSelect value={sortPreset} onChange={(event) => setResearchUrlState({ sort: event.target.value as (typeof researchSortOptions)[number]["value"] })}>
              {researchSortOptions.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
            </FilterSelect>
          </FilterField>
          <ToolbarButton
            label="Reset filters"
            onClick={() => resetResearchUrlState()}
            tone="neutral"
          />
        </FilterToolbar>
      </Section>

      <Section title="Funnel totals" description="Aggregate stage counts across all families in the current research artifact.">
        <KeyValueGrid data={data.funnel_totals} emptyTitle="No funnel totals" emptyDescription="The research summary did not provide aggregate stage counts." />
      </Section>

      <Section title="Funnel shape" description="Stage-by-stage stacked bars make the current research throughput easier to scan than raw counts alone.">
        <div className="research-funnel-grid">
          {funnelStageOrder.map((stage) => {
            const value = coerceNumber(data.funnel_totals?.[stage]);
            const width = `${Math.max((value / maxVisibleStage) * 100, value > 0 ? 8 : 0)}%`;
            return (
              <div key={stage} className="research-funnel-card">
                <div className="research-funnel-topline">
                  <span>{funnelStageLabels[stage]}</span>
                  <strong>{formatNumber(value)}</strong>
                </div>
                <div className="research-funnel-track">
                  <div className="research-funnel-fill" style={{ width }} />
                </div>
                <p>{stage === "accepted" ? formatPercent(totalConversionPct) : `${formatPercent(totalGenerated > 0 ? (value / totalGenerated) * 100 : 0)} of generated`}</p>
              </div>
            );
          })}
        </div>
      </Section>

      <Section title="Since previous run" description="Batch-to-batch comparison against the latest older snapshot found for this symbol/timeframe.">
        {comparison.previous_generated_at ? (
          <div className="dashboard-stack">
            <div className="stats-grid">
              <StatCard label="Compared to" value={compactValue(String(comparison.label ?? "previous snapshot"))} hint={formatDateTime(comparison.previous_generated_at)} tone="info" />
              <StatCard label="Generated delta" value={formatDelta(coerceNumber(comparisonSummary.generated_delta))} hint="Current minus previous snapshot" tone={toneFromMagnitude(coerceNumber(comparisonSummary.generated_delta), 0, 5)} />
              <StatCard label="Accepted delta" value={formatDelta(coerceNumber(comparisonSummary.accepted_delta))} hint="Pool-ready candidates gained or lost" tone={toneFromMagnitude(coerceNumber(comparisonSummary.accepted_delta), 0, 2)} />
              <StatCard label="Conversion delta" value={formatDelta(coerceNumber(comparisonSummary.conversion_pct_delta), "%")} hint="Accepted ÷ generated shift" tone={toneFromMagnitude(coerceNumber(comparisonSummary.conversion_pct_delta), 0.5, 3)} />
            </div>
            <DataTable
              columns={["Family", "Generated Δ", "Accepted Δ", "Conversion Δ", "Rejections Δ", "Top rejection now", "Top rejection before"]}
              rows={comparisonFamilyDeltas.map((row) => [
                compactValue(row.family),
                formatDelta(coerceNumber(row.generated_delta)),
                formatDelta(coerceNumber(row.accepted_delta)),
                formatDelta(coerceNumber(row.conversion_pct_delta), "%"),
                formatDelta(coerceNumber(row.rejection_delta)),
                compactValue(row.current_top_rejection),
                compactValue(row.previous_top_rejection),
              ])}
              emptyTitle="No comparison rows"
              emptyDescription="No family-level deltas were available for the previous snapshot comparison."
            />
          </div>
        ) : (
          <EmptyState
            title="No previous snapshot"
            description="Only one research snapshot is available for this symbol/timeframe, so change tracking cannot be derived yet."
            tone="info"
            eyebrow="Research continuity"
            meaning="You can read the current funnel, but not whether throughput is improving or deteriorating versus the prior batch yet."
            nextStep="Wait for the next research artifact for this same symbol/timeframe to land, then re-open the delta table."
          />
        )}
      </Section>

      <Section title="Fragile families" description="Families with meaningful generation volume but weak conversion or heavy rejection pressure should get operator attention first.">
        <DataTable
          columns={["Family", "Generated", "Accepted", "Conversion", "Rejections", "Primary issue"]}
          rows={fragileFamilies.map((row) => [
            compactValue(row.family),
            formatNumber(row.generated),
            formatNumber(row.accepted),
            formatPercent(row.conversionPct),
            formatNumber(row.rejectionCount),
            compactValue(row.accepted === 0 ? "No accepted output" : row.topRejection),
          ])}
          emptyTitle="No fragile families"
          emptyDescription="No currently visible family meets the low-conversion or high-rejection attention threshold."
        />
      </Section>

      <Section title="Top rejection reasons" description="Most common reasons strategies are dropping out of the research pipeline.">
        <KeyValueGrid data={data.rejection_totals} emptyTitle="No rejection totals" emptyDescription="The research summary did not provide rejection-reason counts." />
      </Section>

      <Section title="Skip-reason drilldown" description="Per-family rejection mix with exact counts and example strategy names, so operators can see whether a family is blocked by saturation, prescreen quality, or duplicate pressure.">
        <DataTable
          columns={["Family", "Generated", "Accepted", "Conversion", "Skip count", "Top skip", "Reason breakdown"]}
          rows={familySkipDrilldown.map((row) => [
            compactValue(row.family),
            formatNumber(row.generated),
            formatNumber(row.accepted),
            formatPercent(row.conversion_pct),
            formatNumber(row.rejection_count),
            compactValue(row.top_rejection),
            row.reasons.length ? (
              <div className="space-y-2" key={`${row.family}-reasons`}>
                {row.reasons.map((reason) => (
                  <div key={`${row.family}-${reason.reason}`}>
                    <strong>{`${reason.reason} (${formatNumber(reason.count)})`}</strong>
                    <div className="text-xs text-muted-foreground">
                      {reason.samples.length ? `Examples: ${reason.samples.join(", ")}` : "No sample strategies stored for this skip reason."}
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              compactValue("No skip reasons")
            ),
          ])}
          emptyTitle="No skip drilldown rows"
          emptyDescription="The current filter has no family-level skip reasons with stored counts and examples."
        />
      </Section>

      <Section title="Family funnel table" description="Per-family progress from generated candidates through accepted entries, with client-side filtering and sorting for quick diagnosis.">
        <DataTable
          columns={["Family", "Generated", "Cheap pass", "Backtest pass", "WF pass", "MC pass", "Accepted", "Conversion", "Rejections", "Top rejection"]}
          rows={sortedRows.map((row) => [
            compactValue(row.family),
            formatNumber(row.generated),
            formatNumber(row.cheapPass),
            formatNumber(row.backtestPass),
            formatNumber(row.wfPass),
            formatNumber(row.mcPass),
            formatNumber(row.accepted),
            formatPercent(row.conversionPct),
            formatNumber(row.rejectionCount),
            compactValue(row.topRejection),
          ])}
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
          <EmptyState
            title="No rejection samples"
            description="The research artifact did not include sample strategy names for rejection buckets."
            tone="warning"
            eyebrow="Research evidence missing"
            meaning="Operators can still see rejection counts, but not concrete example strategies behind each failure bucket."
            nextStep="Use the skip-reason drilldown above for aggregate diagnosis until a richer sample-bearing artifact is generated."
          />
        )}
      </Section>
    </div>
  );
}

export default function ResearchPage() {
  return (
    <Suspense fallback={<LoadingState title="Loading research funnel" description="Restoring URL-driven operator filters." />}>
      <ResearchPageContent />
    </Suspense>
  );
}
