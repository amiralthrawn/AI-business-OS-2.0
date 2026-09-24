import Link from "next/link";
import Badge from "@/components/ui/Badge";
import { fmtMoney } from "@/lib/objects";
import type { DocumentSummary } from "@/lib/types";

const STAGES: { status: string; label: string }[] = [
  { status: "new", label: "Nouvelles" },
  { status: "qualifying", label: "Qualification" },
  { status: "quoting", label: "Chiffrage" },
  { status: "negotiating", label: "Négociation" },
  { status: "won", label: "Gagnées" },
  { status: "lost", label: "Perdues" },
];

// The deals ("affaires") by stage: a customer request is the root of a deal
// -- its quotes, order and purchases all hang off it (brain/business_object_model.md).
export default function DealPipeline({ deals }: { deals: DocumentSummary[] }) {
  return (
    <div className="grid gap-3 overflow-x-auto md:grid-cols-3 xl:grid-cols-6">
      {STAGES.map((stage) => {
        const items = deals.filter((d) => d.status === stage.status);
        return (
          <div key={stage.status} className="min-w-[180px] rounded-2xl border border-border bg-surface-alt p-3">
            <p className="mb-2.5 flex items-center justify-between px-1 text-[12px] font-semibold text-text-soft">
              {stage.label} <span className="font-mono text-text-faint">{items.length}</span>
            </p>
            <ul className="space-y-2">
              {items.map((d) => (
                <li key={d.id}>
                  <Link href={`/documents/${d.id}`} className="block rounded-xl border border-border bg-surface p-3 transition-colors hover:border-border-strong">
                    <p className="font-mono text-[11.5px] text-text-faint">{d.number}</p>
                    <p className="mt-0.5 truncate text-[13px] font-medium text-text">{d.title ?? `${d.line_count} ligne(s)`}</p>
                    <div className="mt-1.5 flex items-center justify-between gap-2">
                      <span className="truncate text-[12px] text-text-soft">{d.party?.name}</span>
                      {d.party?.status === "prospect" && <Badge label="Prospect" tone="warning" />}
                    </div>
                    {d.total !== null && <p className="mt-1 font-mono text-[12px] font-semibold text-text">{fmtMoney(d.total)}</p>}
                  </Link>
                </li>
              ))}
            </ul>
          </div>
        );
      })}
    </div>
  );
}
