import { DataTable, ErrorState, Header, LoadingState, Section, StatCard, StatusBadge } from '../components/ui';
import { useQuery } from '../hooks/useQuery';
import { uiApi } from '../lib/api';
import { formatDateTime, formatNumber } from '../lib/format';

export function PoolOverviewPage() {
  const { data, loading, error } = useQuery('pool-summary', uiApi.poolSummary);

  if (loading) return <LoadingState title="Loading pool overview" />;
  if (error || !data) return <ErrorState message={error ?? 'Pool summary unavailable'} />;

  return (
    <>
      <Header
        title="Pool Overview"
        subtitle="Strategy inventory quality, slot concentration, and top-scoring pool entries."
        meta={`Generated ${formatDateTime(data.generated_at)}`}
      />

      <Section title="Pool composition" description="Size and status distribution across the governed strategy pool.">
        <div className="stats-grid">
          <StatCard label="Total strategies" value={formatNumber(data.total)} />
          {Object.entries(data.status_counts).slice(0, 3).map(([status, count]) => (
            <StatCard key={status} label={status} value={formatNumber(count)} tone={status === 'active' ? 'positive' : 'neutral'} />
          ))}
        </div>
        <div className="badge-row">
          {Object.entries(data.status_counts).map(([status, count]) => (
            <StatusBadge key={status} label={`${status}: ${count}`} tone={status === 'disabled' ? 'warning' : 'neutral'} />
          ))}
        </div>
      </Section>

      <Section title="Pool by slot" description="How strategy inventory is distributed across symbol and timeframe slots.">
        <DataTable
          columns={['Symbol', 'Timeframe', 'Count']}
          rows={data.by_slot.map((row) => [row.symbol, row.timeframe, formatNumber(row.count)])}
        />
      </Section>

      <Section title="Top strategies" description="Highest-scoring pool records from the backend summary.">
        <DataTable
          columns={['Strategy', 'Symbol', 'Timeframe', 'Status', 'Score']}
          rows={data.top_strategies.map((row) => [
            row.name,
            row.symbol,
            row.timeframe,
            <StatusBadge label={row.status} tone={row.status === 'active' ? 'positive' : 'neutral'} />,
            formatNumber(row.score ?? null, { maximumFractionDigits: 3 }),
          ])}
        />
      </Section>
    </>
  );
}
