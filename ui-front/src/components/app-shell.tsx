import Link from "next/link";
import { ThemeToggle } from "./theme-toggle";

const navItems = [
  ["/", "Overview", "Capital, health strip, freshness, runtime posture"],
  ["/execution", "Execution", "Live posture, no-trade diagnosis, attention events"],
  ["/pool", "Pool", "Inventory, relationship mapping, strategy drill-down"],
  ["/manifest", "Manifest", "Artifact presence and deployment composition"],
  ["/audit", "Audit", "Merged timeline with operator filters"],
] as const;

export function AppShell({
  children,
  pathname,
}: {
  children: React.ReactNode;
  pathname: string;
}) {
  return (
    <div className="app-shell">
      <aside className="sidebar panel">
        <div className="sidebar-brand">
          <div className="eyebrow">Autonomous Trading AI</div>
          <h1>Operator UI</h1>
          <p>
            Read-only operator visibility into backend health, runtime artifacts, execution diagnostics,
            and strategy-layer coherence.
          </p>
        </div>

        <nav className="nav-list" aria-label="Primary navigation">
          {navItems.map(([href, label, detail]) => {
            const active = pathname === href;
            return (
              <Link key={href} href={href} className={`nav-item${active ? " is-active" : ""}`}>
                <span className="nav-label">{label}</span>
                <span className="nav-detail">{detail}</span>
              </Link>
            );
          })}
        </nav>

        <div className="sidebar-footer">
          <div>
            <div className="eyebrow">Mode</div>
            <div className="sidebar-footnote">Read-only operator surface · no live execution controls</div>
          </div>
          <ThemeToggle />
        </div>
      </aside>
      <div className="content-column">{children}</div>
    </div>
  );
}

export function PageHeader({
  title,
  subtitle,
  meta,
  action,
}: {
  title: string;
  subtitle: string;
  meta?: string;
  action?: React.ReactNode;
}) {
  return (
    <header className="page-header panel panel-hero">
      <div>
        <div className="eyebrow">Operator dashboard</div>
        <h2>{title}</h2>
        <p>{subtitle}</p>
      </div>
      <div className="page-header-side">
        {meta ? <div className="header-meta">{meta}</div> : null}
        {action ? <div className="page-header-action">{action}</div> : null}
      </div>
    </header>
  );
}
