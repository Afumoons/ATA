"use client";

import { PageHeader } from "@/components/app-shell";
import {
  AttentionCard,
  DataTable,
  EmptyState,
  ErrorState,
  FreshnessBadge,
  InlineNotice,
  KeyValueGrid,
  LoadingState,
  Section,
  StatCard,
  StatusBadge,
  ToolbarButton,
} from "@/components/dashboard";
import { useQuery } from "@/hooks/use-query";
import { uiApi } from "@/lib/api";
import { compactValue, formatCurrency, formatDateTime, formatNumber, formatRelativeAge } from "@/lib/format";
import { getHighSignalExecutionReasons, summarizeEvent, toneFromSignedNumber } from "@/lib/ui-state";

function formatDurationMinutes(value: unknown) {
  if (typeof value !== "number" || Number.isNaN(value)) return "—";
  if (value < 60) return `${value}m`;
  const hours = Math.floor(value / 60);
  const minutes = value % 60;
  if (hours < 24) return `${hours}h ${minutes}m`;
  const days = Math.floor(hours / 24);
  const remainderHours = hours % 24;
  return `${days}d ${remainderHours}h`;
}

function toneFromProtectionStatus(value: unknown) {
  switch (value) {
    case "sl_tp":
      return "success" as const;
    case "sl_only":
    case "tp_only":
      return "warning" as const;
    case "unprotected":
      return "critical" as const;
    default:
      return "neutral" as const;
  }
}

function labelForProtectionStatus(value: unknown) {
  switch (value) {
    case "sl_tp":
      return "SL + TP";
    case "sl_only":
      return "SL only";
    case "tp_only":
      return "TP only";
    case "unprotected":
      return "No SL / TP";
    default:
      return compactValue(value);
  }
}

function toneFromRegistrationFailureCause(value: unknown) {
  const cause = String(value ?? "");
  if (cause === "permission" || cause === "journal_write") return "critical" as const;
  if (cause === "unknown") return "warning" as const;
  return "info" as const;
}

function toneFromUnmatchedDeal(deal: Record<string, unknown>) {
  const confidence = String(deal.pairing_confidence ?? "").toLowerCase();
  if (confidence === "low") return "critical" as const;
  if (confidence === "medium") return "warning" as const;
  if (confidence === "high") return "success" as const;
  return "neutral" as const;
}

function buildSymbolPosture(trades: Array<Record<string, unknown>>): {
  incompleteProtectionCount: number;
  staleUpdateCount: number;
  agedCount: number;
  noRecentLogCount: number;
  missingLiveStatsCount: number;
  longCount: number;
  shortCount: number;
  tone: "success" | "warning" | "critical";
  label: string;
} {
  const incompleteProtectionCount = trades.filter((trade) => trade.protection_status !== "sl_tp").length;
  const staleUpdateCount = trades.filter((trade) => typeof trade.minutes_since_update === "number" && Number(trade.minutes_since_update) >= 60).length;
  const agedCount = trades.filter((trade) => typeof trade.holding_minutes === "number" && Number(trade.holding_minutes) >= 240).length;
  const noRecentLogCount = trades.filter((trade) => Array.isArray(trade.operator_flags) && trade.operator_flags.includes("no_recent_log_match")).length;
  const missingLiveStatsCount = trades.filter((trade) => Array.isArray(trade.operator_flags) && trade.operator_flags.includes("missing_live_stats")).length;
  const longCount = trades.filter((trade) => trade.side === "long").length;
  const shortCount = trades.filter((trade) => trade.side === "short").length;

  const tone = incompleteProtectionCount > 0 || staleUpdateCount > 0
    ? "critical"
    : agedCount > 0 || noRecentLogCount > 0 || missingLiveStatsCount > 0
      ? "warning"
      : "success";

  const label = incompleteProtectionCount > 0
    ? "Protection gap"
    : staleUpdateCount > 0
      ? "Stale updates"
      : agedCount > 0 || noRecentLogCount > 0 || missingLiveStatsCount > 0
        ? "Needs operator watch"
        : "Healthy posture";

  return {
    incompleteProtectionCount,
    staleUpdateCount,
    agedCount,
    noRecentLogCount,
    missingLiveStatsCount,
    longCount,
    shortCount,
    tone,
    label,
  };
}

export default function ExecutionPage() {
  const executionQuery = useQuery("execution-summary", uiApi.executionSummary, { refetchIntervalMs: 45_000 });
  const auditQuery = useQuery("execution-audit-context", () => uiApi.auditTimeline(30), { refetchIntervalMs: 60_000 });

  const { data, error, loading, hasData, refreshing, refresh } = executionQuery;

  if (loading && !hasData) {
    return (
      <LoadingState
        title="Loading execution diagnostics"
        description="Collecting live posture, trade traces, reconciliation state, and recent attention events."
      />
    );
  }

  if (!data) {
    return <ErrorState error={error} resourceLabel="execution summary" />;
  }

  const diagnosisItems = getHighSignalExecutionReasons(data);
  const openTradeSummary = data.open_trades.summary ?? {};
  const openTradeDrilldown = data.open_trades.drilldown ?? [];
  const openTradeBySymbol = openTradeSummary.by_symbol ?? [];
  const recentActivity = data.recent_activity ?? {};
  const recentFills = recentActivity.fills ?? {};
  const recentExits = recentActivity.exits ?? {};
  const recentWindowHours = Number(recentActivity.window_hours ?? 24);
  const executionArtifactWarnings = data.execution_artifact_warnings ?? {};
  const executionArtifactRows = executionArtifactWarnings.artifacts ?? [];
  const tradeContextRegistrationFailures = data.trade_context_registration_failures ?? {};
  const registrationFailureCauses = tradeContextRegistrationFailures.causes ?? [];
  const registrationFailureStrategies = tradeContextRegistrationFailures.strategies ?? [];
  const registrationFailureRecent = tradeContextRegistrationFailures.recent ?? [];
  const noTradeDiagnosis = data.no_trade_diagnosis ?? {};
  const noTradeCauses = noTradeDiagnosis.causes ?? [];
  const activeNoTradeCauses = noTradeCauses.filter((cause) => cause.status === "active");
  const unmatchedDashboard = data.unmatched_closed_deals.dashboard ?? {};
  const unmatchedSummary = unmatchedDashboard.summary ?? {};
  const unmatchedConfidence = unmatchedDashboard.confidence ?? {};
  const unmatchedConfidenceBuckets = unmatchedConfidence.buckets ?? [];
  const unmatchedConfidenceSignals = unmatchedConfidence.signals ?? [];
  const unmatchedLanes = unmatchedDashboard.lanes ?? [];
  const unmatchedReasons = unmatchedDashboard.reasons ?? [];
  const unmatchedSymbols = unmatchedDashboard.symbols ?? [];
  const unmatchedManualBuckets = unmatchedDashboard.manual_buckets ?? [];
  const unmatchedRecent = unmatchedDashboard.recent ?? data.unmatched_closed_deals.recent ?? [];
  const attentionEvents = (auditQuery.data?.events ?? []).filter((event) => {
    const source = String(event.source ?? "").toLowerCase();
    return source.includes("unmatched") || source.includes("trade");
  }).slice(0, 8);

  return (
    <div className="dashboard-stack">
      <PageHeader
        title="Execution diagnostics"
        subtitle="Read-only visibility into live execution state, no-trade context, open positions, reconciliation faults, and the most recent events worth operator attention."
        meta={`Snapshot ${formatDateTime(data.generated_at)}`}
        action={
          <div className="page-toolbar">
            <FreshnessBadge timestamp={data.generated_at} thresholds={{ warningMs: 5 * 60_000, criticalMs: 15 * 60_000 }} />
            <ToolbarButton
              label="Refresh now"
              onClick={() => {
                void Promise.all([refresh(), auditQuery.refresh()]);
              }}
              busy={refreshing || auditQuery.refreshing}
              tone="info"
            />
          </div>
        }
      />

      {auditQuery.error && !auditQuery.data ? (
        <InlineNotice
          tone="warning"
          title="Recent attention events unavailable"
          description="The execution summary loaded, but the companion audit timeline did not. Diagnosis still works, but recent operator-attention events are incomplete for now."
        />
      ) : null}

      <section className="stats-grid">
        <StatCard label="Open trades" value={formatNumber(data.open_trades.count)} hint="Currently open positions" tone="info" />
        <StatCard label="Strategies live" value={formatNumber(data.strategy_live_stats.strategy_count)} hint="Strategies contributing live stats" tone="success" />
        <StatCard label="Trades tracked" value={formatNumber(data.strategy_live_stats.total_trades)} hint="Aggregated strategy trade count" tone="neutral" />
        <StatCard
          label="Realized PnL"
          value={formatCurrency(data.strategy_live_stats.total_realized_pnl)}
          hint="Reported realized PnL"
          tone={toneFromSignedNumber(data.strategy_live_stats.total_realized_pnl)}
        />
      </section>

      <Section title="Recent fills and exits" description={`Compact execution flow over the last ${formatNumber(recentWindowHours)} hour(s), combining fresh fill traces with the trade-context exit journal.`}>
        <div className="dashboard-stack">
          <section className="stats-grid">
            <StatCard
              label="Recent fills"
              value={formatNumber(Number(recentFills.count ?? 0))}
              hint={`Vol ${compactValue(recentFills.total_volume)} · top ${compactValue(recentFills.top_symbol)}`}
              tone={Number(recentFills.count ?? 0) > 0 ? "info" : "neutral"}
            />
            <StatCard
              label="Long / short"
              value={`${formatNumber(Number(recentFills.buy_count ?? 0))} / ${formatNumber(Number(recentFills.sell_count ?? 0))}`}
              hint={recentFills.latest_at ? `Latest fill ${formatDateTime(recentFills.latest_at)}` : "No recent fill timestamp"}
              tone="neutral"
            />
            <StatCard
              label="Recent exits"
              value={formatNumber(Number(recentExits.count ?? 0))}
              hint={`${formatNumber(Number(recentExits.win_count ?? 0))} win · ${formatNumber(Number(recentExits.loss_count ?? 0))} loss`}
              tone={Number(recentExits.count ?? 0) > 0 ? "success" : "neutral"}
            />
            <StatCard
              label="Exit net PnL"
              value={formatCurrency(Number(recentExits.net_pnl ?? 0))}
              hint={recentExits.latest_at ? `Latest exit ${formatDateTime(recentExits.latest_at)} · top ${compactValue(recentExits.top_symbol)}` : "No recent exit timestamp"}
              tone={toneFromSignedNumber(Number(recentExits.net_pnl ?? 0))}
            />
          </section>

          <div className="detail-grid-2">
            <DataTable
              columns={["Fill time", "Strategy", "Side / symbol", "Volume", "Price"]}
              rows={(recentFills.recent ?? []).map((fill) => [
                compactValue(formatDateTime(fill.timestamp)),
                compactValue(fill.strategy_name),
                <div key={`${compactValue(fill.ticket)}-fill-side`} className="table-stack">
                  <strong>{compactValue(fill.side)}</strong>
                  <span>{compactValue(fill.symbol)}</span>
                </div>,
                compactValue(fill.volume),
                compactValue(fill.price),
              ])}
              emptyTitle="No recent fills"
              emptyDescription="The latest execution window did not surface any recent fill traces from trades.log."
            />

            <DataTable
              columns={["Exit time", "Strategy", "Symbol", "PnL", "Context"]}
              rows={(recentExits.recent ?? []).map((exit) => [
                compactValue(formatDateTime(exit.timestamp)),
                compactValue(exit.strategy_name),
                compactValue(exit.symbol),
                <strong key={`${compactValue(exit.ticket)}-exit-pnl`} className={`tone-${toneFromSignedNumber(Number(exit.pnl ?? 0))}`}>{formatCurrency(Number(exit.pnl ?? 0))}</strong>,
                <div key={`${compactValue(exit.ticket)}-exit-context`} className="table-stack">
                  <span>{compactValue(exit.session)}</span>
                  <span>{compactValue(exit.regime)}</span>
                </div>,
              ])}
              emptyTitle="No recent exits"
              emptyDescription="The trade-context journal did not surface any recent exit rows inside the active lookback window."
            />
          </div>
        </div>
      </Section>

      <Section
        title="Execution diagnosis summary"
        description="Compact interpretation of the current execution snapshot using existing backend fields only."
        action={
          <StatusBadge
            label={Boolean(data.live_state.locked_for_day) ? "No-trade context: day lock" : "No-trade context: runtime readout"}
            tone={Boolean(data.live_state.locked_for_day) ? "warning" : "info"}
          />
        }
      >
        <div className="diagnosis-grid">
          {diagnosisItems.map((item) => (
            <article key={item.label} className={`panel diagnosis-card tone-${item.tone}`}>
              <StatusBadge label={item.label} tone={item.tone} />
              <p>{item.detail}</p>
            </article>
          ))}
        </div>
      </Section>

      <Section
        title="No-trade diagnosis breakdown"
        description="Cause-by-cause readout explaining whether inactivity is intentional, telemetry-driven, or simply a flat execution window."
        action={
          noTradeDiagnosis.posture ? (
            <StatusBadge
              label={`Posture: ${String(noTradeDiagnosis.posture).replace(/_/g, " ")}`}
              tone={noTradeDiagnosis.posture === "telemetry_gap" ? "critical" : noTradeDiagnosis.posture === "locked" || noTradeDiagnosis.posture === "inactive_watch" ? "warning" : noTradeDiagnosis.posture === "engaged" ? "info" : "success"}
            />
          ) : undefined
        }
      >
        <div className="dashboard-stack">
          <section className="stats-grid">
            <StatCard
              label="Primary cause"
              value={compactValue(noTradeDiagnosis.primary_cause ?? noTradeDiagnosis.headline ?? "—")}
              hint={compactValue(noTradeDiagnosis.detail ?? "No diagnosis detail")}
              tone={activeNoTradeCauses.length > 0 ? "warning" : "success"}
            />
            <StatCard
              label="Active causes"
              value={formatNumber(Number(noTradeDiagnosis.active_cause_count ?? activeNoTradeCauses.length))}
              hint={`${formatNumber(noTradeCauses.length)} cause row(s) evaluated`}
              tone={activeNoTradeCauses.length > 0 ? "warning" : "success"}
            />
            <StatCard
              label="Open / fills"
              value={`${formatNumber(Number(data.open_trades.count ?? 0))} / ${formatNumber(Number(recentFills.count ?? 0))}`}
              hint={`Open trades vs fills in last ${formatNumber(recentWindowHours)}h`}
              tone={Number(data.open_trades.count ?? 0) > 0 || Number(recentFills.count ?? 0) > 0 ? "info" : "warning"}
            />
            <StatCard
              label="Live telemetry"
              value={formatNumber(Number(data.strategy_live_stats.strategy_count ?? 0))}
              hint={`${formatNumber(Number(data.strategy_live_stats.total_trades ?? 0))} total live trade(s)`}
              tone={Number(data.strategy_live_stats.strategy_count ?? 0) > 0 ? "success" : "critical"}
            />
          </section>

          {noTradeDiagnosis.headline ? (
            <InlineNotice
              tone={activeNoTradeCauses.length > 0 ? "warning" : "info"}
              title={String(noTradeDiagnosis.headline)}
              description={String(noTradeDiagnosis.detail ?? "")}
            />
          ) : null}

          {noTradeCauses.length ? (
            <div className="execution-incident-grid">
              {noTradeCauses.map((cause) => (
                <article key={cause.key} className={`panel execution-incident-card tone-${cause.tone}`}>
                  <div className="execution-incident-header">
                    <div>
                      <span className="execution-incident-eyebrow">Inactivity cause</span>
                      <h4>{compactValue(cause.label)}</h4>
                    </div>
                    <StatusBadge label={compactValue(cause.status)} tone={cause.tone} />
                  </div>
                  <p className="execution-incident-copy">{compactValue(cause.detail ?? cause.evidence ?? "No operator meaning supplied")}</p>
                  <div className="execution-incident-meta">
                    <div>
                      <span>Evidence</span>
                      <strong>{compactValue(cause.evidence ?? "No evidence")}</strong>
                    </div>
                    <div>
                      <span>Lane</span>
                      <strong>{compactValue(cause.key)}</strong>
                    </div>
                  </div>
                </article>
              ))}
            </div>
          ) : null}

          <DataTable
            columns={["Cause", "Status", "Evidence", "Operator meaning"]}
            rows={noTradeCauses.map((cause) => [
              <div key={`${cause.key}-label`} className="table-stack">
                <strong>{compactValue(cause.label)}</strong>
                <span>{compactValue(cause.key)}</span>
              </div>,
              <div key={`${cause.key}-status`} className="table-stack">
                <StatusBadge label={compactValue(cause.status)} tone={cause.tone} />
                <span>{compactValue(cause.tone)}</span>
              </div>,
              compactValue(cause.evidence),
              compactValue(cause.detail),
            ])}
            emptyTitle="No no-trade causes shaped"
            emptyDescription="The execution payload did not return a cause breakdown for inactivity diagnosis."
          />
        </div>
      </Section>

      <Section title="Stale execution artifact warnings" description="Freshness check across the core runtime artifacts that feed execution posture, trade explainability, and reconciliation surfaces.">
        <div className="dashboard-stack">
          <section className="stats-grid">
            <StatCard
              label="Critical stale"
              value={formatNumber(Number(executionArtifactWarnings.critical_count ?? 0))}
              hint="Artifacts beyond the critical freshness threshold"
              tone={Number(executionArtifactWarnings.critical_count ?? 0) > 0 ? "critical" : "success"}
            />
            <StatCard
              label="Needs review"
              value={formatNumber(Number(executionArtifactWarnings.warning_count ?? 0))}
              hint="Artifacts beyond the watch threshold"
              tone={Number(executionArtifactWarnings.warning_count ?? 0) > 0 ? "warning" : "neutral"}
            />
            <StatCard
              label="Missing"
              value={formatNumber(Number(executionArtifactWarnings.missing_count ?? 0))}
              hint="Execution artifacts not found on disk"
              tone={Number(executionArtifactWarnings.missing_count ?? 0) > 0 ? "critical" : "success"}
            />
            <StatCard
              label="Healthy"
              value={formatNumber(Number(executionArtifactWarnings.healthy_count ?? 0))}
              hint="Artifacts currently inside their freshness window"
              tone="success"
            />
          </section>

          {executionArtifactWarnings.headline ? (
            <InlineNotice
              tone={(executionArtifactWarnings.tone as "neutral" | "info" | "success" | "warning" | "critical") ?? "info"}
              title={String(executionArtifactWarnings.headline)}
              description="Use this table to separate truly stale runtime evidence from quiet low-traffic artifacts before trusting the downstream execution and reconciliation readouts."
            />
          ) : null}

          <DataTable
            columns={["Artifact", "Freshness", "Status", "What it affects"]}
            rows={executionArtifactRows.map((artifact) => [
              <div key={`${compactValue(artifact.key)}-artifact`} className="table-stack">
                <strong>{compactValue(artifact.label)}</strong>
                <span>{compactValue(artifact.note)}</span>
              </div>,
              <div key={`${compactValue(artifact.key)}-freshness`} className="table-stack">
                <strong>{artifact.observed_at ? formatDateTime(artifact.observed_at) : "No timestamp"}</strong>
                <span>{artifact.observed_at ? formatRelativeAge(artifact.observed_at) : compactValue(artifact.path)}</span>
              </div>,
              <div key={`${compactValue(artifact.key)}-status`} className="table-stack">
                <StatusBadge
                  label={String(artifact.status ?? "unknown").replace(/_/g, " ")}
                  tone={(artifact.tone as "neutral" | "info" | "success" | "warning" | "critical") ?? "neutral"}
                />
                <span>{compactValue(artifact.detail)}</span>
              </div>,
              <div key={`${compactValue(artifact.key)}-meaning`} className="table-stack">
                <span>{compactValue(artifact.operator_meaning)}</span>
                <span>{compactValue(artifact.path)}</span>
              </div>,
            ])}
            emptyTitle="No execution artifact warnings shaped"
            emptyDescription="The execution payload did not return artifact freshness diagnostics for this snapshot."
          />
        </div>
      </Section>

      <Section title="Operator attention lanes" description="Quick visual grouping of the execution issues most likely to need immediate intervention or deeper diagnosis.">
        <div className="attention-grid">
          <AttentionCard
            label="No-trade pressure"
            value={formatNumber(Number(noTradeDiagnosis.active_cause_count ?? activeNoTradeCauses.length))}
            detail={String(noTradeDiagnosis.headline ?? "No active no-trade cause is dominating this execution snapshot.")}
            tone={activeNoTradeCauses.length > 0 ? "warning" : "success"}
          />
          <AttentionCard
            label="Stale artifacts"
            value={formatNumber(Number(executionArtifactWarnings.critical_count ?? 0))}
            detail="Critical freshness misses can distort downstream posture, reconciliation, and operator trust in the snapshot."
            tone={Number(executionArtifactWarnings.critical_count ?? 0) > 0 ? "critical" : "success"}
          />
          <AttentionCard
            label="Context registration failures"
            value={formatNumber(Number(tradeContextRegistrationFailures.count ?? 0))}
            detail="Journal registration errors strip away execution evidence and weaken exit explainability."
            tone={Number(tradeContextRegistrationFailures.count ?? 0) > 0 ? "warning" : "success"}
          />
          <AttentionCard
            label="Unmatched closed deals"
            value={formatNumber(Number(unmatchedSummary.count ?? data.unmatched_closed_deals.count ?? 0))}
            detail="Closed-deal backlog is the clearest signal that reconciliation confidence is slipping and may need manual help."
            tone={Number(unmatchedSummary.count ?? data.unmatched_closed_deals.count ?? 0) > 0 ? "critical" : "success"}
          />
        </div>
      </Section>

      <Section title="Live posture" description="Raw execution-level state from the backend UI API.">
        {Object.keys(data.live_state ?? {}).length ? (
          <KeyValueGrid data={data.live_state} />
        ) : (
          <EmptyState
            title="Live state missing"
            description="The execution endpoint responded, but no live_state object was included. That weakens no-trade diagnosis and backend posture visibility."
          />
        )}
      </Section>

      <Section title="Recent attention events" description="Latest high-signal execution and audit events promoted near the top for operator triage.">
        <DataTable
          columns={["Time", "Source", "Summary", "Symbol / PnL"]}
          rows={attentionEvents.map((event) => [
            formatDateTime(event.recorded_at ?? event.last_update ?? event.timestamp),
            compactValue(event.source),
            summarizeEvent(event),
            compactValue(event.symbol ?? event.profit ?? event.floating_pnl),
          ])}
          emptyTitle="No recent attention events"
          emptyDescription="The recent audit/runtime feed does not currently show unmatched-close or trade-log events that need promotion here."
        />
      </Section>

      <Section title="Top live strategies snapshot" description="Most active live strategies according to the execution summary.">
        <DataTable
          columns={["Strategy", "Trades", "PnL", "Last update", "Recent PnLs"]}
          rows={(data.strategy_live_stats.top_active ?? []).map((item) => [
            compactValue(item.name ?? item.strategy_name),
            compactValue(item.num_trades ?? item.total_trades),
            compactValue(item.total_pnl ?? item.realized_pnl ?? item.pnl),
            compactValue(formatDateTime(item.last_update)),
            compactValue(item.recent_pnls),
          ])}
          emptyTitle="No live strategy rows"
          emptyDescription="The execution summary did not return top_active strategies. Either runtime stats are empty or the backend did not shape them into the payload."
        />
      </Section>

      <Section title="Open trade ledger" description="Current open-trade records returned by the execution summary endpoint.">
        <DataTable
          columns={["Symbol", "Side", "Volume", "Open time", "Floating PnL"]}
          rows={(data.open_trades.trades ?? []).map((trade) => [
            compactValue(trade.symbol),
            compactValue(trade.side ?? trade.direction),
            compactValue(trade.volume ?? trade.lots),
            compactValue(formatDateTime(trade.open_time ?? trade.opened_at)),
            compactValue(trade.floating_pnl ?? trade.pnl ?? trade.profit),
          ])}
          emptyTitle="No open trades"
          emptyDescription="The latest execution snapshot reports zero open positions. If that is unexpected, inspect the diagnosis summary and recent attention events above."
        />
      </Section>

      <Section title="Open trade posture" description="Execution-facing breakdown of live positions by symbol, protection state, age, and floating pressure.">
        <div className="dashboard-stack">
          <section className="stats-grid">
            <StatCard label="Symbols engaged" value={formatNumber(Number(openTradeSummary.symbol_count ?? 0))} hint="Symbols with at least one open trade" tone="info" />
            <StatCard
              label="Net floating PnL"
              value={formatCurrency(Number(openTradeSummary.net_floating_pnl ?? 0))}
              hint={`${formatNumber(Number(openTradeSummary.floating_loss_count ?? 0))} trade(s) underwater`}
              tone={toneFromSignedNumber(Number(openTradeSummary.net_floating_pnl ?? 0))}
            />
            <StatCard
              label="Protection coverage"
              value={`${formatNumber(Number(openTradeSummary.protected_count ?? 0))} / ${formatNumber(Number(data.open_trades.count ?? 0))}`}
              hint={`${formatNumber(Number(openTradeSummary.incomplete_protection_count ?? 0))} need SL/TP review`}
              tone={Number(openTradeSummary.incomplete_protection_count ?? 0) > 0 ? "warning" : "success"}
            />
            <StatCard
              label="Aged / stale"
              value={`${formatNumber(Number(openTradeSummary.aged_trade_count ?? 0))} / ${formatNumber(Number(openTradeSummary.stale_update_count ?? 0))}`}
              hint="Held over 4h / update lag over 60m"
              tone={Number(openTradeSummary.aged_trade_count ?? 0) > 0 || Number(openTradeSummary.stale_update_count ?? 0) > 0 ? "warning" : "neutral"}
            />
          </section>

          {openTradeBySymbol.length ? (
            <div className="execution-posture-grid">
              {openTradeBySymbol.map((row) => {
                const symbol = String(row.symbol ?? "unknown");
                const symbolTrades = openTradeDrilldown.filter((trade) => String(trade.symbol ?? "") === symbol);
                const posture = buildSymbolPosture(symbolTrades);
                return (
                  <article key={`${symbol}-posture-card`} className={`panel execution-posture-card tone-${posture.tone}`}>
                    <div className="execution-posture-topline">
                      <div>
                        <span className="execution-posture-eyebrow">Symbol posture</span>
                        <h4>{symbol}</h4>
                      </div>
                      <StatusBadge label={posture.label} tone={posture.tone} />
                    </div>

                    <div className="execution-posture-metrics">
                      <div>
                        <span>Net floating</span>
                        <strong className={`tone-${toneFromSignedNumber(Number(row.net_floating_pnl ?? 0))}`}>{formatCurrency(Number(row.net_floating_pnl ?? 0))}</strong>
                      </div>
                      <div>
                        <span>Exposure</span>
                        <strong>{formatNumber(Number(row.open_trade_count ?? 0))} trade(s) · vol {compactValue(row.total_volume)}</strong>
                      </div>
                      <div>
                        <span>Structure</span>
                        <strong>{formatNumber(posture.longCount)} long · {formatNumber(posture.shortCount)} short</strong>
                      </div>
                      <div>
                        <span>Oldest position</span>
                        <strong>{formatDurationMinutes(typeof row.oldest_age_minutes === "number" ? row.oldest_age_minutes : Number.NaN)}</strong>
                      </div>
                    </div>

                    <div className="badge-row">
                      <StatusBadge
                        label={posture.incompleteProtectionCount > 0 ? `${formatNumber(posture.incompleteProtectionCount)} incomplete SL/TP` : "Protection covered"}
                        tone={posture.incompleteProtectionCount > 0 ? "critical" : "success"}
                      />
                      <StatusBadge
                        label={Number(row.floating_loss_count ?? 0) > 0 ? `${formatNumber(Number(row.floating_loss_count ?? 0))} floating loss` : "No underwater trades"}
                        tone={Number(row.floating_loss_count ?? 0) > 0 ? "warning" : "success"}
                      />
                      <StatusBadge
                        label={posture.agedCount > 0 ? `${formatNumber(posture.agedCount)} aged > 4h` : "Age within 4h"}
                        tone={posture.agedCount > 0 ? "warning" : "info"}
                      />
                      <StatusBadge
                        label={posture.staleUpdateCount > 0 ? `${formatNumber(posture.staleUpdateCount)} stale update` : "Fresh update trail"}
                        tone={posture.staleUpdateCount > 0 ? "critical" : "info"}
                      />
                    </div>

                    <p className="execution-posture-copy">
                      {Array.isArray(row.strategies) && row.strategies.length ? row.strategies.join(", ") : "No strategy names surfaced"}
                    </p>
                    <p className="execution-posture-copy">
                      {posture.noRecentLogCount > 0 || posture.missingLiveStatsCount > 0
                        ? `${formatNumber(posture.noRecentLogCount)} trade(s) missing recent log match, ${formatNumber(posture.missingLiveStatsCount)} trade(s) missing live stats.`
                        : `Recent logs and live stats align for the visible ${formatNumber(Number(row.open_trade_count ?? 0))} trade(s).`}
                    </p>
                  </article>
                );
              })}
            </div>
          ) : null}

          <DataTable
            columns={["Symbol", "Open trades", "Net floating", "Volume", "Strategies", "Oldest position"]}
            rows={openTradeBySymbol.map((row) => [
              compactValue(row.symbol),
              compactValue(row.open_trade_count),
              <div key={`${compactValue(row.symbol)}-pnl`} className="table-stack">
                <strong className={`tone-${toneFromSignedNumber(Number(row.net_floating_pnl ?? 0))}`}>{formatCurrency(Number(row.net_floating_pnl ?? 0))}</strong>
                <span>{formatNumber(Number(row.floating_loss_count ?? 0))} loss-making trade(s)</span>
              </div>,
              compactValue(row.total_volume),
              <div key={`${compactValue(row.symbol)}-strategies`} className="table-stack">
                <strong>{formatNumber(Number(row.strategy_count ?? 0))}</strong>
                <span>{Array.isArray(row.strategies) && row.strategies.length ? row.strategies.join(", ") : "—"}</span>
              </div>,
              <div key={`${compactValue(row.symbol)}-age`} className="table-stack">
                <strong>{formatDurationMinutes(typeof row.oldest_age_minutes === "number" ? row.oldest_age_minutes : Number.NaN)}</strong>
                <span>{formatDateTime(typeof row.oldest_open_time === "string" ? row.oldest_open_time : undefined)}</span>
              </div>,
            ])}
            emptyTitle="No symbol posture yet"
            emptyDescription="There are no open positions to aggregate by symbol in this snapshot."
          />
        </div>
      </Section>

      <Section title="Open trade drilldown" description="Per-position operator context including hold age, protection completeness, live strategy context, and flags that deserve review.">
        <DataTable
          columns={["Strategy", "Position", "Live context", "Protection", "Flags"]}
          rows={openTradeDrilldown.map((trade) => [
            <div key={`${compactValue(trade.ticket)}-strategy`} className="table-stack">
              <strong>{compactValue(trade.strategy_name ?? trade.comment)}</strong>
              <span>{compactValue(trade.symbol)}</span>
            </div>,
            <div key={`${compactValue(trade.ticket)}-position`} className="table-stack">
              <strong className={`tone-${toneFromSignedNumber(Number(trade.floating_pnl ?? 0))}`}>{formatCurrency(Number(trade.floating_pnl ?? 0))}</strong>
              <span>{compactValue(trade.side)} · vol {compactValue(trade.volume)} · held {formatDurationMinutes(typeof trade.holding_minutes === "number" ? trade.holding_minutes : Number.NaN)}</span>
              <span>Opened {formatDateTime(typeof trade.open_time === "string" ? trade.open_time : undefined)} at {compactValue(trade.open_price)}</span>
            </div>,
            <div key={`${compactValue(trade.ticket)}-live`} className="table-stack">
              <strong>{formatNumber(typeof trade.live_num_trades === "number" ? trade.live_num_trades : undefined)} live trades</strong>
              <span>Realized {formatCurrency(typeof trade.live_total_pnl === "number" ? trade.live_total_pnl : undefined)}</span>
              <span>Recent PnLs {compactValue(trade.recent_realized_pnls)}</span>
            </div>,
            <div key={`${compactValue(trade.ticket)}-protection`} className="table-stack">
              <strong className={`tone-${toneFromProtectionStatus(trade.protection_status)}`}>{labelForProtectionStatus(trade.protection_status)}</strong>
              <span>SL {compactValue(trade.sl)} · TP {compactValue(trade.tp)}</span>
              <span>R:R {compactValue(trade.risk_reward)} · update lag {formatDurationMinutes(typeof trade.minutes_since_update === "number" ? trade.minutes_since_update : Number.NaN)}</span>
            </div>,
            <div key={`${compactValue(trade.ticket)}-flags`} className="table-stack">
              <div className="badge-row">
                {Array.isArray(trade.operator_flags) && trade.operator_flags.length ? (
                  trade.operator_flags.map((flag) => (
                    <StatusBadge
                      key={`${compactValue(trade.ticket)}-${String(flag)}`}
                      label={String(flag).replace(/_/g, " ")}
                      tone={String(flag).includes("loss") || String(flag).includes("unprotected") ? "critical" : String(flag).includes("incomplete") || String(flag).includes("aged") || String(flag).includes("stale") ? "warning" : "info"}
                    />
                  ))
                ) : (
                  <StatusBadge label="No review flags" tone="success" />
                )}
              </div>
              <span>Ticket {compactValue(trade.ticket ?? trade.position_id)}</span>
            </div>,
          ])}
          emptyTitle="No enriched open-trade rows"
          emptyDescription="There are no current positions to enrich with operator drilldown context."
        />
      </Section>

      <Section title="Recent trade-context registration failures" description="Latest exceptions raised while the runtime tried to attach entry or exit context into the trade-context journal.">
        <div className="dashboard-stack">
          <section className="stats-grid">
            <StatCard
              label="Failures captured"
              value={formatNumber(Number(tradeContextRegistrationFailures.count ?? 0))}
              hint={tradeContextRegistrationFailures.latest_at ? `Latest ${formatDateTime(String(tradeContextRegistrationFailures.latest_at))}` : "No recent registration exceptions found in scanned system logs"}
              tone={Number(tradeContextRegistrationFailures.count ?? 0) > 0 ? "warning" : "success"}
            />
            <StatCard
              label="Entry / exit"
              value={`${formatNumber(Number(tradeContextRegistrationFailures.entry_count ?? 0))} / ${formatNumber(Number(tradeContextRegistrationFailures.exit_count ?? 0))}`}
              hint="Entry context failures first, exit context failures second"
              tone="neutral"
            />
            <StatCard
              label="Unique strategies"
              value={formatNumber(registrationFailureStrategies.length)}
              hint={Array.isArray(tradeContextRegistrationFailures.files_scanned) && tradeContextRegistrationFailures.files_scanned.length ? `Logs ${tradeContextRegistrationFailures.files_scanned.join(", ")}` : "System log scan metadata unavailable"}
              tone="info"
            />
            <StatCard
              label="Top cause bucket"
              value={compactValue(registrationFailureCauses[0]?.key ?? "none")}
              hint={registrationFailureCauses.length ? `${formatNumber(Number(registrationFailureCauses[0]?.count ?? 0))} hit(s) in the recent panel` : "No cause buckets to summarize"}
              tone={registrationFailureCauses.length ? "warning" : "neutral"}
            />
          </section>

          {Number(tradeContextRegistrationFailures.count ?? 0) > 0 ? (
            <InlineNotice
              tone="warning"
              title="Trade-context journal registration is dropping runtime evidence"
              description="These failures usually weaken exit attribution and recent fill-to-journal explainability. Clear the dominant cause before trusting downstream reconciliation surfaces." 
            />
          ) : (
            <InlineNotice
              tone="success"
              title="No recent registration failures found"
              description="The scanned system logs did not show entry/exit context registration exceptions, so trade-context enrichment looks quiet from this slice."
            />
          )}

          {registrationFailureRecent.length ? (
            <div className="execution-incident-grid">
              {registrationFailureRecent.slice(0, 6).map((row) => {
                const causeTone = toneFromRegistrationFailureCause(row.cause_key);
                return (
                  <article key={`${compactValue(row.ticket)}-${compactValue(row.phase)}-incident`} className={`panel execution-incident-card tone-${causeTone}`}>
                    <div className="execution-incident-header">
                      <div>
                        <span className="execution-incident-eyebrow">Registration incident</span>
                        <h4>{compactValue(row.strategy_name)}</h4>
                      </div>
                      <StatusBadge label={compactValue(row.phase ?? "unknown phase")} tone={causeTone} />
                    </div>
                    <p className="execution-incident-copy">{compactValue(row.cause_detail ?? row.message ?? "No cause detail")}</p>
                    <div className="execution-incident-meta">
                      <div>
                        <span>Ticket</span>
                        <strong>{compactValue(row.ticket ?? row.ticket_label)}</strong>
                      </div>
                      <div>
                        <span>Cause</span>
                        <strong>{compactValue(row.cause_key ?? row.cause)}</strong>
                      </div>
                      <div>
                        <span>When</span>
                        <strong>{compactValue(formatDateTime(typeof row.timestamp === "string" ? row.timestamp : undefined))}</strong>
                      </div>
                      <div>
                        <span>Trace hint</span>
                        <strong>{Array.isArray(row.traceback) && row.traceback.length ? compactValue(row.traceback[row.traceback.length - 1]) : "No traceback lines"}</strong>
                      </div>
                    </div>
                  </article>
                );
              })}
            </div>
          ) : null}

          <div className="detail-grid-2">
            <DataTable
              columns={["Cause bucket", "Count"]}
              rows={registrationFailureCauses.map((row) => [compactValue(row.key), formatNumber(Number(row.count ?? 0))])}
              emptyTitle="No failure causes"
              emptyDescription="No recent registration exceptions were parsed from the available system logs."
            />

            <DataTable
              columns={["Strategy", "Count"]}
              rows={registrationFailureStrategies.map((row) => [compactValue(row.strategy_name), formatNumber(Number(row.count ?? 0))])}
              emptyTitle="No impacted strategies"
              emptyDescription="The current log scan did not surface any strategy-specific registration failures."
            />
          </div>

          <DataTable
            columns={["When", "Strategy / phase", "Ticket", "Cause", "Traceback hint"]}
            rows={registrationFailureRecent.map((row) => [
              compactValue(formatDateTime(typeof row.timestamp === "string" ? row.timestamp : undefined)),
              <div key={`${compactValue(row.ticket)}-${compactValue(row.phase)}-phase`} className="table-stack">
                <strong>{compactValue(row.strategy_name)}</strong>
                <span>{compactValue(row.phase)} context</span>
              </div>,
              <div key={`${compactValue(row.ticket)}-${compactValue(row.phase)}-ticket`} className="table-stack">
                <strong>{compactValue(row.ticket)}</strong>
                <span>{compactValue(row.ticket_label)}</span>
                <span>{compactValue(row.log_file)}</span>
              </div>,
              <div key={`${compactValue(row.ticket)}-${compactValue(row.phase)}-cause`} className="table-stack">
                <StatusBadge
                  label={compactValue(row.cause_key)}
                  tone={toneFromRegistrationFailureCause(row.cause_key)}
                />
                <span>{compactValue(row.cause_detail)}</span>
                <span>{compactValue(row.cause)}</span>
              </div>,
              <div key={`${compactValue(row.ticket)}-${compactValue(row.phase)}-trace`} className="table-stack">
                <span>{Array.isArray(row.traceback) && row.traceback.length ? compactValue(row.traceback[row.traceback.length - 1]) : "No traceback lines captured"}</span>
                <span>{compactValue(row.message)}</span>
              </div>,
            ])}
            emptyTitle="No recent registration failures"
            emptyDescription="The execution logs did not show trade-context journal registration exceptions in the scanned files."
          />
        </div>
      </Section>

      <Section title="Unmatched closed-deal resolution dashboard" description="Operator-facing breakdown of unresolved close attribution, recovery lanes, and the strongest hints available for pairing work.">
        <div className="dashboard-stack">
          <section className="stats-grid">
            <StatCard
              label="Unmatched deals"
              value={formatNumber(Number(unmatchedSummary.count ?? data.unmatched_closed_deals.count ?? 0))}
              hint={unmatchedSummary.newest_recorded_at ? `Latest ${formatDateTime(String(unmatchedSummary.newest_recorded_at))}` : "Closed-deal reconciliation is currently quiet"}
              tone={Number(unmatchedSummary.count ?? data.unmatched_closed_deals.count ?? 0) > 0 ? "warning" : "success"}
            />
            <StatCard
              label="Recoverable"
              value={formatNumber(Number(unmatchedSummary.recoverable_count ?? 0))}
              hint={`${formatNumber(Number(unmatchedSummary.ambiguous_count ?? 0))} ambiguous candidate set(s)`}
              tone={Number(unmatchedSummary.recoverable_count ?? 0) > 0 ? "info" : "neutral"}
            />
            <StatCard
              label="Manual fallback"
              value={formatNumber(Number(unmatchedSummary.manual_bucket_only_count ?? unmatchedSummary.manual_bucket_count ?? 0))}
              hint={`${formatNumber(Number(unmatchedSummary.symbols_affected ?? 0))} symbol(s) affected`}
              tone={Number(unmatchedSummary.manual_bucket_only_count ?? unmatchedSummary.manual_bucket_count ?? 0) > 0 ? "critical" : "neutral"}
            />
            <StatCard
              label="Journal context"
              value={formatNumber(Number(unmatchedSummary.journal_context_count ?? 0))}
              hint={unmatchedSummary.oldest_recorded_at ? `Oldest ${formatDateTime(String(unmatchedSummary.oldest_recorded_at))}` : "No unresolved aging backlog"}
              tone={Number(unmatchedSummary.journal_context_count ?? 0) > 0 ? "info" : "neutral"}
            />
          </section>

          {Number(unmatchedSummary.count ?? data.unmatched_closed_deals.count ?? 0) > 0 ? (
            <InlineNotice
              tone="warning"
              title="Reconciliation backlog needs operator review"
              description="Use the lane table to separate single-candidate recoveries from ambiguous/manual-bucket cases before digging into raw audit rows."
            />
          ) : null}

          {unmatchedRecent.length ? (
            <div className="execution-dossier-grid">
              {unmatchedRecent.slice(0, 6).map((deal) => {
                const dealTone = toneFromUnmatchedDeal(deal);
                return (
                  <article key={`${compactValue(deal.deal_ticket ?? deal.position_id)}-dossier`} className={`panel execution-dossier-card tone-${dealTone}`}>
                    <div className="execution-dossier-header">
                      <div className="execution-dossier-heading">
                        <span className="execution-dossier-eyebrow">Closed-deal dossier</span>
                        <h4>{compactValue(deal.symbol)}</h4>
                        <p>
                          Deal {compactValue(deal.deal_ticket ?? deal.ticket)} · position {compactValue(deal.position_id)}
                        </p>
                      </div>
                      <div className="execution-dossier-badges">
                        <StatusBadge label={compactValue(deal.resolution_label ?? deal.resolution_lane)} tone={dealTone} />
                        <StatusBadge label={`Confidence ${compactValue(deal.pairing_confidence ?? "unknown")}`} tone={dealTone} />
                      </div>
                    </div>

                    <div className="execution-dossier-metrics">
                      <div>
                        <span>PnL</span>
                        <strong className={`tone-${toneFromSignedNumber(Number(deal.profit ?? deal.pnl ?? 0))}`}>{formatCurrency(Number(deal.profit ?? deal.pnl ?? 0))}</strong>
                      </div>
                      <div>
                        <span>Pairing score</span>
                        <strong>{formatNumber(Number(deal.pairing_score ?? 0))}</strong>
                      </div>
                      <div>
                        <span>Evidence</span>
                        <strong>{formatNumber(Number(deal.ticket_alias_count ?? 0))} alias hint(s)</strong>
                      </div>
                      <div>
                        <span>Age</span>
                        <strong>{deal.age_minutes != null ? formatDurationMinutes(Number(deal.age_minutes)) : "Unknown age"}</strong>
                      </div>
                    </div>

                    <div className="badge-row">
                      <StatusBadge label={deal.has_comment_uid4 ? "Comment UID present" : "No comment UID"} tone={deal.has_comment_uid4 ? "success" : "warning"} />
                      <StatusBadge label={deal.journal_context_present ? `Journal ${compactValue(deal.journal_strategy_name)}` : "No journal hit"} tone={deal.journal_context_present ? "info" : "critical"} />
                    </div>

                    <div className="execution-dossier-footer">
                      <div className="execution-dossier-copy">
                        <span className="execution-dossier-label">Resolution read</span>
                        <p>{compactValue(deal.resolution_detail ?? deal.pairing_confidence_detail ?? "No resolution detail")}</p>
                      </div>
                      <div className="execution-dossier-copy">
                        <span className="execution-dossier-label">Strategy hints</span>
                        <p>{Array.isArray(deal.candidate_matches) && deal.candidate_matches.length ? deal.candidate_matches.join(", ") : compactValue(deal.manual_bucket ?? deal.reason ?? "No candidate strategies")}</p>
                      </div>
                    </div>
                  </article>
                );
              })}
            </div>
          ) : null}

          <div className="detail-grid-2">
            <DataTable
              columns={["Resolution lane", "Count", "Tone", "Operator meaning"]}
              rows={unmatchedLanes.map((lane) => [
                <div key={`${compactValue(lane.key)}-lane`} className="table-stack">
                  <strong>{compactValue(lane.label)}</strong>
                  <span>{compactValue(lane.key)}</span>
                </div>,
                formatNumber(Number(lane.count ?? 0)),
                <StatusBadge key={`${compactValue(lane.key)}-tone`} label={compactValue(lane.tone)} tone={lane.tone as "neutral" | "info" | "success" | "warning" | "critical"} />,
                compactValue(lane.detail),
              ])}
              emptyTitle="No resolution lanes"
              emptyDescription="There are no unresolved close rows to classify right now."
            />

            <DataTable
              columns={["Symbol", "Deals", "Recoverable", "Net PnL", "Latest"]}
              rows={unmatchedSymbols.map((row) => [
                compactValue(row.symbol),
                formatNumber(Number(row.count ?? 0)),
                formatNumber(Number(row.recoverable_count ?? 0)),
                <strong key={`${compactValue(row.symbol)}-profit`} className={`tone-${toneFromSignedNumber(Number(row.profit ?? 0))}`}>{formatCurrency(Number(row.profit ?? 0))}</strong>,
                compactValue(formatDateTime(row.latest_recorded_at)),
              ])}
              emptyTitle="No symbol hotspots"
              emptyDescription="No unresolved backlog means there is nothing to cluster by symbol yet."
            />
          </div>

          <div className="detail-grid-2">
            <DataTable
              columns={["Pairing confidence", "Count", "Tone", "Operator meaning"]}
              rows={unmatchedConfidenceBuckets.map((bucket) => [
                compactValue(bucket.label ?? bucket.key),
                formatNumber(Number(bucket.count ?? 0)),
                <StatusBadge key={`${compactValue(bucket.key)}-confidence`} label={compactValue(bucket.tone)} tone={bucket.tone as "neutral" | "info" | "success" | "warning" | "critical"} />,
                compactValue(bucket.detail),
              ])}
              emptyTitle="No confidence buckets"
              emptyDescription="No unresolved rows are currently available to explain pairing confidence."
            />

            <DataTable
              columns={["Signal", "Count", "Impact", "Why it matters"]}
              rows={unmatchedConfidenceSignals.map((signal) => [
                compactValue(signal.label ?? signal.key),
                formatNumber(Number(signal.count ?? 0)),
                <StatusBadge
                  key={`${compactValue(signal.key)}-impact`}
                  label={compactValue(signal.impact)}
                  tone={signal.impact === "positive" ? "success" : signal.impact === "negative" ? "critical" : "warning"}
                />,
                compactValue(signal.detail),
              ])}
              emptyTitle="No confidence signals"
              emptyDescription="The current unmatched-close backlog does not yet show explicit pairing evidence signals."
            />
          </div>

          {unmatchedConfidence.heuristic ? (
            <InlineNotice
              tone="info"
              title="How pairing confidence is explained"
              description={compactValue(unmatchedConfidence.heuristic)}
            />
          ) : null}

          <div className="detail-grid-2">
            <DataTable
              columns={["Reason", "Count"]}
              rows={unmatchedReasons.map((row) => [compactValue(row.reason), formatNumber(Number(row.count ?? 0))])}
              emptyTitle="No reason breakdown"
              emptyDescription="The current unmatched-close backlog does not have reason labels to summarize."
            />

            <DataTable
              columns={["Manual bucket", "Count"]}
              rows={unmatchedManualBuckets.map((row) => [compactValue(row.bucket), formatNumber(Number(row.count ?? 0))])}
              emptyTitle="No manual bucket usage"
              emptyDescription="No unresolved rows were forced into manual attribution buckets in this snapshot."
            />
          </div>

          <DataTable
            columns={["Deal", "Resolution", "Evidence", "Strategy hints", "PnL"]}
            rows={unmatchedRecent.map((deal) => [
              <div key={`${compactValue(deal.deal_ticket ?? deal.position_id)}-deal`} className="table-stack">
                <strong>{compactValue(deal.symbol)}</strong>
                <span>Deal {compactValue(deal.deal_ticket ?? deal.ticket)}</span>
                <span>Position {compactValue(deal.position_id)}</span>
              </div>,
              <div key={`${compactValue(deal.deal_ticket ?? deal.position_id)}-resolution`} className="table-stack">
                <StatusBadge
                  label={compactValue(deal.resolution_label ?? deal.resolution_lane)}
                  tone={toneFromUnmatchedDeal(deal)}
                />
                <span>{compactValue(deal.resolution_detail)}</span>
                <span>
                  Confidence {compactValue(deal.pairing_confidence)} · score {formatNumber(Number(deal.pairing_score ?? 0))}
                </span>
                <span>{compactValue(deal.pairing_confidence_detail)}</span>
              </div>,
              <div key={`${compactValue(deal.deal_ticket ?? deal.position_id)}-evidence`} className="table-stack">
                <span>{formatNumber(Number(deal.ticket_alias_count ?? 0))} alias hint(s)</span>
                <span>{deal.has_comment_uid4 ? "Comment UID available" : "No comment UID"}</span>
                <span>{deal.journal_context_present ? `Journal hit ${compactValue(deal.journal_strategy_name)}` : "No journal hit"}</span>
                <span>{deal.age_minutes != null ? `Age ${formatDurationMinutes(Number(deal.age_minutes))}` : "Unknown age"}</span>
              </div>,
              <div key={`${compactValue(deal.deal_ticket ?? deal.position_id)}-hints`} className="table-stack">
                <strong>{Array.isArray(deal.candidate_matches) && deal.candidate_matches.length ? deal.candidate_matches.join(", ") : "No candidate strategies"}</strong>
                <span>{compactValue(deal.manual_bucket ?? "No manual bucket")}</span>
                <span>{compactValue(deal.reason)}</span>
              </div>,
              <strong key={`${compactValue(deal.deal_ticket ?? deal.position_id)}-pnl`} className={`tone-${toneFromSignedNumber(Number(deal.profit ?? deal.pnl ?? 0))}`}>{formatCurrency(Number(deal.profit ?? deal.pnl ?? 0))}</strong>,
            ])}
            emptyTitle="No unmatched closed deals"
            emptyDescription="Closed-deal reconciliation currently looks clean from this route."
          />
        </div>
      </Section>

      <Section title="Recent trade log" description="Latest execution log entries surfaced directly from the UI API.">
        <DataTable
          columns={["Time", "Strategy", "Event", "Symbol", "Detail"]}
          rows={data.recent_trade_log.map((entry) => [
            compactValue(formatDateTime(entry.timestamp ?? entry.recorded_at ?? entry.time)),
            compactValue(entry.strategy_name ?? entry.strategy),
            compactValue(entry.event ?? entry.type),
            compactValue(entry.symbol),
            compactValue(entry.detail ?? entry.message ?? entry.comment ?? entry.raw),
          ])}
          emptyTitle="Recent trade log is empty"
          emptyDescription="The backend returned no recent trade-log lines for this view."
        />
      </Section>
    </div>
  );
}
