import Link from "next/link";
import Badge from "@/components/ui/Badge";
import SectionLabel from "@/components/objects/SectionLabel";
import type { ObjectSignal } from "@/lib/types";
import { valueLabel } from "@/lib/labels";

// Open Risks/Opportunities on this object or on what it involves (a PO
// shows the open risk on its supplier) -- V1 intelligence meeting V2 objects.
export default function ObjectSignals({ signals }: { signals: ObjectSignal[] }) {
  if (signals.length === 0) return null;
  return (
    <section>
      <SectionLabel>Intelligence</SectionLabel>
      <ul className="space-y-2.5">
        {signals.map((s) => (
          <li key={s.id}>
            <Link href={s.href ?? "#"} className="block rounded-xl border border-border bg-surface px-4 py-3 transition-colors hover:border-border-strong">
              <div className="flex flex-wrap items-center gap-2">
                <Badge label={s.kind_label} tone={s.type === "risk" ? "danger" : "success"} />
                {s.severity && <Badge label={`priorité ${valueLabel("severity", s.severity)}`} tone="neutral" />}
                <span className="text-[13.5px] font-medium text-text">{s.title}</span>
              </div>
              {s.via && <p className="mt-1 text-[12px] text-text-faint">via {s.via}</p>}
            </Link>
          </li>
        ))}
      </ul>
    </section>
  );
}
