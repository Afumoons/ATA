"use client";

import { Suspense, useMemo } from "react";
import { PageHeader } from "@/components/app-shell";
import {
  AttentionCard,
  DataTable,
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
import { compactValue, formatCurrency, formatDateTime, formatNumber, formatPercent } from "@/lib/format";
import type { ReviewQueueRow, StatusTone } from "@/lib/types";

const triageLabels: Record<string, string> = {
  promote_watch: "Promote watch",
  demote_watch: "Demote watch",
  inspect: "Inspect",
  archive: "Archive",
};

const triageTones: Record<string, StatusTone> = {
  promote_watch: "success",
  demote_watch: "critical",
  inspect: "warning",
  archive: "neutral",
};

const categoryLabels: Record<string, string> = {
  almost_accepted: "Almost accepted",
  live_drifting: "Live drifting",
  family_or_regime_mismatched: "Family/regime mismatch",
  stale_but_active: "Stale but active",
  repeated_reconciliation_anomalies: "Repeated recon anomalies",
};

const severityTones: Record<string, StatusTone> = {
  healthy: "success",
  watch: "warning",
  drifting: "warning",
  broken: "critical",
};

function normalizeFilterValue(value: string) {
  return value === "__all__" ? "" : value;
}

function bucketBadge(value: string | null | undefined) {
  const key = value ?? "inspect";
  return <StatusBadge label={triageLabels[key] ?? compactValue(key)} tone={triageTones[key] ?? "neutral"} />;
}

function severityBadge(value: string | null | undefined) {
  const key = value ?? "unknown";
  const label = key === "unknown" ? "Unknown" : key[0].toUpperCase() + key.slice(1);
  return <StatusBadge label={label} tone={severityTones[key] ?? "neutral"} />;
}

function categorySummary(row: ReviewQueueRow) {
  const labels = (row.category_flags ?? []).map((value) => categoryLabels[value] ?? value);
  if (!labels.length) return <span className="text-xs text-muted-foreground">No category</span>;
  return compactValue(labels.join(" • "));
}

function reasonSummary(row: ReviewQueueRow) {
  const reasons = row.triage_reasons ?? [];
  if (!reasons.length) return <span className="text-xs text-muted-foreground">No triage reason</span>;
  return compactValue(reasons.join(" • "));
}

function metricToneFromNumber(value: number | null | undefined, inverse = false): StatusTone {
  if (value == null || Number.isNaN(value)) return "neutral";
  if (value === 0) return "neutral";
  if (inverse) {
    return value > 0 ? "warning" : "success";
  }
  return value > 0 ? "success" : "critical";
}

function staleTone(hours: number | null | undefined): StatusTone {
  if (hours == null || Number.isNaN(hours)) return "neutral";
  if (hours >= 48) return "critical";
  if (hours >= 24) return "warning";
  return "success";
}

function renderCategoryChips(row: ReviewQueueRow) {
  const labels = (row.category_flags ?? []).map((value) => categoryLabels[value] ?? value);
  if (!labels.length) {
    return <span className="review-chip tone-neutral">No category flag</span>;
  }

  return labels.map((label) => (
    <span key={`${row.name}-${label}`} className="review-chip tone-info">{label}</span>
  ));
}

function reviewPriorityLabel(row: ReviewQueueRow) {
  if (row.triage_bucket === "demote_watch") return "Needs demotion review";
  if (row.triage_bucket === "promote_watch") return "Ready for promotion review";
  if (row.triage_bucket === "archive") return "Archive / cleanup candidate";
  return "Needs operator diagnosis";
}

function ReviewPageContent() {
  const reviewUrlDefaults = useMemo(() => ({
    bucket: "",
    category: "",
    status: "",
    symbol: "",
  }), []);
  const { state: reviewUrlState, setState: setReviewUrlState, resetState: resetReviewUrlState } = useUrlState(reviewUrlDefaults);
  const reviewQuery = useQuery("review-queue", uiApi.reviewQueue, { refetchIntervalMs: 60_000 });
  const { data, error, loading, hasData, refreshing, refresh, lastSuccessAt } = reviewQuery;
  const bucketFilter = reviewUrlState.bucket;
  const categoryFilter = reviewUrlState.category;
  const statusFilter = reviewUrlState.status;
  const symbolFilter = reviewUrlState.symbol;

  const filteredRows = useMemo(() => {
    return (data?.rows ?? []).filter((row) => {
      if (bucketFilter && row.triage_bucket !== bucketFilter) return false;
      if (categoryFilter && !(row.category_flags ?? []).includes(categoryFilter)) return false;
      if (statusFilter && row.status !== statusFilter) return false;
      if (symbolFilter && row.symbol !== symbolFilter) return false;
      return true;
    });
  }, [bucketFilter, categoryFilter, data?.rows, statusFilter, symbolFilter]);

  const bucketRows = useMemo(() => {
    const rowsByBucket = new Map<string, ReviewQueueRow[]>();
    for (const key of ["promote_watch", "demote_watch", "inspect", "archive"]) {
      rowsByBucket.set(key, filteredRows.filter((row) => row.triage_bucket === key));
    }
    return rowsByBucket;
  }, [filteredRows]);

  if (loading && !hasData) {
    return <LoadingState title="Loading review queue" description="Shaping strategy review candidates into promotion, demotion, inspection, and archive buckets." />;
  }

  if (!data) {
    return <ErrorState error={error} resourceLabel="review queue" />;
  }

  const filterOptions = data.summary?.available_filters ?? {};
  const triageCounts = data.summary?.triage_counts ?? {};
  const categoryCounts = data.summary?.category_counts ?? {};

  return (
    <div className="dashboard-stack">
      <PageHeader
        title="Review queue"
        subtitle="Operator triage surface for near-promotion candidates, drifting live strategies, stale active slots, and reconciliation anomalies."
        meta={`Snapshot ${formatDateTime(data.generated_at)}`}
        action={
          <div className="page-toolbar">
            <FreshnessBadge timestamp={data.generated_at} thresholds={{ warningMs: 15 * 60_000, criticalMs: 60 * 60_000 }} />
            <ToolbarButton label="Refresh now" onClick={() => void refresh()} busy={refreshing} tone="info" />
          </div>
        }
      />

      <QueryStateNotice error={error} refreshing={refreshing} hasData={hasData} resourceLabel="review queue" lastSuccessAt={lastSuccessAt} />

      <section className="stats-grid">
        <StatCard label="Queued strategies" value={formatNumber(Number(data.summary?.queue_count ?? 0))} hint="All rows eligible for review" tone="info" />
        <StatCard label="Promote watch" value={formatNumber(Number(triageCounts.promote_watch ?? 0))} hint="Candidates close to live acceptance" tone="success" />
        <StatCard label="Demote watch" value={formatNumber(Number(triageCounts.demote_watch ?? 0))} hint="Live rows with drift or stale risk" tone="critical" />
        <StatCard label="Inspect" value={formatNumber(Number(triageCounts.inspect ?? 0))} hint="Rows needing operator diagnosis" tone="warning" />
        <StatCard label="Archive" value={formatNumber(Number(triageCounts.archive ?? 0))} hint="Rows likely ready for retirement cleanup" tone="neutral" />
        <StatCard label="Mismatch" value={formatNumber(Number(categoryCounts.family_or_regime_mismatched ?? 0))} hint="Family metadata or regime disagreement" tone="warning" />
        <StatCard label="Repeated recon" value={formatNumber(Number(categoryCounts.repeated_reconciliation_anomalies ?? 0))} hint="Unmatched-close anomalies repeating" tone="critical" />
      </section>

      <Section title="Queue filters" description="Slice the review queue by triage bucket, queue category, current status, and symbol.">
        <FilterToolbar>
          <FilterField label="Triage bucket">
            <FilterSelect value={bucketFilter || "__all__"} onChange={(event) => setReviewUrlState({ bucket: normalizeFilterValue(event.target.value) })}>
              <option value="__all__">All buckets</option>
              {(filterOptions.triage_buckets ?? []).map((value) => <option key={value} value={value}>{triageLabels[value] ?? value}</option>)}
            </FilterSelect>
          </FilterField>
          <FilterField label="Category">
            <FilterSelect value={categoryFilter || "__all__"} onChange={(event) => setReviewUrlState({ category: normalizeFilterValue(event.target.value) })}>
              <option value="__all__">All categories</option>
              {(filterOptions.categories ?? []).map((value) => <option key={value} value={value}>{categoryLabels[value] ?? value}</option>)}
            </FilterSelect>
          </FilterField>
          <FilterField label="Status">
            <FilterSelect value={statusFilter || "__all__"} onChange={(event) => setReviewUrlState({ status: normalizeFilterValue(event.target.value) })}>
              <option value="__all__">All statuses</option>
              {(filterOptions.statuses ?? []).map((value) => <option key={value} value={value}>{value}</option>)}
            </FilterSelect>
          </FilterField>
          <FilterField label="Symbol">
            <FilterSelect value={symbolFilter || "__all__"} onChange={(event) => setReviewUrlState({ symbol: normalizeFilterValue(event.target.value) })}>
              <option value="__all__">All symbols</option>
              {(filterOptions.symbols ?? []).map((value) => <option key={value} value={value}>{value}</option>)}
            </FilterSelect>
          </FilterField>
          <ToolbarButton
            label="Reset filters"
            onClick={() => resetReviewUrlState()}
            tone="neutral"
          />
        </FilterToolbar>
      </Section>

      <Section title="Triage lane spotlight" description="Visual grouping for the four operator lanes that matter most before reading the full queue.">
        <div className="attention-grid">
          <AttentionCard
            label="Promote watch"
            value={formatNumber(Number(triageCounts.promote_watch ?? 0))}
            detail="Near-acceptance candidates that deserve quick promotion review before they cool off."
            tone="success"
          />
          <AttentionCard
            label="Demote watch"
            value={formatNumber(Number(triageCounts.demote_watch ?? 0))}
            detail="Live rows drifting, degrading, or staying active while evidence is turning against them."
            tone="critical"
          />
          <AttentionCard
            label="Inspect"
            value={formatNumber(Number(triageCounts.inspect ?? 0))}
            detail="Rows with mismatched metadata or runtime anomalies that need diagnosis, not instant action."
            tone="warning"
          />
          <AttentionCard
            label="Archive"
            value={formatNumber(Number(triageCounts.archive ?? 0))}
            detail="Disabled or cleanup-tier rows that still carry governance or housekeeping questions."
            tone="neutral"
          />
        </div>
      </Section>

      <Section title="Queue summary" description="Compact aggregate counts exposed by the backend queue adapter.">
        <KeyValueGrid data={data.summary ?? {}} emptyTitle="No queue summary" emptyDescription="The review queue endpoint did not return aggregate metadata." />
      </Section>

      <div className="grid gap-4 xl:grid-cols-2">
        {(["promote_watch", "demote_watch", "inspect", "archive"] as const).map((bucket) => (
          <Section
            key={bucket}
            title={triageLabels[bucket]}
            description={{
              promote_watch: "Candidates close to the live floor and worth keeping visible for a promotion decision.",
              demote_watch: "Active or exploratory rows where live behavior is now pointing the wrong way.",
              inspect: "Rows where mismatched metadata or anomalies deserve operator diagnosis before action.",
              archive: "Disabled or archive-tier rows that still surface meaningful cleanup or governance questions.",
            }[bucket]}
            action={bucketBadge(bucket)}
          >
            <DataTable
              columns={["Strategy", "Status", "Family", "Categories", "Drift", "Promotion gap", "Reasons"]}
              rows={(bucketRows.get(bucket) ?? []).slice(0, 8).map((row) => [
                compactValue(row.name),
                compactValue(row.status),
                compactValue(row.family),
                categorySummary(row),
                severityBadge(row.drift_severity),
                row.promotion_gap == null ? <span className="text-xs text-muted-foreground">n/a</span> : formatNumber(row.promotion_gap),
                reasonSummary(row),
              ])}
              emptyTitle={`No ${triageLabels[bucket].toLowerCase()} rows`}
              emptyDescription="No filtered strategies currently land in this triage bucket."
            />
          </Section>
        ))}
      </div>

      <Section title="Full review queue" description="Detailed operator queue spanning all roadmap review categories and triage buckets.">
        <div className="dashboard-stack">
          <div className="review-dossier-grid">
            {filteredRows.map((row) => (
              <article key={`${row.name}-${row.symbol}-${row.family}`} className={`panel review-dossier-card tone-${triageTones[row.triage_bucket ?? "inspect"] ?? "neutral"}`}>
                <div className="review-dossier-header">
                  <div className="review-dossier-heading">
                    <span className="review-dossier-eyebrow">{reviewPriorityLabel(row)}</span>
                    <h4>{compactValue(row.name)}</h4>
                    <p>
                      {compactValue(row.symbol)} · {compactValue(row.family)} · {compactValue(row.status)}
                    </p>
                  </div>
                  <div className="review-dossier-badges">
                    {bucketBadge(row.triage_bucket)}
                    {severityBadge(row.drift_severity)}
                  </div>
                </div>

                <div className="review-chip-row">{renderCategoryChips(row)}</div>

                <div className="review-dossier-metrics">
                  <div className={`review-dossier-metric tone-${metricToneFromNumber(row.score)}`}>
                    <span>Score</span>
                    <strong>{formatNumber(row.score)}</strong>
                  </div>
                  <div className={`review-dossier-metric tone-${metricToneFromNumber(row.promotion_gap, true)}`}>
                    <span>Promotion gap</span>
                    <strong>{row.promotion_gap == null ? "n/a" : formatNumber(row.promotion_gap)}</strong>
                  </div>
                  <div className={`review-dossier-metric tone-${metricToneFromNumber(Number(row.research_return_pct ?? 0))}`}>
                    <span>Research return</span>
                    <strong>{formatPercent(Number(row.research_return_pct ?? 0))}</strong>
                  </div>
                  <div className={`review-dossier-metric tone-${metricToneFromNumber(Number(row.live_total_pnl ?? 0))}`}>
                    <span>Live PnL</span>
                    <strong>{formatCurrency(Number(row.live_total_pnl ?? 0))}</strong>
                  </div>
                  <div className={`review-dossier-metric tone-${metricToneFromNumber(Number(row.recent_avg_pnl ?? 0))}`}>
                    <span>Recent avg</span>
                    <strong>{formatCurrency(Number(row.recent_avg_pnl ?? 0))}</strong>
                  </div>
                  <div className={`review-dossier-metric tone-${Number(row.unmatched_close_count ?? 0) > 0 ? "critical" : "success"}`}>
                    <span>Recon pressure</span>
                    <strong>{formatNumber(Number(row.unmatched_close_count ?? 0))} unmatched</strong>
                  </div>
                  <div className={`review-dossier-metric tone-${Number(row.decay_warning_count ?? 0) > 0 ? "warning" : "success"}`}>
                    <span>Decay warnings</span>
                    <strong>{formatNumber(Number(row.decay_warning_count ?? 0))}</strong>
                  </div>
                  <div className={`review-dossier-metric tone-${staleTone(row.stale_hours)}`}>
                    <span>Stale window</span>
                    <strong>{row.stale_hours == null ? "n/a" : `${formatNumber(row.stale_hours)}h`}</strong>
                  </div>
                </div>

                <div className="review-dossier-footer">
                  <div className="review-dossier-copy">
                    <span className="review-dossier-label">Why it is here</span>
                    <p>{reasonSummary(row)}</p>
                  </div>
                  <div className="review-dossier-copy">
                    <span className="review-dossier-label">Manifest / freshness</span>
                    <p>
                      Rank {formatNumber(row.manifest_rank)}
                      {row.last_update ? ` · last update ${formatDateTime(row.last_update)}` : " · last update unavailable"}
                    </p>
                  </div>
                </div>
              </article>
            ))}
          </div>

          <DataTable
            columns={["Strategy", "Bucket", "Status", "Symbol", "Family", "Categories", "Score", "Manifest rank", "Research return", "Live PnL", "Recent avg", "Unmatched closes", "Decay count", "Stale hours", "Last update", "Reasons"]}
            rows={filteredRows.map((row) => [
              compactValue(row.name),
              bucketBadge(row.triage_bucket),
              compactValue(row.status),
              compactValue(row.symbol),
              compactValue(row.family),
              categorySummary(row),
              formatNumber(row.score),
              formatNumber(row.manifest_rank),
              formatPercent(Number(row.research_return_pct ?? 0)),
              formatCurrency(Number(row.live_total_pnl ?? 0)),
              formatCurrency(Number(row.recent_avg_pnl ?? 0)),
              formatNumber(Number(row.unmatched_close_count ?? 0)),
              formatNumber(Number(row.decay_warning_count ?? 0)),
              row.stale_hours == null ? <span className="text-xs text-muted-foreground">n/a</span> : `${formatNumber(row.stale_hours)}h`,
              compactValue(formatDateTime(row.last_update)),
              reasonSummary(row),
            ])}
            emptyTitle="No review rows"
            emptyDescription="No strategies match the current review queue filters."
          />
        </div>
      </Section>
    </div>
  );
}

export default function ReviewPage() {
  return (
    <Suspense fallback={<LoadingState title="Loading review queue" description="Restoring URL-driven operator filters." />}>
      <ReviewPageContent />
    </Suspense>
  );
}
