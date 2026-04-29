"use client";

import { useEffect, useMemo, useState } from "react";
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
import { compactValue, formatDateTime, formatNumber, formatPercent } from "@/lib/format";
import { toneFromMagnitude } from "@/lib/ui-state";

const researchSortOptions = [
  { value: "accepted-desc", label: "Accepted highest" },
  { value: "conversion-desc", label: "Best conversion" },
  { value: "generated-desc", label: "Most generated" },
  { value: "rejections-desc", label: "Most rejected" },
  { value: "family-asc", label: "Family A-Z" },
] as const;

function normalizeFilterValue(value: string) {
  return value === "__all__" ? "" : value;
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

export default function ResearchPage() {
  const [symbol, setSymbol] = useState("XAUUSDm");
  const [timeframe, setTimeframe] = useState("M15");
  const [familyFilter, setFamilyFilter] = useState("");
  const [sortPreset, setSortPreset] = useState<(typeof researchSortOptions)[number]["value"]>("accepted-desc");

  const researchQuery = useQuery(`research-summary:${symbol}:${timeframe}`, () => uiApi.researchSummary(symbol, timeframe), {
    refetchIntervalMs: 60_000,
  });

  const { data, error, loading, hasData, refreshing, refresh } = researchQuery;
  const timeframesBySymbol = data?.available_filters?.timeframes_by_symbol ?? {};

  const availableTimeframes = useMemo(() => {
    const symbolSpecific = timeframesBySymbol[symbol] ?? [];
    return symbolSpecific.length ? symbolSpecific : (data?.available_filters?.timeframes ?? []);
  }, [data?.available_filters, symbol, timeframesBySymbol]);

  useEffect(() => {
    if (!availableTimeframes.length) return;
    if (!availableTimeframes.includes(timeframe)) {
      setTimeframe(availableTimeframes[0]);
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
        <StatCard label="Visible families" value={formatNumber(filteredRows.length)} hint="Families after current filter" tone="info" />
        <StatCard label="Visible conversion" value={formatPercent(visibleConversionPct)} hint="Accepted ÷ generated for filtered rows" tone={toneFromMagnitude(visibleConversionPct, 5, 20)} />
        <StatCard label="Visible rejections" value={formatNumber(visibleRejections)} hint="Skipped or rejected rows inside current family filter" tone="warning" />
        <StatCard label="Top visible family" value={compactValue(bestVisibleFamily)} hint="Leading family under current sort" tone="info" />
      </section>

      <Section title="Research filters" description="Switch symbol/timeframe artifacts, narrow to one family, and reorder the funnel table by the most useful operator lens.">
        <div className="flex flex-wrap gap-3">
          <select
            className="rounded-md border bg-background px-3 py-2 text-sm"
            value={symbol}
            onChange={(event) => {
              const nextSymbol = event.target.value;
              const nextTimeframes = timeframesBySymbol[nextSymbol] ?? [];
              setSymbol(nextSymbol);
              if (nextTimeframes.length && !nextTimeframes.includes(timeframe)) {
                setTimeframe(nextTimeframes[0]);
              }
            }}
          >
            {(data.available_filters?.symbols ?? [symbol]).map((value) => <option key={value} value={value}>{value}</option>)}
          </select>
          <select className="rounded-md border bg-background px-3 py-2 text-sm" value={timeframe} onChange={(event) => setTimeframe(event.target.value)}>
            {(availableTimeframes.length ? availableTimeframes : [timeframe]).map((value) => <option key={value} value={value}>{value}</option>)}
          </select>
          <select className="rounded-md border bg-background px-3 py-2 text-sm" value={familyFilter || "__all__"} onChange={(event) => setFamilyFilter(normalizeFilterValue(event.target.value))}>
            <option value="__all__">All families</option>
            {familyOptions.map((value) => <option key={value} value={value}>{value}</option>)}
          </select>
          <select className="rounded-md border bg-background px-3 py-2 text-sm" value={sortPreset} onChange={(event) => setSortPreset(event.target.value as (typeof researchSortOptions)[number]["value"])}>
            {researchSortOptions.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
          </select>
          <ToolbarButton
            label="Reset filters"
            onClick={() => {
              setSymbol("XAUUSDm");
              setTimeframe("M15");
              setFamilyFilter("");
              setSortPreset("accepted-desc");
            }}
            tone="neutral"
          />
        </div>
      </Section>

      <Section title="Funnel totals" description="Aggregate stage counts across all families in the current research artifact.">
        <KeyValueGrid data={data.funnel_totals} emptyTitle="No funnel totals" emptyDescription="The research summary did not provide aggregate stage counts." />
      </Section>

      <Section title="Top rejection reasons" description="Most common reasons strategies are dropping out of the research pipeline.">
        <KeyValueGrid data={data.rejection_totals} emptyTitle="No rejection totals" emptyDescription="The research summary did not provide rejection-reason counts." />
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
          <EmptyState title="No rejection samples" description="The research artifact did not include sample strategy names for rejection buckets." />
        )}
      </Section>
    </div>
  );
}
