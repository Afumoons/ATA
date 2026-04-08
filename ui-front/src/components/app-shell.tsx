import Link from "next/link";
import { ThemeToggle } from "./theme-toggle";

const navItems = [
  ["/", "Overview", "Capital, pool, manifest readiness"],
  ["/execution", "Execution", "Live posture and trade traces"],
  ["/pool", "Pool", "Inventory, slot mix, top records"],
  ["/manifest", "Manifest", "Current composition and entries"],
  ["/audit", "Audit", "Merged event timeline"],
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
          <h1>Operator UI v1</h1>
          <p>
            Calm, read-only operator visibility into live execution state, governed strategy inventory,
            and manifest composition.
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
            <div className="sidebar-footnote">Read-only operator surface</div>
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
}: {
  title: string;
  subtitle: string;
  meta?: string;
}) {
  return (
    <header className="page-header panel panel-hero">
      <div>
        <div className="eyebrow">Operator dashboard</div>
        <h2>{title}</h2>
        <p>{subtitle}</p>
      </div>
      {meta ? <div className="header-meta">{meta}</div> : null}
    </header>
  );
}
