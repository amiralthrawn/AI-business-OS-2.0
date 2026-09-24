import Link from "next/link";
import Badge from "@/components/ui/Badge";
import Card from "@/components/ui/Card";
import SectionLabel from "@/components/objects/SectionLabel";
import { statusTone } from "@/lib/objects";
import type { RelatedGroup } from "@/lib/types";

// "What is this object linked to?" -- the same panel on every object page,
// fed by GET /objects/{type}/{id}/context (the relationship graph). Every
// row is a link: the next place to go is always one click away.
export default function RelatedObjects({ groups, exclude = [], title = "Objets liés" }: { groups: RelatedGroup[]; exclude?: string[]; title?: string }) {
  const visible = groups.filter((g) => !exclude.includes(g.type));
  if (visible.length === 0) return null;

  return (
    <section>
      <SectionLabel>{title}</SectionLabel>
      <Card className="divide-y divide-border">
        {visible.map((group) => (
          <div key={group.type} className="p-5">
            <p className="mb-2.5 text-[12.5px] font-semibold text-text-soft">
              {group.label} <span className="font-mono text-text-faint">({group.count})</span>
            </p>
            <ul className="flex flex-wrap gap-2">
              {group.items.slice(0, 12).map((item) => {
                const body = (
                  <span className="flex items-center gap-2">
                    <span className="max-w-[260px] truncate">{item.title}</span>
                    {item.status_label && <Badge label={item.status_label} tone={statusTone(item.status ?? "")} />}
                  </span>
                );
                return (
                  <li key={`${item.type}-${item.id}`}>
                    {item.href ? (
                      <Link
                        href={item.href}
                        title={`${item.kind_label}${item.subtitle ? ` — ${item.subtitle}` : ""}`}
                        className="inline-flex rounded-lg border border-border bg-surface-alt px-3 py-1.5 text-[12.5px] text-text transition-colors hover:border-border-strong"
                      >
                        {body}
                      </Link>
                    ) : (
                      <span className="inline-flex rounded-lg border border-border bg-surface-alt px-3 py-1.5 text-[12.5px] text-text-soft">{body}</span>
                    )}
                  </li>
                );
              })}
              {group.items.length > 12 && <li className="self-center text-[12px] text-text-faint">+ {group.items.length - 12} autres</li>}
            </ul>
          </div>
        ))}
      </Card>
    </section>
  );
}
