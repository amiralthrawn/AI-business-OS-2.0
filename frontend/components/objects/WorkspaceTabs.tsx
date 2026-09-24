import Link from "next/link";

// Sub-navigation inside a workspace (Ventes, Achats, Catalogue,
// Communications, Intelligence, Actions). URL-driven (?tab= or a sibling
// route), so every tab is linkable and survives a refresh.
export default function WorkspaceTabs({ tabs, active }: { tabs: { key: string; label: string; href: string; count?: number }[]; active: string }) {
  return (
    <nav className="-mb-px flex gap-1 overflow-x-auto border-b border-border" aria-label="Sous-navigation">
      {tabs.map((tab) => {
        const isActive = tab.key === active;
        return (
          <Link
            key={tab.key}
            href={tab.href}
            className={`shrink-0 border-b-2 px-3.5 pb-2.5 pt-1 text-[13.5px] font-medium transition-colors ${
              isActive ? "border-accent text-accent-strong" : "border-transparent text-text-soft hover:text-text"
            }`}
          >
            {tab.label}
            {tab.count !== undefined && tab.count > 0 && <span className="ml-1.5 font-mono text-[11px] text-text-faint">{tab.count}</span>}
          </Link>
        );
      })}
    </nav>
  );
}
