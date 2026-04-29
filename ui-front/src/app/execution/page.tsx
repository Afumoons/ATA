"use client";

import { PageHeader } from "@/components/app-shell";
import {
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
import { compactValue, formatCurrency, formatDateTime, formatNumber } from "@/lib/format";
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

      <Section title="Unmatched closed deals" description="Closed deals that have not been cleanly paired or reconciled.">
        <DataTable
          columns={["Symbol", "Ticket", "Closed at", "Reason", "PnL"]}
          rows={(data.unmatched_closed_deals.recent ?? []).map((deal) => [
            compactValue(deal.symbol),
            compactValue(deal.ticket ?? deal.position_id ?? deal.deal_ticket),
            compactValue(formatDateTime(deal.closed_at ?? deal.recorded_at ?? deal.close_time)),
            compactValue(deal.reason ?? deal.comment),
            compactValue(deal.pnl ?? deal.profit),
          ])}
          emptyTitle="No unmatched closed deals"
          emptyDescription="Closed-deal reconciliation currently looks clean from this route."
        />
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
