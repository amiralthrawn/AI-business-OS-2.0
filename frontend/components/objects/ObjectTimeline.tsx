import SectionLabel from "@/components/objects/SectionLabel";
import { formatDateFR, formatTimeFR } from "@/lib/labels";
import type { TimelineEntry } from "@/lib/types";

// The object's own history, from the Event Log's structured subject (V2).
export default function ObjectTimeline({ entries }: { entries: TimelineEntry[] }) {
  if (entries.length === 0) return null;
  return (
    <section>
      <SectionLabel>Historique</SectionLabel>
      <ol className="space-y-2">
        {entries.slice(0, 15).map((e, i) => (
          <li key={i} className="flex items-baseline gap-3 text-[13px]">
            <span className="w-[120px] shrink-0 font-mono text-[11.5px] text-text-faint">
              <span className="num">{formatDateFR(e.occurred_at)} {formatTimeFR(e.occurred_at)}</span>
            </span>
            <span className="text-text">{e.label}</span>
            {e.detail && <span className="truncate text-text-faint">{e.detail}</span>}
          </li>
        ))}
      </ol>
    </section>
  );
}
