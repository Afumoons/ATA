import { Header, KeyValueGrid, LoadingState, ErrorState, Section, StatCard, DataTable, StatusBadge } from '../components/ui';
import { useQuery } from '../hooks/useQuery';
import { formatCurrency, formatNumber, formatDateTime } from '../lib/format';
import { uiApi } from '../lib/api';

export function OverviewPage() {
  const { data, loading, error } = useQuery('overview', uiApi.overview);

  if (loading) return <LoadingState title="Loading overview" />;
  if (error || !data) return <ErrorState message={error ?? 'Overview unavailable'} />;

  return (
    <>
      <Header
        title="System Overview"
        subtitle="A calm summary of live capital state, pool health, and manifest readiness."
        meta={`Generated ${formatDateTime(data.generated_at)}`}
      />

      <Section title="At a glance" description="Top-line operator metrics from the backend overview endpoint.">
        <div className="stats-grid stats-grid-hero">
          <StatCard label="Equity" value={formatCurrency(data.equity_current)} hint={`State date ${data.live_state_date ?? '—'}`} />
          <StatCard
            label="Daily PnL"
            value={formatCurrency(data.daily_pnl)}
            tone={(data.daily_pnl ?? 0) >= 0 ? 'positive' : 'danger'}
            hint={`${formatNumber(data.trades_today)} trades today`}
          />
          <StatCard
            label="Pool size"
            value={formatNumber(data.pool_total)}
            hint={`${formatNumber(data.manifest_entry_count)} manifest entries`}
          />
          <StatCard
            label="Risk lock"
            value={data.locked_for_day ? 'Locked' : 'Open'}
            tone={data.locked_for_day ? 'warning' : 'positive'}
            hint={`${formatNumber(data.strategy_index_entry_count)} indexed strategies`}
          />
        </div>
      </Section>

      <Section title="Pool status mix" description="Current strategy states distilled into operator-safe counts.">
        <div className="badge-row">
          {Object.entries(data.pool_status_counts).map(([status, count]) => (
            <StatusBadge key={status} label={`${status}: ${count}`} tone={status === 'active' ? 'positive' : 'neutral'} />
          ))}
        </div>
      </Section>

      <Section title="Live slots" description="Manifest distribution by symbol and timeframe.">
        <DataTable
          columns={['Symbol', 'Timeframe', 'Count']}
          rows={data.live_slots.map((slot) => [slot.symbol, slot.timeframe, formatNumber(slot.count)])}
        />
      </Section>

      <Section title="Diagnostics metadata" description="Backend timestamps and structural clues for operator context.">
        <KeyValueGrid data={data.diagnostics} />
      </Section>
    </>
  );
}
