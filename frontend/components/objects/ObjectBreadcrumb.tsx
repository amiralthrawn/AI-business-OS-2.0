import Link from "next/link";
import type { ObjectSummary } from "@/lib/types";

// "Where am I, and where does this come from?" -- the section, then the
// document chain from the deal's root down to the current object.
export default function ObjectBreadcrumb({
  section,
  chain,
}: {
  section: { label: string; href: string };
  chain: ObjectSummary[];
}) {
  return (
    <nav aria-label="Fil d'Ariane" className="flex flex-wrap items-center gap-1.5 text-[13px] text-text-faint">
      <Link href={section.href} className="hover:text-text">
        {section.label}
      </Link>
      {chain.map((item, i) => {
        const last = i === chain.length - 1;
        const label = item.title.split(" · ")[0];
        return (
          <span key={item.id} className="flex items-center gap-1.5">
            <span className="text-border-strong">/</span>
            {last || !item.href ? (
              <span className={last ? "font-semibold text-text" : ""}>{label}</span>
            ) : (
              <Link href={item.href} className="hover:text-text" title={item.kind_label}>
                {label}
              </Link>
            )}
          </span>
        );
      })}
    </nav>
  );
}
