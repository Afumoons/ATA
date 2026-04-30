"use client";

import { Suspense, useMemo } from "react";
import { PageHeader } from "@/components/app-shell";
import {
  AttentionCard,
  EmptyState,
  ErrorState,
  FilterField,
  FilterSelect,
  FilterToolbar,
  FreshnessBadge,
  InsightCard,
  LoadingState,
  QueryStateNotice,
  Section,
  StatCard,
  StatusBadge,
  Timeline,
  ToolbarButton,
} from "@/components/dashboard";
import { useQuery } from "@/hooks/use-query";
import { useUrlState } from "@/hooks/use-url-state";
import { uiApi } from "@/lib/api";
import { formatDateTime, formatNumber, formatRelativeAge, prettifyKey, truncateMiddle } from "@/lib/format";
import { attentionToneForEvent, getEventStrategyName, getEventSymbol, getEventTimestamp, summarizeEvent } from "@/lib/ui-state";
import type { StatusTone } from "@/lib/types";

const EMPTY_EVENTS: Array<Record<string, unknown>> = [];
const DATE_RANGE_OPTIONS = [
  { value: "all", label: "All time" },
  { value: "6h", label: "Last 6h" },
  { value: "24h", label: "Last 24h" },
  { value: "72h", label: "Last 72h" },
  { value: "7d", label: "Last 7d" },
] as const;
const PRESET_META = {
  all: {
    label: "All events",
    eyebrow: "Merged feed",
    description: "Watching the full audit stream across pool, trade, and anomaly events.",
  },
  attention: {
    label: "Attention lens",
    eyebrow: "Operator triage",
    description: "Only rows with failure, mismatch, or missing-data language stay in focus.",
  },
  execution: {
    label: "Execution lens",
    eyebrow: "Trade runtime",
    description: "Filtering down to trade-linked evidence so runtime incidents read cleanly.",
  },
  pool: {
    label: "Pool audit lens",
    eyebrow: "Selection history",
    description: "Filtering down to pool posture and strategy-selection events.",
  },
} as const;
const ATTENTION_TONES: StatusTone[] = ["critical", "warning"];
const TONE_PRIORITY: Record<StatusTone, number> = {
  critical: 4,
  warning: 3,
  info: 2,
  success: 1,
  neutral: 0,
};

type AuditPreset = keyof typeof PRESET_META;

function dateRangeCutoff(value: (typeof DATE_RANGE_OPTIONS)[number]["value"]) {
  const now = Date.now();
  if (value === "6h") return now - 6 * 60 * 60_000;
  if (value === "24h") return now - 24 * 60 * 60_000;
  if (value === "72h") return now - 72 * 60 * 60_000;
  if (value === "7d") return now - 7 * 24 * 60 * 60_000;
  return null;
}

function getTopEntries(counts: Map<string, number>, limit = 3) {
  return Array.from(counts.entries())
    .sort((left, right) => right[1] - left[1] || left[0].localeCompare(right[0]))
    .slice(0, limit);
}

function AuditPageContent() {
  const auditUrlDefaults = useMemo(
    () => ({
      source: "all",
      strategy: "all",
      symbol: "all",
      range: "24h",
      preset: "all",
      expanded: "0",
      raw: "0",
    }),
    [],
  );
  const { state: auditUrlState, setState: setAuditUrlState } = useUrlState(auditUrlDefaults);
  const sourceFilter = auditUrlState.source;
  const strategyFilter = auditUrlState.strategy;
  const symbolFilter = auditUrlState.symbol;
  const dateRange = auditUrlState.range as (typeof DATE_RANGE_OPTIONS)[number]["value"];
  const preset = auditUrlState.preset as AuditPreset;
  const expanded = auditUrlState.expanded === "1";
  const showRaw = auditUrlState.raw === "1";

  const { data, error, loading, hasData, refreshing, refresh, lastSuccessAt } = useQuery(
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

  const auditSummary = useMemo(() => {
    const toneCounts = new Map<StatusTone, number>();
    const sourceCounts = new Map<string, number>();
    const strategyCounts = new Map<string, number>();
    const symbolCounts = new Map<string, number>();
    const sortedEvents = [...filteredEvents].sort((left, right) => {
      const leftTime = Date.parse(String(getEventTimestamp(left) ?? ""));
      const rightTime = Date.parse(String(getEventTimestamp(right) ?? ""));
      return (Number.isFinite(rightTime) ? rightTime : 0) - (Number.isFinite(leftTime) ? leftTime : 0);
    });

    for (const event of sortedEvents) {
      const tone = attentionToneForEvent(event);
      toneCounts.set(tone, (toneCounts.get(tone) ?? 0) + 1);

      const source = String(event.source ?? "event");
      sourceCounts.set(source, (sourceCounts.get(source) ?? 0) + 1);

      const strategy = getEventStrategyName(event);
      if (strategy) strategyCounts.set(strategy, (strategyCounts.get(strategy) ?? 0) + 1);

      const symbol = getEventSymbol(event);
      if (symbol) symbolCounts.set(symbol, (symbolCounts.get(symbol) ?? 0) + 1);
    }

    const attentionEvents = sortedEvents.filter((event) => ATTENTION_TONES.includes(attentionToneForEvent(event)));
    const highestTone = Array.from(toneCounts.entries()).sort((left, right) => right[1] - left[1] || TONE_PRIORITY[right[0]] - TONE_PRIORITY[left[0]])[0]?.[0] ?? "neutral";

    return {
      sortedEvents,
      attentionEvents,
      latestEvent: sortedEvents[0] ?? null,
      latestAttentionEvent: attentionEvents[0] ?? null,
      highestTone,
      toneCounts,
      topSources: getTopEntries(sourceCounts),
      topStrategies: getTopEntries(strategyCounts),
      topSymbols: getTopEntries(symbolCounts),
    };
  }, [filteredEvents]);

  if (loading && !hasData) {
    return <LoadingState title="Loading audit timeline" description="Merging recent pool-audit, unmatched-close, and trade-log events for operator filtering." />;
  }

  if (!data) {
    return <ErrorState error={error} resourceLabel="audit timeline" />;
  }

  const presetMeta = PRESET_META[preset];
  const criticalCount = auditSummary.toneCounts.get("critical") ?? 0;
  const warningCount = auditSummary.toneCounts.get("warning") ?? 0;
  const infoCount = auditSummary.toneCounts.get("info") ?? 0;
  const latestAttentionEvent = auditSummary.latestAttentionEvent;
  const latestEvent = auditSummary.latestEvent;

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

      <QueryStateNotice error={error} refreshing={refreshing} hasData={hasData} resourceLabel="audit timeline" lastSuccessAt={lastSuccessAt} />

      <section className="stats-grid">
        <StatCard label="Events" value={formatNumber(data.events.length)} hint="Timeline records returned" tone="info" />
        <StatCard label="Visible" value={formatNumber(filteredEvents.length)} hint="Rows after filters" tone="success" />
        <StatCard label="Priority rows" value={formatNumber(criticalCount + warningCount)} hint="Critical + warning events in lens" tone={criticalCount ? "critical" : warningCount ? "warning" : "neutral"} />
        <StatCard label="Lens" value={presetMeta.label} hint={DATE_RANGE_OPTIONS.find((option) => option.value === dateRange)?.label ?? "Current range"} tone={auditSummary.highestTone} />
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
                onClick={() => setAuditUrlState({ preset: value as AuditPreset })}
              >
                {label}
              </button>
            ))}
          </div>

          <FilterField label="Source">
            <FilterSelect value={sourceFilter} onChange={(event) => setAuditUrlState({ source: event.target.value })}>
              <option value="all">All sources</option>
              {sourceOptions.map((source) => (
                <option key={source} value={source}>
                  {source}
                </option>
              ))}
            </FilterSelect>
          </FilterField>

          <FilterField label="Strategy">
            <FilterSelect value={strategyFilter} onChange={(event) => setAuditUrlState({ strategy: event.target.value })}>
              <option value="all">All strategies</option>
              {strategyOptions.map((strategy) => (
                <option key={strategy} value={strategy}>
                  {strategy}
                </option>
              ))}
            </FilterSelect>
          </FilterField>

          <FilterField label="Symbol">
            <FilterSelect value={symbolFilter} onChange={(event) => setAuditUrlState({ symbol: event.target.value })}>
              <option value="all">All symbols</option>
              {symbolOptions.map((symbol) => (
                <option key={symbol} value={symbol}>
                  {symbol}
                </option>
              ))}
            </FilterSelect>
          </FilterField>

          <FilterField label="Date range">
            <FilterSelect value={dateRange} onChange={(event) => setAuditUrlState({ range: event.target.value as (typeof DATE_RANGE_OPTIONS)[number]["value"] })}>
              {DATE_RANGE_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </FilterSelect>
          </FilterField>

          <div className="toggle-toolbar">
            <button type="button" className={`segmented-button${expanded ? " is-active" : ""}`} onClick={() => setAuditUrlState({ expanded: expanded ? "0" : "1" })}>
              {expanded ? "Expanded rows" : "Compact rows"}
            </button>
            <button type="button" className={`segmented-button${showRaw ? " is-active" : ""}`} onClick={() => setAuditUrlState({ raw: showRaw ? "0" : "1" })}>
              {showRaw ? "Raw payload on" : "Raw payload off"}
            </button>
          </div>
        </FilterToolbar>
      </Section>

      <Section title="Operator brief" description="Translate the current filter lens into the fastest read on pressure, freshness, and where to drill next.">
        <div className="insight-grid">
          <InsightCard
            eyebrow={presetMeta.eyebrow}
            title={presetMeta.label}
            description={presetMeta.description}
            tone={auditSummary.highestTone}
            badges={<StatusBadge label={`${formatNumber(filteredEvents.length)} visible`} tone="info" />}
            metrics={[
              { label: "Critical", value: formatNumber(criticalCount) },
              { label: "Warning", value: formatNumber(warningCount) },
              { label: "Informational", value: formatNumber(infoCount) },
            ]}
            footer={
              <span>
                Filters: {sourceFilter === "all" ? "all sources" : sourceFilter}, {strategyFilter === "all" ? "all strategies" : truncateMiddle(strategyFilter, 36)}, {symbolFilter === "all" ? "all symbols" : symbolFilter}.
              </span>
            }
          />

          <InsightCard
            eyebrow="Latest event"
            title={latestEvent ? summarizeEvent(latestEvent) : "No event in current lens"}
            description={
              latestEvent
                ? `Newest row landed ${formatRelativeAge(getEventTimestamp(latestEvent))} and keeps the ledger anchored to the latest audit evidence.`
                : "There is no matching event inside the current filter combination."
            }
            tone={latestEvent ? attentionToneForEvent(latestEvent) : "neutral"}
            metrics={latestEvent ? [{ label: "Timestamp", value: formatDateTime(getEventTimestamp(latestEvent)) }] : undefined}
            footer={latestEvent ? <span>{String(latestEvent.source ?? "event")}</span> : undefined}
          />

          <InsightCard
            eyebrow="Escalation check"
            title={latestAttentionEvent ? summarizeEvent(latestAttentionEvent) : "No high-signal incident in current lens"}
            description={
              latestAttentionEvent
                ? `Latest warning/critical row appeared ${formatRelativeAge(getEventTimestamp(latestAttentionEvent))}, so this is the fastest incident to inspect before dropping into the raw ledger.`
                : "Current lens does not contain warning or critical events, so the merged feed looks calm right now."
            }
            tone={latestAttentionEvent ? attentionToneForEvent(latestAttentionEvent) : "success"}
            metrics={latestAttentionEvent ? [{ label: "Severity", value: prettifyKey(attentionToneForEvent(latestAttentionEvent)) }] : undefined}
            footer={latestAttentionEvent ? <span>{truncateMiddle(String(latestAttentionEvent.reason ?? latestAttentionEvent.type ?? latestAttentionEvent.event ?? "No explicit reason"), 84)}</span> : undefined}
          />
        </div>
      </Section>

      <Section title="Attention lanes" description="See whether the current lens is dominated by hard failures, soft degradation, or routine telemetry before reading row by row.">
        <div className="attention-grid cols-3">
          <AttentionCard
            label="Critical incidents"
            value={formatNumber(criticalCount)}
            detail={criticalCount ? "Failures, missed pairings, or broken-path language are present in the filtered feed." : "No hard-failure language is visible in the current lens."}
            tone={criticalCount ? "critical" : "success"}
          />
          <AttentionCard
            label="Watchlist drift"
            value={formatNumber(warningCount)}
            detail={warningCount ? "Negative PnL or softer anomaly rows still need human judgement before they escalate." : "No softer warning rows are visible in the current lens."}
            tone={warningCount ? "warning" : "success"}
          />
          <AttentionCard
            label="Routine telemetry"
            value={formatNumber(infoCount)}
            detail={infoCount ? "Trade or pool audit rows are still flowing, so the feed retains operator context around the incidents." : "The current lens is almost entirely focused on incidents rather than routine feed context."}
            tone={infoCount ? "info" : "neutral"}
          />
        </div>
      </Section>

      <Section title="Hotspots" description="Top recurring sources, strategies, and symbols in the current filter lens so the operator can jump straight to repetition patterns.">
        <div className="insight-grid">
          <InsightCard
            eyebrow="Source concentration"
            title={auditSummary.topSources[0] ? prettifyKey(auditSummary.topSources[0][0]) : "No source concentration yet"}
            description="Which event source is dominating this lens right now."
            tone={auditSummary.topSources[0] ? "info" : "neutral"}
            metrics={auditSummary.topSources.map(([label, count]) => ({ label: prettifyKey(label), value: formatNumber(count) }))}
          />

          <InsightCard
            eyebrow="Strategy hotspot"
            title={auditSummary.topStrategies[0]?.[0] ?? "No named strategy in current lens"}
            description="Repeated strategy mentions usually signal the fastest place to inspect for audit repetition or recurring execution friction."
            tone={auditSummary.topStrategies[0] ? "warning" : "neutral"}
            metrics={auditSummary.topStrategies.map(([label, count]) => ({ label: truncateMiddle(label, 28), value: formatNumber(count) }))}
          />

          <InsightCard
            eyebrow="Symbol hotspot"
            title={auditSummary.topSymbols[0]?.[0] ?? "No symbol emphasis in current lens"}
            description="Repeated symbol mentions help separate single-market issues from broader system behaviour."
            tone={auditSummary.topSymbols[0] ? "info" : "neutral"}
            metrics={auditSummary.topSymbols.map(([label, count]) => ({ label, value: formatNumber(count) }))}
          />
        </div>
      </Section>

      <Section title="Raw timeline ledger" description="The full event-by-event feed stays below once the briefing cards have pointed you at the most relevant lane.">
        {filteredEvents.length ? (
          <Timeline items={filteredEvents} expanded={expanded} showRaw={showRaw} />
        ) : (
          <EmptyState
            title="No audit rows match this lens"
            description="The current filter combination removes every event from the merged audit feed."
            eyebrow="Filtered to zero"
            meaning="This is usually a filter mismatch rather than a silent system failure."
            nextStep="Relax source, strategy, symbol, or time-range filters to repopulate the timeline ledger."
          />
        )}
      </Section>
    </div>
  );
}

export default function AuditPage() {
  return (
    <Suspense fallback={<LoadingState title="Loading audit timeline" description="Restoring URL-driven operator filters." />}>
      <AuditPageContent />
    </Suspense>
  );
}
