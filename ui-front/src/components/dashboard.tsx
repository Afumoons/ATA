import type { ReactNode, SelectHTMLAttributes } from "react";
import { compactValue, formatDateTime, prettifyKey, truncateMiddle } from "@/lib/format";
import { attentionToneForEvent, describeQueryError, getEventTimestamp, getFreshnessState, summarizeEvent } from "@/lib/ui-state";
import type { StatusTone } from "@/lib/types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils";

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
    <Card className={cn("stat-card", `tone-${tone}`)}>
      <span className="stat-label">{label}</span>
      <strong className="stat-value">{value}</strong>
      {hint ? <span className="stat-hint">{hint}</span> : null}
    </Card>
  );
}

export function StatusBadge({ label, tone = "neutral" }: { label: string; tone?: StatusTone }) {
  return <Badge variant={tone === "neutral" ? "neutral" : tone}>{label}</Badge>;
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
    <Button type="button" variant="toolbar" className={cn(`tone-${tone}`)} onClick={onClick} disabled={busy}>
      {busy ? "Refreshing…" : label}
    </Button>
  );
}

export function FilterToolbar({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  return <div className={cn("filter-toolbar", "panel", className)}>{children}</div>;
}

export function FilterField({
  label,
  children,
}: {
  label: string;
  children: ReactNode;
}) {
  return (
    <label className="filter-field">
      <span>{label}</span>
      {children}
    </label>
  );
}

export function FilterSelect({ className, children, ...props }: SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select className={cn("filter-input", className)} {...props}>
      {children}
    </select>
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
    <Card className={cn("inline-notice", `tone-${tone}`)}>
      <div>
        <h4>{title}</h4>
        <p>{description}</p>
      </div>
      {action ? <div className="inline-notice-action">{action}</div> : null}
    </Card>
  );
}

export function StatusStrip({
  items,
}: {
  items: Array<{ label: string; value: string; tone?: StatusTone; detail?: string }>;
}) {
  return (
    <Card className="status-strip">
      {items.map((item) => (
        <div key={`${item.label}-${item.value}`} className="status-strip-item">
          <div className="status-strip-topline">
            <span className="status-strip-label">{item.label}</span>
            <StatusBadge label={item.value} tone={item.tone ?? "neutral"} />
          </div>
          {item.detail ? <p>{item.detail}</p> : null}
        </div>
      ))}
    </Card>
  );
}

export function AttentionCard({
  label,
  value,
  detail,
  tone = "neutral",
}: {
  label: string;
  value: ReactNode;
  detail: string;
  tone?: StatusTone;
}) {
  const toneLabel = tone === "neutral" ? "Monitor" : tone.charAt(0).toUpperCase() + tone.slice(1);

  return (
    <Card className={cn("attention-card", `tone-${tone}`)}>
      <div className="attention-card-topline">
        <span className="attention-card-label">{label}</span>
        <StatusBadge label={toneLabel} tone={tone} />
      </div>
      <strong className="attention-card-value">{value}</strong>
      <p>{detail}</p>
    </Card>
  );
}

export function InsightCard({
  eyebrow,
  title,
  description,
  tone = "neutral",
  badges,
  metrics,
  footer,
}: {
  eyebrow: string;
  title: ReactNode;
  description: string;
  tone?: StatusTone;
  badges?: ReactNode;
  metrics?: Array<{ label: string; value: ReactNode }>;
  footer?: ReactNode;
}) {
  return (
    <Card className={cn("insight-card", `tone-${tone}`)}>
      <div className="insight-card-header">
        <div className="insight-card-heading">
          <span className="insight-card-eyebrow">{eyebrow}</span>
          <strong>{title}</strong>
          <p>{description}</p>
        </div>
        {badges ? <div className="insight-card-badges">{badges}</div> : null}
      </div>
      {metrics?.length ? (
        <div className="insight-card-metrics">
          {metrics.map((metric) => (
            <div key={`${metric.label}-${String(metric.value)}`}>
              <span>{metric.label}</span>
              <strong>{metric.value}</strong>
            </div>
          ))}
        </div>
      ) : null}
      {footer ? <div className="insight-card-footer">{footer}</div> : null}
    </Card>
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
    <Card className="table-panel">
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
                  {row.map((cell, cellIndex) => {
                    const columnLabel = columns[cellIndex] ?? `Column ${cellIndex + 1}`;
                    const isPrimaryCell = cellIndex === 0;

                    return (
                      <td
                        key={cellIndex}
                        data-column={columnLabel}
                        data-primary-cell={isPrimaryCell ? "true" : undefined}
                        aria-label={`${columnLabel}: ${typeof cell === "string" ? cell : "table cell"}`}
                      >
                        {cell}
                      </td>
                    );
                  })}
                </tr>
              ))
            ) : (
              <tr className="table-empty-row">
                <td colSpan={columns.length}>
                  <EmptyState title={emptyTitle} description={emptyDescription} compact />
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </Card>
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
    <Card className="kv-grid">
      {entries.map(([key, value]) => (
        <div key={key} className="kv-item">
          <span className="kv-key">{prettifyKey(key)}</span>
          <strong className="kv-value">{compactValue(value)}</strong>
        </div>
      ))}
    </Card>
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
          <Card key={`${String(timestamp)}-${index}`} className={cn("timeline-item", `tone-${tone}`)}>
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
            {showRaw && item.raw ? <pre className="raw-block">{String(item.raw)}</pre> : null}
          </Card>
        );
      })}
    </div>
  );
}

export function LoadingState({ title = "Loading view", description }: { title?: string; description?: string }) {
  return (
    <Card className="state-panel">
      <CardHeader className="pb-2">
        <div className="loading-dot" />
        <CardTitle>{title}</CardTitle>
        <CardDescription>{description ?? "Fetching the latest operator snapshot from the UI API."}</CardDescription>
      </CardHeader>
    </Card>
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
    <Card className="state-panel state-error">
      <CardHeader className="pb-2">
        <StatusBadge label={state.badge} tone={state.tone} />
        <CardTitle>{state.title}</CardTitle>
        <CardDescription>{state.description}</CardDescription>
      </CardHeader>
      {state.detail ? (
        <CardContent>
          <code className="inline-code">{truncateMiddle(state.detail, 180)}</code>
        </CardContent>
      ) : null}
    </Card>
  );
}

export function EmptyState({
  title,
  description,
  compact = false,
  tone = "neutral",
  eyebrow,
  meaning,
  nextStep,
}: {
  title: string;
  description: string;
  compact?: boolean;
  tone?: StatusTone;
  eyebrow?: string;
  meaning?: string;
  nextStep?: string;
}) {
  return (
    <Card className={cn("state-panel", "state-empty", `tone-${tone}`, compact && "is-compact")}>
      <CardHeader className="pb-2">
        {eyebrow ? <span className="eyebrow state-eyebrow">{eyebrow}</span> : null}
        <CardTitle>{title}</CardTitle>
        <CardDescription>{description}</CardDescription>
      </CardHeader>
      {meaning || nextStep ? (
        <CardContent className="state-panel-meta">
          {meaning ? (
            <div className="state-meta-block">
              <span>Operator meaning</span>
              <strong>{meaning}</strong>
            </div>
          ) : null}
          {nextStep ? (
            <div className="state-meta-block">
              <span>Best next read</span>
              <strong>{nextStep}</strong>
            </div>
          ) : null}
        </CardContent>
      ) : null}
    </Card>
  );
}
