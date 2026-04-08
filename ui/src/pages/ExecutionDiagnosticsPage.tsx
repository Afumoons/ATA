import { DataTable, EmptyState, ErrorState, Header, KeyValueGrid, LoadingState, Section, StatCard } from '../components/ui';
import { useQuery } from '../hooks/useQuery';
import { uiApi } from '../lib/api';
import { compactValue, formatCurrency, formatDateTime, formatNumber } from '../lib/format';

export function ExecutionDiagnosticsPage() {
  const { data, loading, error } = useQuery('execution-summary', uiApi.executionSummary);

  if (loading) return <LoadingState title="Loading execution diagnostics" />;
  if (error || !data) return <ErrorState message={error ?? 'Execution diagnostics unavailable'} />;

  const topActive = data.strategy_live_stats.top_active ?? [];
  const openTrades = data.open_trades.trades ?? [];
  const unmatched = data.unmatched_closed_deals.recent ?? [];

  return (
    <>
      <Header
        title="Execution Diagnostics"
        subtitle="Operational live-state context, open-trade visibility, and recent execution traces."
        meta={`Generated ${formatDateTime(data.generated_at)}`}
      />

      <Section title="Execution posture" description="Compact operator signals from the execution summary endpoint.">
        <div className="stats-grid">
          <StatCard label="Tracked strategies" value={formatNumber(data.strategy_live_stats.strategy_count)} />
          <StatCard label="Realized live PnL" value={formatCurrency(data.strategy_live_stats.total_realized_pnl)} />
          <StatCard label="Live trades" value={formatNumber(data.strategy_live_stats.total_trades)} />
          <StatCard label="Open positions" value={formatNumber(data.open_trades.count)} hint={`${formatNumber(data.unmatched_closed_deals.count)} unmatched closes`} />
        </div>
      </Section>

      <Section title="Live state snapshot" description="Raw account-level state, shown plainly for fast inspection.">
        <KeyValueGrid data={data.live_state} />
      </Section>

      <Section title="Top active strategies" description="Highest-activity live strategies in the current stats snapshot.">
        <DataTable
          columns={['Strategy', 'Trades', 'Total PnL', 'Last update']}
          rows={topActive.map((row) => [
            compactValue(row.name),
            compactValue(row.num_trades),
            compactValue(row.total_pnl),
            compactValue(row.last_update),
          ])}
        />
      </Section>

      <Section title="Open trades" description="Current open-position snapshot from execution state.">
        {openTrades.length ? (
          <DataTable
            columns={['Ticket', 'Symbol', 'Type', 'Volume', 'Strategy', 'Open price']}
            rows={openTrades.slice(0, 20).map((row) => [
              compactValue(row.ticket),
              compactValue(row.symbol),
              compactValue(row.type),
              compactValue(row.volume),
              compactValue(row.strategy_name ?? row.strategy),
              compactValue(row.price_open),
            ])}
          />
        ) : (
          <EmptyState title="No open trades" description="The backend currently reports no open positions." />
        )}
      </Section>

      <Section title="Recent unmatched closes" description="Auditable edge cases where closed deals did not map cleanly.">
        <DataTable
          columns={['Time', 'Symbol', 'Reason', 'Ticket']}
          rows={unmatched.map((row) => [
            compactValue(row.recorded_at ?? row.time),
            compactValue(row.symbol),
            compactValue(row.reason),
            compactValue(row.ticket),
          ])}
        />
      </Section>

      <Section title="Trade log tail" description="Recent structured trade log rows for operator context.">
        <DataTable
          columns={['Time', 'Action', 'Symbol', 'Strategy', 'Raw']}
          rows={data.recent_trade_log.slice(0, 20).map((row) => [
            compactValue(row.time ?? row.timestamp),
            compactValue(row.action),
            compactValue(row.symbol),
            compactValue(row.strategy),
            compactValue(row.raw),
          ])}
        />
      </Section>
    </>
  );
}
