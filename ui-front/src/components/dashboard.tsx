import { compactValue, formatDateTime, prettifyKey } from "@/lib/format";
import type { StatusTone } from "@/lib/types";

export function Section({
  title,
  description,
  children,
  action,
}: {
  title: string;
  description?: string;
  children: React.ReactNode;
  action?: React.ReactNode;
}) {
  return (
    <section className="section-block">
      <div className="section-heading">
        <div>
          <h3>{title}</h3>
          {description ? <p>{description}</p> : null}
        </div>
        {action}
      </div>
      {children}
    </section>
  );
}

export function StatCard({
  label,
  value,
  hint,
  tone = "neutral",
}: {
  label: string;
  value: React.ReactNode;
  hint?: string;
  tone?: StatusTone;
}) {
  return (
    <article className={`stat-card tone-${tone}`}>
      <span className="stat-label">{label}</span>
      <strong className="stat-value">{value}</strong>
      {hint ? <span className="stat-hint">{hint}</span> : null}
    </article>
  );
}

export function StatusBadge({ label, tone = "neutral" }: { label: string; tone?: StatusTone }) {
  return <span className={`status-badge tone-${tone}`}>{label}</span>;
}

export function DataTable({ columns, rows }: { columns: string[]; rows: Array<Array<React.ReactNode>> }) {
  return (
    <div className="panel table-panel">
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              {columns.map((column) => (
                <th key={column}>{column}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.length ? (
              rows.map((row, rowIndex) => (
                <tr key={rowIndex}>
                  {row.map((cell, cellIndex) => (
                    <td key={cellIndex}>{cell}</td>
                  ))}
                </tr>
              ))
            ) : (
              <tr>
                <td colSpan={columns.length}>
                  <EmptyState title="No rows" description="Nothing is available for this view yet." compact />
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export function KeyValueGrid({ data }: { data: Record<string, unknown> }) {
  const entries = Object.entries(data);
  if (!entries.length) {
    return <EmptyState title="No metadata" description="The backend did not return structured metadata for this block." compact />;
  }

  return (
    <div className="panel kv-grid">
      {entries.map(([key, value]) => (
        <div key={key} className="kv-item">
          <span className="kv-key">{prettifyKey(key)}</span>
          <strong className="kv-value">{compactValue(value)}</strong>
        </div>
      ))}
    </div>
  );
}

export function Timeline({ items }: { items: Array<Record<string, unknown>> }) {
  if (!items.length) {
    return <EmptyState title="No audit events" description="Audit feeds are currently empty." />;
  }

  return (
    <div className="timeline-list">
      {items.map((item, index) => {
        const timestamp = item.recorded_at ?? item.last_update ?? item.generated_at ?? item.timestamp;
        return (
          <article key={`${String(timestamp)}-${index}`} className="panel timeline-item">
            <div className="timeline-topline">
              <StatusBadge label={String(item.source ?? "event")} tone="info" />
              <span>{formatDateTime(timestamp)}</span>
            </div>
            <div className="timeline-grid">
              {Object.entries(item)
                .slice(0, 8)
                .map(([key, value]) => (
                  <div key={key} className="timeline-cell">
                    <span>{prettifyKey(key)}</span>
                    <strong>{compactValue(value)}</strong>
                  </div>
                ))}
            </div>
          </article>
        );
      })}
    </div>
  );
}

export function LoadingState({ title = "Loading view" }: { title?: string }) {
  return (
    <div className="panel state-panel">
      <div className="loading-dot" />
      <h3>{title}</h3>
      <p>Fetching the latest operator snapshot from the UI API.</p>
    </div>
  );
}

export function ErrorState({ message }: { message: string }) {
  return (
    <div className="panel state-panel state-error">
      <StatusBadge label="API error" tone="danger" />
      <h3>Unable to load this view</h3>
      <p>{message}</p>
    </div>
  );
}

export function EmptyState({
  title,
  description,
  compact = false,
}: {
  title: string;
  description: string;
  compact?: boolean;
}) {
  return (
    <div className={`state-panel${compact ? " is-compact" : ""}`}>
      <h3>{title}</h3>
      <p>{description}</p>
    </div>
  );
}
