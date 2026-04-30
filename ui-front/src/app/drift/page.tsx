"use client";

import { Suspense, useMemo } from "react";
import { PageHeader } from "@/components/app-shell";
import {
  AttentionCard,
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
  StatusBadge,
  ToolbarButton,
} from "@/components/dashboard";
import { useQuery } from "@/hooks/use-query";
import { useUrlState } from "@/hooks/use-url-state";
import { uiApi } from "@/lib/api";
import { compactValue, formatCurrency, formatDateTime, formatNumber, formatPercent, formatRelativeAge } from "@/lib/format";
import type { DriftSummaryRow, StatusTone } from "@/lib/types";

const severityTone: Record<string, StatusTone> = {
  healthy: "success",
  watch: "warning",
  drifting: "warning",
  broken: "critical",
};

const severityRank: Record<string, number> = {
  healthy: 0,
  watch: 1,
  drifting: 2,
  broken: 3,
};

const regimeAlignmentTone: Record<string, StatusTone> = {
  aligned: "success",
  mismatch: "critical",
  insufficient_live_data: "warning",
  unknown: "neutral",
};

const regimeAlignmentLabel: Record<string, string> = {
  aligned: "Aligned",
  mismatch: "Mismatch",
  insufficient_live_data: "Thin live data",
  unknown: "Unknown",
};

const severityLabel: Record<string, string> = {
  healthy: "Stable edge",
  watch: "Watch drift",
  drifting: "Drifting edge",
  broken: "Broken thesis",
};

const severityNarrative: Record<string, string> = {
  healthy: "Live behavior is still reading close to the research thesis, so operator effort can stay elsewhere.",
  watch: "Early mismatch is visible, but it has not stacked into a full breakdown yet.",
  drifting: "Live results are leaning away from the research edge and deserve a near-term read.",
  broken: "The live thesis is no longer matching research expectations and should be treated as an active incident.",
};

const sortPresetOptions = [
  { value: "highest-drift", label: "Highest drift" },
  { value: "negative-recent-avg", label: "Negative recent avg" },
  { value: "most-live-trades", label: "Most live trades" },
  { value: "newest-warnings", label: "Newest warnings" },
] as const;

const anomalyLabel: Record<string, string> = {
  unmatched_close: "Unmatched close",
  missing_live_stats: "Missing live stats",
  stale_update: "Stale update",
  unmatched_without_strategy: "Unmatched without strategy",
};

function normalizeFilterValue(value: string) {
  return value === "__all__" ? "" : value;
}

function severityBadge(value: string | null | undefined) {
  const key = value ?? "";
  return <StatusBadge label={severityLabel[key] ?? "Unknown"} tone={severityTone[key] ?? "neutral"} />;
}

function lastUpdateTimestamp(value: string | null | undefined) {
  if (!value) return 0;
  const parsed = Date.parse(value);
  return Number.isFinite(parsed) ? parsed : 0;
}

function regimeAlignmentBadge(value: DriftSummaryRow["regime_alignment"]) {
  const key = value ?? "unknown";
  return <StatusBadge label={regimeAlignmentLabel[key] ?? regimeAlignmentLabel.unknown} tone={regimeAlignmentTone[key] ?? "neutral"} />;
}

function regimePairValue(row: DriftSummaryRow) {
  return compactValue(`${row.best_regime ?? "?"} → ${row.live_observed_regime ?? "?"}`);
}

function anomalySummary(row: DriftSummaryRow) {
  const anomalies = (row.unresolved_anomalies ?? []).map((value) => anomalyLabel[value] ?? value);
  if (!anomalies.length) {
    return <span className="text-xs text-muted-foreground">None</span>;
  }
  return compactValue(anomalies.join(", "));
}

function reviewReasonSummary(row: DriftSummaryRow) {
  const reasons = row.review_reasons ?? [];
  if (!reasons.length) {
    return <span className="text-xs text-muted-foreground">No manual review flag</span>;
  }
  return compactValue(reasons.join(" • "));
}

function buildDriftHeadline(row: DriftSummaryRow) {
  if (row.severity === "broken") {
    return "Treat as an active incident";
  }
  if (row.severity === "drifting") {
    return "Momentum is bending away from research";
  }
  if (row.regime_alignment === "mismatch") {
    return "Edge is showing up in the wrong regime";
  }
  if (row.decay_warning_count && row.decay_warning_count >= 2) {
    return "Repeated decay warnings are stacking up";
  }
  return "Monitor for further divergence";
}

function buildDriftNarrative(row: DriftSummaryRow) {
  const segments: string[] = [];
  if (row.recent_avg_pnl != null) {
    segments.push(`Recent average ${formatCurrency(Number(row.recent_avg_pnl))}.`);
  }
  if (row.regime_alignment === "mismatch") {
    segments.push(`Research prefers ${row.best_regime ?? "unknown"}, while live is reading ${row.live_observed_regime ?? "unknown"}.`);
  }
  if ((row.unresolved_anomalies ?? []).length) {
    segments.push(`Unresolved anomalies: ${(row.unresolved_anomalies ?? []).map((value) => anomalyLabel[value] ?? value).join(", ")}.`);
  }
  if (!segments.length && row.latest_decay_reason) {
    segments.push(row.latest_decay_reason);
  }
  return segments.join(" ") || "This row is elevated because live behavior no longer cleanly matches the original research posture.";
}

function driftPriority(row: DriftSummaryRow) {
  return (
    (severityRank[row.severity ?? ""] ?? 0) * 100 +
    Number(Boolean(row.regime_alignment === "mismatch")) * 20 +
    Number(row.decay_warning_count ?? 0) * 6 +
    Number(row.unresolved_anomaly_count ?? 0) * 8 +
    Number(Boolean(row.decay_warning)) * 4 +
    Math.max(0, Number(row.drift_score ?? 0))
  );
}

function RecentPnlSparkline({ values }: { values?: number[] | null }) {
  const sequence = (values ?? []).filter((value) => Number.isFinite(value));

  if (!sequence.length) {
    return <span className="text-xs text-muted-foreground">No recent sequence</span>;
  }

  if (sequence.length === 1) {
    const tone: StatusTone = sequence[0] >= 0 ? "success" : "critical";
    return <StatusBadge label={formatCurrency(sequence[0])} tone={tone} />;
  }

  const width = 120;
  const height = 36;
  const padding = 4;
  const minValue = Math.min(...sequence, 0);
  const maxValue = Math.max(...sequence, 0);
  const range = maxValue - minValue || 1;
  const zeroY = padding + ((maxValue - 0) / range) * (height - padding * 2);
  const points = sequence.map((value, index) => {
    const x = padding + (index / (sequence.length - 1)) * (width - padding * 2);
    const y = padding + ((maxValue - value) / range) * (height - padding * 2);
    return `${x},${y}`;
  }).join(" ");
  const stroke = sequence.at(-1)! >= 0 ? "var(--success)" : "var(--critical)";

  return (
    <div className="flex min-w-[120px] flex-col gap-1">
      <svg viewBox={`0 0 ${width} ${height}`} className="h-9 w-[120px] overflow-visible">
        <line x1={padding} y1={zeroY} x2={width - padding} y2={zeroY} stroke="rgba(148, 163, 184, 0.35)" strokeDasharray="3 3" strokeWidth="1" />
        <polyline fill="none" points={points} stroke={stroke} strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
      <span className="text-[0.68rem] uppercase tracking-[0.14em] text-muted-foreground">
        {formatCurrency(sequence[0])} to {formatCurrency(sequence.at(-1))}
      </span>
    </div>
  );
}

function DriftSignalCard({ row }: { row: DriftSummaryRow }) {
  const tone = severityTone[row.severity ?? ""] ?? "neutral";

  return (
    <article className={`drift-signal-card tone-${tone}`}>
      <div className="drift-signal-header">
        <div className="drift-signal-heading">
          <span className="drift-signal-eyebrow">{row.symbol ?? "Unknown symbol"} · {row.family ?? "Unknown family"}</span>
          <h4>{row.name}</h4>
          <p>{buildDriftHeadline(row)}</p>
        </div>
        <div className="drift-signal-badges">
          {severityBadge(row.severity)}
          {regimeAlignmentBadge(row.regime_alignment)}
        </div>
      </div>

      <div className="drift-chip-row">
        <span className="drift-chip">Status {compactValue(row.status)}</span>
        <span className="drift-chip">Drift {formatNumber(Number(row.drift_score ?? 0))}</span>
        <span className="drift-chip">Decay {formatNumber(Number(row.decay_warning_count ?? 0))}</span>
        <span className="drift-chip">Updated {formatRelativeAge(row.last_update)}</span>
      </div>

      <div className="drift-signal-metrics">
        <div>
          <span>Live PnL</span>
          <strong>{formatCurrency(Number(row.live_total_pnl ?? 0))}</strong>
        </div>
        <div>
          <span>Recent avg</span>
          <strong>{formatCurrency(Number(row.recent_avg_pnl ?? 0))}</strong>
        </div>
        <div>
          <span>Live trades</span>
          <strong>{formatNumber(Number(row.live_trades ?? 0))}</strong>
        </div>
        <div>
          <span>Research best → live</span>
          <strong>{regimePairValue(row)}</strong>
        </div>
      </div>

      <div className="drift-signal-footer">
        <div className="drift-signal-copy">
          <p>{buildDriftNarrative(row)}</p>
          {row.review_reasons?.length ? <p>Review reasons: {row.review_reasons.join(" • ")}.</p> : null}
        </div>
        <RecentPnlSparkline values={row.recent_pnls} />
      </div>
    </article>
  );
}

function DriftReviewCard({ row }: { row: DriftSummaryRow }) {
  const tone = severityTone[row.severity ?? ""] ?? "neutral";

  return (
    <article className={`drift-review-card tone-${tone}`}>
      <div className="drift-review-header">
        <div className="drift-review-heading">
          <span className="drift-review-eyebrow">Manual review dossier</span>
          <h4>{row.name}</h4>
          <p>{buildDriftHeadline(row)}</p>
        </div>
        <div className="drift-review-badges">
          {severityBadge(row.severity)}
          {row.decay_warning ? <StatusBadge label="Decay warning" tone="critical" /> : null}
        </div>
      </div>

      <div className="drift-chip-row">
        <span className="drift-chip">{row.symbol ?? "Unknown symbol"}</span>
        <span className="drift-chip">{row.family ?? "Unknown family"}</span>
        <span className="drift-chip">{compactValue(row.status)}</span>
      </div>

      <div className="drift-review-metrics">
        <div>
          <span>Review stack</span>
          <strong>{reviewReasonSummary(row)}</strong>
        </div>
        <div>
          <span>Anomalies</span>
          <strong>{anomalySummary(row)}</strong>
        </div>
        <div>
          <span>Regime posture</span>
          <strong>{regimePairValue(row)}</strong>
        </div>
        <div>
          <span>Last update</span>
          <strong>{compactValue(formatDateTime(row.last_update))}</strong>
        </div>
      </div>
    </article>
  );
}

function DriftPageContent() {
  const driftUrlDefaults = useMemo(() => ({
    symbol: "",
    family: "",
    status: "",
    severity: "",
    sort: "highest-drift",
  }), []);
  const { state: driftUrlState, setState: setDriftUrlState, resetState: resetDriftUrlState } = useUrlState(driftUrlDefaults);
  const driftQuery = useQuery("drift-summary", uiApi.driftSummary, { refetchIntervalMs: 60_000 });
  const { data, error, loading, hasData, refreshing, refresh, lastSuccessAt } = driftQuery;
  const symbolFilter = driftUrlState.symbol;
  const familyFilter = driftUrlState.family;
  const statusFilter = driftUrlState.status;
  const severityFilter = driftUrlState.severity;
  const sortPreset = driftUrlState.sort as (typeof sortPresetOptions)[number]["value"];

  const filteredRows = useMemo(() => {
    return (data?.rows ?? []).filter((row) => {
      if (symbolFilter && row.symbol !== symbolFilter) return false;
      if (familyFilter && row.family !== familyFilter) return false;
      if (statusFilter && row.status !== statusFilter) return false;
      if (severityFilter && row.severity !== severityFilter) return false;
      return true;
    });
  }, [data?.rows, symbolFilter, familyFilter, statusFilter, severityFilter]);

  const sortedRows = useMemo(() => {
    const nextRows = [...filteredRows];
    nextRows.sort((left, right) => {
      if (sortPreset === "negative-recent-avg") {
        return Number(left.recent_avg_pnl ?? 0) - Number(right.recent_avg_pnl ?? 0) || Number(right.drift_score ?? 0) - Number(left.drift_score ?? 0);
      }
      if (sortPreset === "most-live-trades") {
        return Number(right.live_trades ?? 0) - Number(left.live_trades ?? 0) || Number(right.drift_score ?? 0) - Number(left.drift_score ?? 0);
      }
      if (sortPreset === "newest-warnings") {
        return (
          Number(Boolean(right.decay_warning)) - Number(Boolean(left.decay_warning)) ||
          (severityRank[right.severity ?? ""] ?? 0) - (severityRank[left.severity ?? ""] ?? 0) ||
          lastUpdateTimestamp(right.last_update) - lastUpdateTimestamp(left.last_update) ||
          Number(right.drift_score ?? 0) - Number(left.drift_score ?? 0)
        );
      }
      return (
        Number(right.drift_score ?? 0) - Number(left.drift_score ?? 0) ||
        (severityRank[right.severity ?? ""] ?? 0) - (severityRank[left.severity ?? ""] ?? 0) ||
        Number(right.live_trades ?? 0) - Number(left.live_trades ?? 0)
      );
    });
    return nextRows;
  }, [filteredRows, sortPreset]);

  if (loading && !hasData) {
    return <LoadingState title="Loading drift diagnostics" description="Collecting live-vs-research mismatch and decay-warning candidates." />;
  }

  if (!data) {
    return <ErrorState error={error} resourceLabel="drift summary" />;
  }

  const filterOptions = data.summary?.available_filters ?? {};
  const topAttention = [...sortedRows]
    .filter((row) => row.severity === "drifting" || row.severity === "broken" || Boolean(row.decay_warning))
    .sort((left, right) => driftPriority(right) - driftPriority(left))
    .slice(0, 6);
  const severityCounts = data.summary?.severity_counts ?? {};
  const regimeAlignmentCounts = data.summary?.regime_alignment_counts ?? {};
  const anomalyGroups = data.summary?.unresolved_anomaly_groups ?? {};
  const manualReviewQueue = [...(data.manual_review_queue ?? [])].sort((left, right) => driftPriority(right) - driftPriority(left));
  const visibleBroken = filteredRows.filter((row) => row.severity === "broken").length;
  const visibleDrifting = filteredRows.filter((row) => row.severity === "drifting").length;
  const visibleMismatch = filteredRows.filter((row) => row.regime_alignment === "mismatch").length;
  const visibleAnomalyRows = filteredRows.filter((row) => Number(row.unresolved_anomaly_count ?? 0) > 0).length;

  return (
    <div className="dashboard-stack">
      <PageHeader
        title="Drift"
        subtitle="Live-vs-research mismatch view for spotting decay warnings, negative recent averages, and strategies that deserve operator review."
        meta={`Snapshot ${formatDateTime(data.generated_at)}`}
        action={
          <div className="page-toolbar">
            <FreshnessBadge timestamp={data.generated_at} thresholds={{ warningMs: 15 * 60_000, criticalMs: 60 * 60_000 }} />
            <ToolbarButton label="Refresh now" onClick={() => void refresh()} busy={refreshing} tone="info" />
          </div>
        }
      />

      <QueryStateNotice
        error={error}
        refreshing={refreshing}
        hasData={hasData}
        resourceLabel="drift summary"
        lastSuccessAt={lastSuccessAt}
      />

      <section className="stats-grid">
        <StatCard label="Tracked strategies" value={formatNumber(Number(data.summary?.strategy_count ?? 0))} hint="Rows surfaced by drift adapter" tone="info" />
        <StatCard label="Visible rows" value={formatNumber(filteredRows.length)} hint="Rows after current filters" tone="info" />
        <StatCard label="Broken" value={formatNumber(Number(severityCounts.broken ?? 0))} hint="Highest-risk drift severity" tone="critical" />
        <StatCard label="Drifting" value={formatNumber(Number(severityCounts.drifting ?? 0))} hint="Negative or widening mismatch" tone="warning" />
        <StatCard label="Regime mismatch" value={formatNumber(Number(regimeAlignmentCounts.mismatch ?? 0))} hint="Research best regime disagrees with live observed regime" tone="critical" />
        <StatCard label="Repeated decay" value={formatNumber(Number(data.summary?.repeated_decay_strategy_count ?? 0))} hint="Strategies with 2+ logged decay warnings" tone="warning" />
        <StatCard label="Manual review" value={formatNumber(Number(data.summary?.manual_review_count ?? 0))} hint="Strategies currently queued for operator review" tone="critical" />
      </section>

      <Section title="Drift filters" description="Slice the drift snapshot by symbol, family, lifecycle status, severity, and triage sort preset.">
        <FilterToolbar className="xl:grid-cols-5">
          <FilterField label="Symbol">
            <FilterSelect value={symbolFilter || "__all__"} onChange={(event) => setDriftUrlState({ symbol: normalizeFilterValue(event.target.value) })}>
              <option value="__all__">All symbols</option>
              {(filterOptions.symbols ?? []).map((value) => <option key={value} value={value}>{value}</option>)}
            </FilterSelect>
          </FilterField>
          <FilterField label="Family">
            <FilterSelect value={familyFilter || "__all__"} onChange={(event) => setDriftUrlState({ family: normalizeFilterValue(event.target.value) })}>
              <option value="__all__">All families</option>
              {(filterOptions.families ?? []).map((value) => <option key={value} value={value}>{value}</option>)}
            </FilterSelect>
          </FilterField>
          <FilterField label="Status">
            <FilterSelect value={statusFilter || "__all__"} onChange={(event) => setDriftUrlState({ status: normalizeFilterValue(event.target.value) })}>
              <option value="__all__">All statuses</option>
              {(filterOptions.statuses ?? []).map((value) => <option key={value} value={value}>{value}</option>)}
            </FilterSelect>
          </FilterField>
          <FilterField label="Severity">
            <FilterSelect value={severityFilter || "__all__"} onChange={(event) => setDriftUrlState({ severity: normalizeFilterValue(event.target.value) })}>
              <option value="__all__">All severities</option>
              {(filterOptions.severities ?? []).map((value) => <option key={value} value={value}>{value}</option>)}
            </FilterSelect>
          </FilterField>
          <FilterField label="Sort view">
            <FilterSelect value={sortPreset} onChange={(event) => setDriftUrlState({ sort: event.target.value as (typeof sortPresetOptions)[number]["value"] })}>
              {sortPresetOptions.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
            </FilterSelect>
          </FilterField>
          <ToolbarButton
            label="Reset filters"
            onClick={() => resetDriftUrlState()}
            tone="neutral"
          />
        </FilterToolbar>
      </Section>

      <Section title="Operator attention lanes" description="A faster read on which drift patterns deserve immediate review before you scan the full leaderboard.">
        <div className="attention-grid">
          <AttentionCard
            label="Broken drift"
            value={formatNumber(visibleBroken)}
            detail="Rows where the live thesis is no longer behaving like the research edge and should be handled as incidents."
            tone="critical"
          />
          <AttentionCard
            label="Drifting edge"
            value={formatNumber(visibleDrifting)}
            detail="Strategies still active, but the recent slope is bending away from the profile that originally earned a slot."
            tone="warning"
          />
          <AttentionCard
            label="Regime disagreement"
            value={formatNumber(visibleMismatch)}
            detail="Research expects the edge in one market regime, but live evidence is currently forming somewhere else."
            tone="critical"
          />
          <AttentionCard
            label="Anomaly-backed rows"
            value={formatNumber(visibleAnomalyRows)}
            detail="Rows where unresolved closes, missing live stats, or stale updates make the drift read less trustworthy."
            tone={visibleAnomalyRows > 0 ? "warning" : "neutral"}
          />
        </div>
      </Section>

      <Section title="Severity language" description="Translate each severity bucket into an operator meaning before dropping into row-by-row triage.">
        <div className="drift-lane-grid">
          {(["broken", "drifting", "watch", "healthy"] as const).map((key) => (
            <article key={key} className={`drift-lane-card tone-${severityTone[key]}`}>
              <div className="drift-lane-header">
                <span className="drift-lane-eyebrow">{severityLabel[key]}</span>
                <StatusBadge label={formatNumber(Number(severityCounts[key] ?? 0))} tone={severityTone[key]} />
              </div>
              <strong>{key === "broken" ? "Intervene now" : key === "drifting" ? "Review next" : key === "watch" ? "Track closely" : "Low urgency"}</strong>
              <p>{severityNarrative[key]}</p>
            </article>
          ))}
        </div>
      </Section>

      <Section title="Drift summary" description="Compact aggregate statistics for the current drift snapshot.">
        <KeyValueGrid data={data.summary ?? {}} emptyTitle="No drift summary" emptyDescription="The drift endpoint did not return aggregate drift metadata." />
      </Section>

      <Section title="Unresolved anomaly groups" description="Grouped unresolved issues that should shape operator triage across reconciliation and live-stat freshness.">
        <KeyValueGrid
          data={Object.fromEntries(Object.entries(anomalyGroups).map(([key, value]) => [anomalyLabel[key] ?? key, value]))}
          emptyTitle="No grouped anomalies"
          emptyDescription="The current drift snapshot did not detect unresolved anomaly groups."
        />
      </Section>

      <Section title="Priority drift dossiers" description="Top mismatches rewritten as operator briefs so the riskiest rows do not hide inside a dense table.">
        {topAttention.length ? (
          <div className="drift-signal-grid">
            {topAttention.map((row) => <DriftSignalCard key={`${row.name}-signal`} row={row} />)}
          </div>
        ) : (
          <EmptyState
            title="No priority dossiers"
            description="No filtered rows currently cross the drift attention heuristics."
            compact
          />
        )}
      </Section>

      <Section title="Manual review dossiers" description="Rows where repeated decay, severe mismatch, or anomaly stacking make a human pass worthwhile.">
        {manualReviewQueue.length ? (
          <div className="drift-review-grid">
            {manualReviewQueue.map((row) => <DriftReviewCard key={`${row.name}-review`} row={row} />)}
          </div>
        ) : (
          <EmptyState
            title="No manual review queue"
            description="The drift snapshot did not surface any rows that need manual review right now."
            compact
          />
        )}
      </Section>

      <Section title="Drift leaderboard" description="The full ledger remains here for sort-heavy review once the high-priority dossiers are understood.">
        <DataTable
          columns={["Strategy", "Symbol", "Family", "Status", "Severity", "Regime alignment", "Research best → live observed", "Trades", "Research return", "Research sharpe", "Live PnL", "Recent avg", "Recent sequence", "Decay count", "Anomalies", "Drift score", "Last update"]}
          rows={sortedRows.map((row: DriftSummaryRow) => [
            compactValue(row.name),
            compactValue(row.symbol),
            compactValue(row.family),
            compactValue(row.status),
            severityBadge(row.severity),
            regimeAlignmentBadge(row.regime_alignment),
            regimePairValue(row),
            formatNumber(Number(row.live_trades ?? 0)),
            formatPercent(Number(row.research_return_pct ?? 0)),
            formatNumber(Number(row.research_sharpe ?? 0)),
            formatCurrency(Number(row.live_total_pnl ?? 0)),
            formatCurrency(Number(row.recent_avg_pnl ?? 0)),
            <RecentPnlSparkline key={`${String(row.name)}-leaderboard-sequence`} values={row.recent_pnls} />,
            formatNumber(Number(row.decay_warning_count ?? 0)),
            anomalySummary(row),
            formatNumber(Number(row.drift_score ?? 0)),
            compactValue(formatDateTime(row.last_update)),
          ])}
          emptyTitle="No drift rows"
          emptyDescription="No rows match the current filter selection."
        />
      </Section>
    </div>
  );
}

export default function DriftPage() {
  return (
    <Suspense fallback={<LoadingState title="Loading drift diagnostics" description="Restoring URL-driven operator filters." />}>
      <DriftPageContent />
    </Suspense>
  );
}
