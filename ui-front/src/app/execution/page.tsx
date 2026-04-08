"use client";

import { PageHeader } from "@/components/app-shell";
import {
  DataTable,
  ErrorState,
  KeyValueGrid,
  LoadingState,
  Section,
  StatCard,
} from "@/components/dashboard";
import { useQuery } from "@/hooks/use-query";
import { uiApi } from "@/lib/api";
import { compactValue, formatCurrency, formatDateTime, formatNumber } from "@/lib/format";

export default function ExecutionPage() {
  const { data, loading, error } = useQuery("execution-summary", uiApi.executionSummary);

  if (loading) return <LoadingState title="Loading execution diagnostics" />;
  if (error || !data) return <ErrorState message={error ?? "Execution diagnostics are unavailable."} />;

  return (
    <div className="dashboard-stack">
      <PageHeader
        title="Execution diagnostics"
        subtitle="Read-only visibility into live execution state, active strategy behaviour, unmatched closes, and recent trade logging."
        meta={`Snapshot ${formatDateTime(data.generated_at)}`}
      />

      <section className="stats-grid">
        <StatCard label="Open trades" value={formatNumber(data.open_trades.count)} hint="Currently open positions" tone="info" />
        <StatCard label="Strategies live" value={formatNumber(data.strategy_live_stats.strategy_count)} hint="Strategies contributing live stats" tone="positive" />
        <StatCard label="Total trades" value={formatNumber(data.strategy_live_stats.total_trades)} hint="Aggregated strategy trade count" />
        <StatCard label="Realized PnL" value={formatCurrency(data.strategy_live_stats.total_realized_pnl)} hint="Reported realized PnL" tone={(data.strategy_live_stats.total_realized_pnl ?? 0) >= 0 ? "positive" : "danger"} />
      </section>

      <Section title="Live state" description="Raw execution-level state from the backend UI API.">
        <KeyValueGrid data={data.live_state} />
      </Section>

      <Section title="Top active strategies" description="Most active live strategies according to the execution summary.">
        <DataTable
          columns={["Strategy", "Symbol", "Timeframe", "Status", "PnL / score"]}
          rows={(data.strategy_live_stats.top_active ?? []).map((item) => [
            compactValue(item.strategy_name ?? item.name),
            compactValue(item.symbol),
            compactValue(item.timeframe),
            compactValue(item.status ?? item.live_status),
            compactValue(item.realized_pnl ?? item.score ?? item.pnl),
          ])}
        />
      </Section>

      <Section title="Open trade ledger" description="Current open-trade records returned by the execution summary endpoint.">
        <DataTable
          columns={["Symbol", "Side", "Volume", "Open time", "PnL"]}
          rows={(data.open_trades.trades ?? []).map((trade) => [
            compactValue(trade.symbol),
            compactValue(trade.side ?? trade.direction),
            compactValue(trade.volume ?? trade.lots),
            compactValue(formatDateTime(trade.open_time ?? trade.opened_at)),
            compactValue(trade.pnl ?? trade.profit),
          ])}
        />
      </Section>

      <Section title="Unmatched closed deals" description="Closed deals that have not been cleanly paired or reconciled.">
        <DataTable
          columns={["Symbol", "Ticket", "Closed at", "Reason", "PnL"]}
          rows={(data.unmatched_closed_deals.recent ?? []).map((deal) => [
            compactValue(deal.symbol),
            compactValue(deal.ticket ?? deal.position_id),
            compactValue(formatDateTime(deal.closed_at ?? deal.close_time)),
            compactValue(deal.reason ?? deal.comment),
            compactValue(deal.pnl ?? deal.profit),
          ])}
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
            compactValue(entry.detail ?? entry.message ?? entry.comment),
          ])}
        />
      </Section>
    </div>
  );
}
