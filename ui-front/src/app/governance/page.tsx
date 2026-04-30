"use client";

import { PageHeader } from "@/components/app-shell";
import {
  DataTable,
  EmptyState,
  ErrorState,
  FreshnessBadge,
  InlineNotice,
  LoadingState,
  QueryStateNotice,
  Section,
  StatCard,
  StatusBadge,
  ToolbarButton,
} from "@/components/dashboard";
import { useQuery } from "@/hooks/use-query";
import { uiApi } from "@/lib/api";
import { compactValue, formatCurrency, formatDateTime, formatNumber, formatPercent } from "@/lib/format";
import type { StatusTone } from "@/lib/types";

type GovernanceFamilyRow = Record<string, unknown> & { manifestShare: number; activeShare: number };
type GovernanceImbalanceRow = GovernanceFamilyRow & { ratio: number | null; tone: StatusTone; reading: string };

function normalizeRows(value: unknown) {
  if (!Array.isArray(value)) return [] as Array<Record<string, unknown>>;
  return value.filter((item): item is Record<string, unknown> => Boolean(item) && typeof item === "object" && !Array.isArray(item));
}

function shareTone(value: number) {
  if (value >= 0.6) return "critical" as const;
  if (value >= 0.45) return "warning" as const;
  if (value >= 0.3) return "info" as const;
  return "success" as const;
}

function ratioTone(value: number | null) {
  if (value == null) return "neutral" as const;
  if (value >= 3) return "critical" as const;
  if (value >= 2) return "warning" as const;
  if (value >= 1.2) return "info" as const;
  return "success" as const;
}

function toneLabel(tone: StatusTone) {
  switch (tone) {
    case "success":
      return "Healthy";
    case "info":
      return "Watch";
    case "warning":
      return "Warning";
    case "critical":
      return "Violation";
    default:
      return "Neutral";
  }
}

export default function GovernancePage() {
  const poolQuery = useQuery("governance-pool-summary", uiApi.poolSummary, { refetchIntervalMs: 60_000 });
  const { data, error, loading, hasData, refreshing, refresh, lastSuccessAt } = poolQuery;

  if (loading && !hasData) {
    return <LoadingState title="Loading governance summary" description="Shaping pool concentration, diversity, and inventory-balance signals into a governance readout." />;
  }

  if (!data) {
    return <ErrorState error={error} resourceLabel="governance summary" />;
  }

  const familyRows = normalizeRows(data.family_comparison?.rows);
  const activeCount = Number(data.status_counts?.active ?? 0);
  const candidateCount = Number(data.status_counts?.candidate ?? 0);
  const exploratoryCount = Number(data.status_counts?.exploratory ?? 0);
  const disabledCount = Number(data.status_counts?.disabled ?? 0);
  const manifestTotal = familyRows.reduce((total, row) => total + Number(row.manifest_count ?? 0), 0);
  const activeFamilyRows = familyRows.filter((row) => Number(row.active_count ?? 0) > 0);
  const manifestFamilyRows = familyRows.filter((row) => Number(row.manifest_count ?? 0) > 0);
  const liveFamilyRows = familyRows.filter((row) => Number(row.live_count ?? 0) > 0);
  const topManifestFamily = familyRows.reduce<Record<string, unknown> | null>((best, row) => {
    if (!best) return row;
    return Number(row.manifest_count ?? 0) > Number(best.manifest_count ?? 0) ? row : best;
  }, null);
  const topActiveFamily = familyRows.reduce<Record<string, unknown> | null>((best, row) => {
    if (!best) return row;
    return Number(row.active_count ?? 0) > Number(best.active_count ?? 0) ? row : best;
  }, null);
  const topManifestShare = manifestTotal > 0 ? Number(topManifestFamily?.manifest_count ?? 0) / manifestTotal : 0;
  const topActiveShare = activeCount > 0 ? Number(topActiveFamily?.active_count ?? 0) / activeCount : 0;
  const disabledActiveRatio = activeCount > 0 ? disabledCount / activeCount : disabledCount > 0 ? null : 0;
  const candidateCoverage = activeCount > 0 ? (candidateCount + exploratoryCount) / activeCount : null;

  const policies = [
    {
      rule: "Manifest concentration per family",
      target: "No single family should own more than 50% of current manifest slots",
      observed: `${compactValue(topManifestFamily?.label ?? topManifestFamily?.family ?? "none")} at ${formatPercent(topManifestShare)}`,
      tone: topManifestShare >= 0.5 ? "critical" as const : topManifestShare >= 0.4 ? "warning" as const : "success" as const,
      meaning: "If one lineage dominates deployment composition, governance visibility should treat the manifest as concentrated rather than diversified.",
    },
    {
      rule: "Active pool family share",
      target: "No single family should own more than 45% of active slots",
      observed: `${compactValue(topActiveFamily?.label ?? topActiveFamily?.family ?? "none")} at ${formatPercent(topActiveShare)}`,
      tone: topActiveShare >= 0.6 ? "critical" as const : topActiveShare >= 0.45 ? "warning" as const : "success" as const,
      meaning: "Active-slot concentration matters more than total inventory because it shapes real live exposure.",
    },
    {
      rule: "Active family diversity floor",
      target: activeCount >= 6 ? "Keep at least 3 families active when the active pool is this large" : "Informational while active pool remains small",
      observed: `${formatNumber(activeFamilyRows.length)} active family(ies) across ${formatNumber(activeCount)} active slot(s)`,
      tone: activeCount < 6 ? "info" as const : activeFamilyRows.length >= 3 ? "success" as const : "critical" as const,
      meaning: "A wider active-family mix lowers the risk that one research lineage quietly becomes the whole book.",
    },
    {
      rule: "Disabled inventory balance",
      target: "Disabled inventory should stay under 2x the active inventory",
      observed: disabledActiveRatio == null ? `${formatNumber(disabledCount)} disabled with no active baseline` : `${formatNumber(disabledCount)} disabled vs ${formatNumber(activeCount)} active (${formatNumber(disabledActiveRatio)}x)`,
      tone: disabledActiveRatio == null ? "critical" as const : disabledActiveRatio >= 2 ? "warning" as const : "success" as const,
      meaning: "A heavily parked pool can mean stale lineage buildup, poor pruning, or weak promotion flow.",
    },
  ];

  const violations = policies.filter((policy) => policy.tone === "warning" || policy.tone === "critical");

  const saturationRows = [...familyRows]
    .map((row) => {
      const manifestShare = manifestTotal > 0 ? Number(row.manifest_count ?? 0) / manifestTotal : 0;
      const activeShare = activeCount > 0 ? Number(row.active_count ?? 0) / activeCount : 0;
      return {
        ...(row as Record<string, unknown>),
        manifestShare,
        activeShare,
      } as GovernanceFamilyRow;
    })
    .sort((left, right) => {
      const activeShareDelta = Number(right.activeShare ?? 0) - Number(left.activeShare ?? 0);
      if (activeShareDelta !== 0) return activeShareDelta;
      return Number(right.manifestShare ?? 0) - Number(left.manifestShare ?? 0);
    });

  const imbalanceRows = saturationRows
    .map((row) => {
      const active = Number(row.active_count ?? 0);
      const disabled = Number(row.disabled_count ?? 0);
      const ratio = active > 0 ? disabled / active : disabled > 0 ? null : 0;
      const tone = active === 0 && disabled >= 3 ? "critical" as const : ratio != null && ratio >= 3 ? "critical" as const : ratio != null && ratio >= 1.5 ? "warning" as const : "info" as const;
      const reading = active === 0 && disabled >= 3
        ? "This lineage is mostly parked, with no active representation left in the pool."
        : ratio != null && ratio >= 3
          ? "Disabled inventory heavily outweighs active coverage, which usually means this family needs pruning or a clearer re-entry policy."
          : ratio != null && ratio >= 1.5
            ? "Disabled rows outweigh active coverage enough to deserve cleanup review."
            : "The family still looks reasonably balanced between active and parked inventory.";
      return { ...(row as Record<string, unknown>), ratio, tone, reading } as GovernanceImbalanceRow;
    })
    .filter((row) => Number(row.disabled_count ?? 0) > 0)
    .sort((left, right) => {
      const leftRank = left.ratio == null ? Number.POSITIVE_INFINITY : Number(left.ratio);
      const rightRank = right.ratio == null ? Number.POSITIVE_INFINITY : Number(right.ratio);
      return rightRank - leftRank;
    });

  return (
    <div className="dashboard-stack">
      <PageHeader
        title="Governance"
        subtitle="Read-only governance surface for pool concentration, lineage diversity, policy-style guardrails, and inventory-balance warnings before operator action is needed."
        meta={`Snapshot ${formatDateTime(data.generated_at)}`}
        action={
          <div className="page-toolbar">
            <FreshnessBadge timestamp={data.generated_at} thresholds={{ warningMs: 15 * 60_000, criticalMs: 60 * 60_000 }} />
            <ToolbarButton label="Refresh now" onClick={() => void refresh()} busy={refreshing} tone="info" />
          </div>
        }
      />

      <QueryStateNotice error={error} refreshing={refreshing} hasData={hasData} resourceLabel="governance summary" lastSuccessAt={lastSuccessAt} />

      {violations.length ? (
        <InlineNotice
          tone={violations.some((item) => item.tone === "critical") ? "critical" : "warning"}
          title="Governance guardrails are seeing concentration pressure"
          description={`${formatNumber(violations.length)} policy signal(s) are currently outside the healthy band. This page is read-only, but it makes the concentration shape explicit before it leaks into operator blind spots.`}
        />
      ) : (
        <InlineNotice
          tone="success"
          title="Governance posture looks balanced"
          description="The current pool snapshot does not trip the governance heuristics on manifest concentration, active-family diversity, or disabled-inventory balance."
        />
      )}

      <section className="stats-grid">
        <StatCard label="Active inventory" value={formatNumber(activeCount)} hint={`${formatNumber(activeFamilyRows.length)} active family(ies)`} tone="success" />
        <StatCard label="Disabled inventory" value={formatNumber(disabledCount)} hint={disabledActiveRatio == null ? "No active baseline" : `${formatNumber(disabledActiveRatio)}x of active`} tone={ratioTone(disabledActiveRatio)} />
        <StatCard label="Manifest concentration" value={formatPercent(topManifestShare)} hint={String(topManifestFamily?.label ?? topManifestFamily?.family ?? "No manifest family")} tone={shareTone(topManifestShare)} />
        <StatCard label="Active concentration" value={formatPercent(topActiveShare)} hint={String(topActiveFamily?.label ?? topActiveFamily?.family ?? "No active family")} tone={shareTone(topActiveShare)} />
        <StatCard label="Manifest diversity" value={formatNumber(manifestFamilyRows.length)} hint={`${formatNumber(manifestTotal)} live manifest slot(s)`} tone={manifestFamilyRows.length >= 3 ? "success" : manifestFamilyRows.length >= 2 ? "warning" : "critical"} />
        <StatCard label="Live family coverage" value={formatNumber(liveFamilyRows.length)} hint="Families with surfaced live stats" tone={liveFamilyRows.length >= 3 ? "success" : liveFamilyRows.length >= 2 ? "info" : "warning"} />
        <StatCard label="Promotion pipeline" value={formatNumber(candidateCount + exploratoryCount)} hint={candidateCoverage == null ? "No active baseline" : `${formatNumber(candidateCoverage)}x of active inventory`} tone={candidateCoverage == null ? "neutral" : candidateCoverage >= 1 ? "success" : candidateCoverage >= 0.5 ? "info" : "warning"} />
        <StatCard label="Live family PnL" value={formatCurrency(saturationRows.reduce((total, row) => total + Number(row.live_total_pnl ?? 0), 0))} hint="Family-level live PnL sum from the pool summary payload" tone="info" />
      </section>

      <Section title="Governance policy summary" description="UI-defined guardrails that translate pool composition into operator-readable governance checks. These are read-only heuristics, not execution-changing rules.">
        <DataTable
          columns={["Rule", "Target", "Observed state", "Status", "Why it matters"]}
          rows={policies.map((policy) => [
            <div key={policy.rule} className="table-stack">
              <strong>{policy.rule}</strong>
            </div>,
            compactValue(policy.target),
            compactValue(policy.observed),
            <StatusBadge key={`${policy.rule}-status`} label={toneLabel(policy.tone)} tone={policy.tone} />,
            compactValue(policy.meaning),
          ])}
          emptyTitle="No governance rules shaped"
          emptyDescription="The current pool snapshot did not provide enough family-level detail to evaluate governance heuristics."
        />
      </Section>

      <Section title="Current pool composition rules and violations" description="Only the rules currently outside the healthy band, so the operator can see exactly what is bending the pool shape.">
        {violations.length ? (
          <DataTable
            columns={["Rule", "Observed state", "Severity", "Operator reading"]}
            rows={violations.map((policy) => [
              compactValue(policy.rule),
              compactValue(policy.observed),
              <StatusBadge key={`${policy.rule}-severity`} label={toneLabel(policy.tone)} tone={policy.tone} />,
              compactValue(policy.meaning),
            ])}
          />
        ) : (
          <EmptyState
            title="No current governance violations"
            description="This snapshot stays inside the configured governance bands, so nothing needs to be escalated from the policy layer right now."
            tone="success"
            eyebrow="Policy layer calm"
            meaning="Current family mix, concentration, and inventory shape are staying inside the UI governance heuristics."
            nextStep="Keep watching the saturation and imbalance sections for early drift before it becomes a formal policy break."
          />
        )}
      </Section>

      <Section title="Family saturation and diversity indicators" description="How much each family owns of the live manifest and active pool, plus whether the lineage is broad, fragile, or over-concentrated.">
        <DataTable
          columns={["Family", "Manifest share", "Active share", "Inventory", "Research / live", "DNA risk", "Operator read"]}
          rows={saturationRows.map((row) => [
            <div key={`${compactValue(row.family)}-family`} className="table-stack">
              <strong>{compactValue(row.label ?? row.family)}</strong>
              <span>{compactValue(row.family)}</span>
            </div>,
            <div key={`${compactValue(row.family)}-manifest`} className="table-stack">
              <StatusBadge label={formatPercent(Number(row.manifestShare ?? 0))} tone={shareTone(Number(row.manifestShare ?? 0))} />
              <span>{formatNumber(Number(row.manifest_count ?? 0))} of {formatNumber(manifestTotal)} manifest slot(s)</span>
            </div>,
            <div key={`${compactValue(row.family)}-active`} className="table-stack">
              <StatusBadge label={formatPercent(Number(row.activeShare ?? 0))} tone={shareTone(Number(row.activeShare ?? 0))} />
              <span>{formatNumber(Number(row.active_count ?? 0))} of {formatNumber(activeCount)} active slot(s)</span>
            </div>,
            compactValue(`${formatNumber(Number(row.strategy_count ?? 0))} total · ${formatNumber(Number(row.live_count ?? 0))} live`),
            compactValue(`${formatPercent(Number(row.avg_research_return_pct ?? 0))} · ${formatCurrency(Number(row.live_total_pnl ?? 0))}`),
            compactValue(`${formatPercent(Number(row.warning_density ?? 0))} warn · ${formatPercent(Number(row.fragility_density ?? 0))} fragile`),
            Number(row.activeShare ?? 0) >= 0.45
              ? "This lineage already owns a large part of active exposure."
              : Number(row.manifestShare ?? 0) >= 0.4
                ? "Manifest depth is concentrating here faster than the active pool."
                : Number(row.warning_density ?? 0) >= 0.7
                  ? "The family is broad, but warning density is elevated."
                  : "This family adds diversity without dominating the book.",
          ])}
          emptyTitle="No family saturation rows"
          emptyDescription="The pool summary did not expose family-comparison rows for this snapshot."
        />
      </Section>

      <Section title="Active-vs-disabled inventory imbalance warnings" description="Families where parked inventory is starting to outweigh active representation, which often signals stale buildup or unclear pruning policy.">
        {imbalanceRows.length ? (
          <DataTable
            columns={["Family", "Active / disabled", "Ratio", "Backlog", "Severity", "Operator reading"]}
            rows={imbalanceRows.map((row) => [
              compactValue(row.label ?? row.family),
              `${formatNumber(Number(row.active_count ?? 0))} / ${formatNumber(Number(row.disabled_count ?? 0))}`,
              row.ratio == null ? "No active baseline" : `${formatNumber(Number(row.ratio ?? 0))}x`,
              `${formatNumber(Number(row.candidate_count ?? 0))} candidate · ${formatNumber(Number(row.exploratory_count ?? 0))} exploratory`,
              <StatusBadge key={`${compactValue(row.family)}-imbalance`} label={toneLabel(row.tone)} tone={row.tone} />,
              compactValue(row.reading),
            ])}
            emptyTitle="No imbalance warnings"
            emptyDescription="No family currently has any disabled inventory to compare against active coverage."
          />
        ) : (
          <EmptyState
            title="No imbalance rows"
            description="This snapshot did not surface any family with parked inventory, so there is no active-vs-disabled imbalance to explain."
            tone="success"
            eyebrow="Inventory balance healthy"
            meaning="Disabled or parked strategies are not accumulating in a way that suggests stale family buildup."
            nextStep="Revisit this section when disabled inventory starts growing faster than active family coverage."
          />
        )}
      </Section>
    </div>
  );
}
