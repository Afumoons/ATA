import { ErrorState, Header, LoadingState, Section, Timeline } from '../components/ui';
import { useQuery } from '../hooks/useQuery';
import { uiApi } from '../lib/api';
import { formatDateTime } from '../lib/format';

export function AuditTimelinePage() {
  const { data, loading, error } = useQuery('audit-timeline', () => uiApi.auditTimeline(100));

  if (loading) return <LoadingState title="Loading audit timeline" />;
  if (error || !data) return <ErrorState message={error ?? 'Audit timeline unavailable'} />;

  return (
    <>
      <Header
        title="Audit Timeline"
        subtitle="Recent audit, unmatched-close, and trade-log events merged into one operator timeline."
        meta={`Generated ${formatDateTime(data.generated_at)}`}
      />

      <Section title="Recent events" description="A merged, time-sorted audit feed from the backend UI API.">
        <Timeline items={data.events} />
      </Section>
    </>
  );
}
