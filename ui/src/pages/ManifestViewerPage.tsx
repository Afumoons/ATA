import { DataTable, EmptyState, ErrorState, Header, LoadingState, Section, StatCard } from '../components/ui';
import { useQuery } from '../hooks/useQuery';
import { uiApi } from '../lib/api';
import { compactValue, formatDateTime, formatNumber } from '../lib/format';

export function ManifestViewerPage() {
  const { data, loading, error } = useQuery('manifest', uiApi.manifest);

  if (loading) return <LoadingState title="Loading manifest" />;
  if (error || !data) return <ErrorState message={error ?? 'Manifest unavailable'} />;

  const firstEntry = data.entries[0] ?? null;
  const columns = firstEntry ? Object.keys(firstEntry).slice(0, 8) : [];

  return (
    <>
      <Header
        title="Manifest Viewer"
        subtitle="Read-only view into the current live manifest the operator layer is working from."
        meta={`Generated ${formatDateTime(data.generated_at)}`}
      />

      <Section title="Manifest snapshot" description="Schema and source metadata for the currently active manifest payload.">
        <div className="stats-grid">
          <StatCard label="Entries" value={formatNumber(data.entry_count)} />
          <StatCard label="Schema version" value={formatNumber(data.schema_version)} />
          <StatCard label="Source" value={data.source} />
        </div>
      </Section>

      <Section title="Manifest entries" description="First fields of the live manifest for fast operator inspection.">
        {columns.length ? (
          <DataTable
            columns={columns.map((column) => column.replace(/_/g, ' '))}
            rows={data.entries.slice(0, 30).map((entry) => columns.map((column) => compactValue(entry[column])))}
          />
        ) : (
          <EmptyState title="Manifest empty" description="No manifest entries are currently available from the backend." />
        )}
      </Section>
    </>
  );
}
