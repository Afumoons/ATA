import type { ReactNode } from 'react';
import { NavLink } from 'react-router-dom';
import { compactValue, formatDateTime, prettifyKey } from '../lib/format';
import type { StatusTone } from '../types';

export function AppShell({ children }: { children: ReactNode }) {
  const navItems = [
    ['/', 'Overview'],
    ['/execution', 'Execution'],
    ['/pool', 'Pool'],
    ['/manifest', 'Manifest'],
    ['/audit', 'Audit'],
  ];

  return (
    <div className="app-shell">
      <aside className="sidebar glass-panel">
        <div>
          <div className="eyebrow">Autonomous Trading AI</div>
          <h1>Operator UI v1</h1>
          <p className="sidebar-copy">
            Read-only visibility into live state, pool quality, manifest composition, and execution signals.
          </p>
        </div>
        <nav className="nav-list" aria-label="Primary">
          {navItems.map(([to, label]) => (
            <NavLink
              key={to}
              to={to}
              end={to === '/'}
              className={({ isActive }) => `nav-item ${isActive ? 'is-active' : ''}`}
            >
              <span>{label}</span>
            </NavLink>
          ))}
        </nav>
        <div className="sidebar-footnote">
          Apple-like calm, tuned for operator focus rather than trading-dashboard noise.
        </div>
      </aside>
      <main className="main-column">{children}</main>
    </div>
  );
}

export function Header({ title, subtitle, meta }: { title: string; subtitle: string; meta?: string }) {
  return (
    <header className="page-header glass-strip">
      <div>
        <div className="eyebrow">Read-only operator surface</div>
        <h2>{title}</h2>
        <p>{subtitle}</p>
      </div>
      {meta ? <div className="header-meta">{meta}</div> : null}
    </header>
  );
}

export function Section({ title, description, children }: { title: string; description?: string; children: ReactNode }) {
  return (
    <section className="section-block">
      <div className="section-heading">
        <div>
          <h3>{title}</h3>
          {description ? <p>{description}</p> : null}
        </div>
      </div>
      {children}
    </section>
  );
}

export function StatCard({ label, value, hint, tone = 'neutral' }: { label: string; value: ReactNode; hint?: string; tone?: StatusTone }) {
  return (
    <article className={`stat-card tone-${tone}`}>
      <div className="stat-label">{label}</div>
      <div className="stat-value">{value}</div>
      {hint ? <div className="stat-hint">{hint}</div> : null}
    </article>
  );
}

export function StatusBadge({ label, tone = 'neutral' }: { label: string; tone?: StatusTone }) {
  return <span className={`status-badge tone-${tone}`}>{label}</span>;
}

export function DataTable({ columns, rows }: { columns: string[]; rows: Array<Array<ReactNode>> }) {
  return (
    <div className="table-wrap glass-panel">
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
  );
}

export function KeyValueGrid({ data }: { data: Record<string, unknown> }) {
  return (
    <div className="kv-grid glass-panel">
      {Object.entries(data).map(([key, value]) => (
        <div key={key} className="kv-item">
          <div className="kv-key">{prettifyKey(key)}</div>
          <div className="kv-value">{compactValue(value)}</div>
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
          <article key={`${String(timestamp)}-${index}`} className="timeline-item glass-panel">
            <div className="timeline-topline">
              <StatusBadge label={String(item.source ?? 'event')} tone="info" />
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

export function LoadingState({ title = 'Loading view' }: { title?: string }) {
  return (
    <div className="state-panel glass-panel">
      <div className="loading-dot" />
      <h3>{title}</h3>
      <p>Fetching the latest operator snapshot from the UI API.</p>
    </div>
  );
}

export function ErrorState({ message }: { message: string }) {
  return (
    <div className="state-panel glass-panel state-error">
      <StatusBadge label="API error" tone="danger" />
      <h3>Unable to load this view</h3>
      <p>{message}</p>
    </div>
  );
}

export function EmptyState({ title, description, compact = false }: { title: string; description: string; compact?: boolean }) {
  return (
    <div className={`state-panel glass-panel ${compact ? 'is-compact' : ''}`}>
      <h3>{title}</h3>
      <p>{description}</p>
    </div>
  );
}
