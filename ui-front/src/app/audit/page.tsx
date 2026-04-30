"use client";

import { useMemo, useState } from "react";
import { PageHeader } from "@/components/app-shell";
import { ErrorState, FilterField, FilterSelect, FilterToolbar, FreshnessBadge, LoadingState, Section, StatCard, Timeline, ToolbarButton } from "@/components/dashboard";
import { useQuery } from "@/hooks/use-query";
import { uiApi } from "@/lib/api";
import { formatDateTime, formatNumber } from "@/lib/format";
import { getEventStrategyName, getEventSymbol, getEventTimestamp } from "@/lib/ui-state";

const EMPTY_EVENTS: Array<Record<string, unknown>> = [];
const DATE_RANGE_OPTIONS = [
  { value: "all", label: "All time" },
  { value: "6h", label: "Last 6h" },
  { value: "24h", label: "Last 24h" },
  { value: "72h", label: "Last 72h" },
  { value: "7d", label: "Last 7d" },
] as const;

function dateRangeCutoff(value: (typeof DATE_RANGE_OPTIONS)[number]["value"]) {
  const now = Date.now();
  if (value === "6h") return now - 6 * 60 * 60_000;
  if (value === "24h") return now - 24 * 60 * 60_000;
  if (value === "72h") return now - 72 * 60 * 60_000;
  if (value === "7d") return now - 7 * 24 * 60 * 60_000;
  return null;
}

export default function AuditPage() {
  const [sourceFilter, setSourceFilter] = useState("all");
  const [strategyFilter, setStrategyFilter] = useState("all");
  const [symbolFilter, setSymbolFilter] = useState("all");
  const [dateRange, setDateRange] = useState<(typeof DATE_RANGE_OPTIONS)[number]["value"]>("24h");
  const [preset, setPreset] = useState<"all" | "attention" | "execution" | "pool">("all");
  const [expanded, setExpanded] = useState(false);
  const [showRaw, setShowRaw] = useState(false);

  const { data, error, loading, hasData, refreshing, refresh } = useQuery(
    "audit-timeline",
    () => uiApi.auditTimeline(120),
    { refetchIntervalMs: 60_000 },
  );

  const events = data?.events ?? EMPTY_EVENTS;

  const sourceOptions = Array.from(new Set(events.map((event) => String(event.source ?? "event")))).sort();
  const strategyOptions = Array.from(new Set(events.map((event) => getEventStrategyName(event)).filter(Boolean) as string[])).sort();
  const symbolOptions = Array.from(new Set(events.map((event) => getEventSymbol(event)).filter(Boolean) as string[])).sort();

  const filteredEvents = useMemo(() => {
    const cutoff = dateRangeCutoff(dateRange);
    return events.filter((event) => {
      const source = String(event.source ?? "event");
      const strategy = getEventStrategyName(event) ?? "";
      const symbol = getEventSymbol(event) ?? "";
      const timestamp = getEventTimestamp(event);

      if (preset === "attention") {
        const lowerSource = source.toLowerCase();
        const lowerReason = String(event.reason ?? event.type ?? event.event ?? "").toLowerCase();
        const matchesAttention = lowerSource.includes("unmatched") || lowerReason.includes("miss") || lowerReason.includes("fail");
        if (!matchesAttention) return false;
      }

      if (preset === "execution" && !String(event.source ?? "").toLowerCase().includes("trade")) return false;
      if (preset === "pool" && !String(event.source ?? "").toLowerCase().includes("pool")) return false;
      if (sourceFilter !== "all" && source !== sourceFilter) return false;
      if (strategyFilter !== "all" && strategy !== strategyFilter) return false;
      if (symbolFilter !== "all" && symbol !== symbolFilter) return false;
      if (cutoff != null) {
        const parsed = timestamp ? Date.parse(timestamp) : Number.NaN;
        if (!Number.isFinite(parsed) || parsed < cutoff) return false;
      }
      return true;
    });
  }, [dateRange, events, preset, sourceFilter, strategyFilter, symbolFilter]);

  if (loading && !hasData) {
    return <LoadingState title="Loading audit timeline" description="Merging recent pool-audit, unmatched-close, and trade-log events for operator filtering." />;
  }

  if (!data) {
    return <ErrorState error={error} resourceLabel="audit timeline" />;
  }

  return (
    <div className="dashboard-stack">
      <PageHeader
        title="Audit timeline"
        subtitle="Chronological merged event feed with operator filters for source, strategy, and symbol so anomaly scanning no longer requires immediate log spelunking."
        meta={`Snapshot ${formatDateTime(data.generated_at)}`}
        action={
          <div className="page-toolbar">
            <FreshnessBadge timestamp={data.generated_at} thresholds={{ warningMs: 10 * 60_000, criticalMs: 30 * 60_000 }} />
            <ToolbarButton label="Refresh now" onClick={() => void refresh()} busy={refreshing} tone="info" />
          </div>
        }
      />

      <section className="stats-grid">
        <StatCard label="Events" value={formatNumber(data.events.length)} hint="Timeline records returned" tone="info" />
        <StatCard label="Visible" value={formatNumber(filteredEvents.length)} hint="Rows after filters" tone="success" />
        <StatCard label="Latest snapshot" value={formatDateTime(data.generated_at)} hint="Server generation time" tone="neutral" />
        <StatCard label="Feed mode" value="Merged" hint="Combined audit stream" tone="warning" />
      </section>

      <Section title="Timeline controls" description="Slice the merged timeline to the operator lens you need right now.">
        <FilterToolbar>
          <div className="segmented-control">
            {[
              ["all", "All"],
              ["attention", "Attention"],
              ["execution", "Execution"],
              ["pool", "Pool audit"],
            ].map(([value, label]) => (
              <button
                key={value}
                type="button"
                className={`segmented-button${preset === value ? " is-active" : ""}`}
                onClick={() => setPreset(value as typeof preset)}
              >
                {label}
              </button>
            ))}
          </div>

          <FilterField label="Source">
            <FilterSelect value={sourceFilter} onChange={(event) => setSourceFilter(event.target.value)}>
              <option value="all">All sources</option>
              {sourceOptions.map((source) => (
                <option key={source} value={source}>
                  {source}
                </option>
              ))}
            </FilterSelect>
          </FilterField>

          <FilterField label="Strategy">
            <FilterSelect value={strategyFilter} onChange={(event) => setStrategyFilter(event.target.value)}>
              <option value="all">All strategies</option>
              {strategyOptions.map((strategy) => (
                <option key={strategy} value={strategy}>
                  {strategy}
                </option>
              ))}
            </FilterSelect>
          </FilterField>

          <FilterField label="Symbol">
            <FilterSelect value={symbolFilter} onChange={(event) => setSymbolFilter(event.target.value)}>
              <option value="all">All symbols</option>
              {symbolOptions.map((symbol) => (
                <option key={symbol} value={symbol}>
                  {symbol}
                </option>
              ))}
            </FilterSelect>
          </FilterField>

          <FilterField label="Date range">
            <FilterSelect value={dateRange} onChange={(event) => setDateRange(event.target.value as (typeof DATE_RANGE_OPTIONS)[number]["value"])}>
              {DATE_RANGE_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </FilterSelect>
          </FilterField>

          <div className="toggle-toolbar">
            <button type="button" className={`segmented-button${expanded ? " is-active" : ""}`} onClick={() => setExpanded((value) => !value)}>
              {expanded ? "Expanded rows" : "Compact rows"}
            </button>
            <button type="button" className={`segmented-button${showRaw ? " is-active" : ""}`} onClick={() => setShowRaw((value) => !value)}>
              {showRaw ? "Raw payload on" : "Raw payload off"}
            </button>
          </div>
        </FilterToolbar>
      </Section>

      <Section title="Timeline" description="Event-by-event audit feed with filterable source, strategy, and symbol context.">
        <Timeline items={filteredEvents} expanded={expanded} showRaw={showRaw} />
      </Section>
    </div>
  );
}
