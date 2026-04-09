import type { ReactNode } from "react";
import { compactValue, formatDateTime, truncateMiddle, prettifyKey } from "@/lib/format";
import { attentionToneForEvent, describeQueryError, getFreshnessState, getEventTimestamp, summarizeEvent } from "@/lib/ui-state";
import type { StatusTone } from "@/lib/types";

export function Section({
  title,
  description,
  children,
  action,
}: {
  title: string;
  description?: string;
  children: ReactNode;
  action?: ReactNode;
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
  value: ReactNode;
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

export function ToolbarButton({
  label,
  onClick,
  busy = false,
  tone = "neutral",
}: {
  label: string;
  onClick?: () => void;
  busy?: boolean;
  tone?: StatusTone;
}) {
  return (
    <button type="button" className={`toolbar-button tone-${tone}`} onClick={onClick} disabled={busy}>
      {busy ? "Refreshing…" : label}
    </button>
  );
}

export function FreshnessBadge({
  timestamp,
  thresholds,
}: {
  timestamp: unknown;
  thresholds?: { warningMs?: number; criticalMs?: number };
}) {
  const freshness = getFreshnessState(timestamp, thresholds);
  return <StatusBadge label={freshness.label} tone={freshness.tone} />;
}

export function InlineNotice({
  title,
  description,
  tone = "info",
  action,
}: {
  title: string;
  description: string;
  tone?: StatusTone;
  action?: ReactNode;
}) {
  return (
    <div className={`panel inline-notice tone-${tone}`}>
      <div>
        <h4>{title}</h4>
        <p>{description}</p>
      </div>
      {action ? <div className="inline-notice-action">{action}</div> : null}
    </div>
  );
}

export function StatusStrip({
  items,
}: {
  items: Array<{ label: string; value: string; tone?: StatusTone; detail?: string }>;
}) {
  return (
    <div className="status-strip panel">
      {items.map((item) => (
        <div key={`${item.label}-${item.value}`} className="status-strip-item">
          <div className="status-strip-topline">
            <span className="status-strip-label">{item.label}</span>
            <StatusBadge label={item.value} tone={item.tone ?? "neutral"} />
          </div>
          {item.detail ? <p>{item.detail}</p> : null}
        </div>
      ))}
    </div>
  );
}

export function DataTable({
  columns,
  rows,
  emptyTitle = "No rows",
  emptyDescription = "Nothing is available for this view yet.",
}: {
  columns: string[];
  rows: Array<Array<ReactNode>>;
  emptyTitle?: string;
  emptyDescription?: string;
}) {
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
                  <EmptyState title={emptyTitle} description={emptyDescription} compact />
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export function KeyValueGrid({
  data,
  emptyTitle = "No metadata",
  emptyDescription = "The backend did not return structured metadata for this block.",
}: {
  data: Record<string, unknown>;
  emptyTitle?: string;
  emptyDescription?: string;
}) {
  const entries = Object.entries(data);
  if (!entries.length) {
    return <EmptyState title={emptyTitle} description={emptyDescription} compact />;
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

export function Timeline({
  items,
  expanded = false,
  showRaw = false,
}: {
  items: Array<Record<string, unknown>>;
  expanded?: boolean;
  showRaw?: boolean;
}) {
  if (!items.length) {
    return <EmptyState title="No audit events" description="Audit feeds are currently empty or filtered down to zero rows." />;
  }

  return (
    <div className="timeline-list">
      {items.map((item, index) => {
        const timestamp = getEventTimestamp(item);
        const tone = attentionToneForEvent(item);
        const entries = Object.entries(item).filter(([key]) => key !== "raw");
        const leadingEntries = expanded ? entries.slice(0, 12) : entries.slice(0, 6);

        return (
          <article key={`${String(timestamp)}-${index}`} className={`panel timeline-item tone-${tone}`}>
            <div className="timeline-topline">
              <div className="timeline-heading-block">
                <StatusBadge label={String(item.source ?? "event")} tone={tone === "neutral" ? "info" : tone} />
                <strong>{summarizeEvent(item)}</strong>
              </div>
              <span>{formatDateTime(timestamp)}</span>
            </div>
            <div className="timeline-grid">
              {leadingEntries.map(([key, value]) => (
                <div key={key} className="timeline-cell">
                  <span>{prettifyKey(key)}</span>
                  <strong title={typeof value === "string" ? value : undefined}>
                    {typeof value === "string" ? truncateMiddle(value, expanded ? 100 : 52) : compactValue(value)}
                  </strong>
                </div>
              ))}
            </div>
            {showRaw && item.raw ? (
              <pre className="raw-block">{String(item.raw)}</pre>
            ) : null}
          </article>
        );
      })}
    </div>
  );
}

export function LoadingState({ title = "Loading view", description }: { title?: string; description?: string }) {
  return (
    <div className="panel state-panel">
      <div className="loading-dot" />
      <h3>{title}</h3>
      <p>{description ?? "Fetching the latest operator snapshot from the UI API."}</p>
    </div>
  );
}

export function ErrorState({
  error,
  resourceLabel,
}: {
  error: unknown;
  resourceLabel: string;
}) {
  const state = describeQueryError(error, resourceLabel);

  return (
    <div className="panel state-panel state-error">
      <StatusBadge label={state.badge} tone={state.tone} />
      <h3>{state.title}</h3>
      <p>{state.description}</p>
      {state.detail ? <code className="inline-code">{truncateMiddle(state.detail, 180)}</code> : null}
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
