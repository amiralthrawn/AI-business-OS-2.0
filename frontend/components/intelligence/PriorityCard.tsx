import Link from "next/link";
import ReasoningTrail from "@/components/intelligence/ReasoningTrail";
import Badge, { type BadgeTone } from "@/components/ui/Badge";
import Card from "@/components/ui/Card";
import type { IntelligenceSignal } from "@/lib/types";
import { valueLabel } from "@/lib/labels";

function impactTone(impact: string): BadgeTone {
  if (impact === "high") return "danger";
  if (impact === "medium") return "warning";
  return "success";
}



function kindIcon(kind: string) {
  if (kind === "risk") {
    return (
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
        <path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0Z" />
        <line x1="12" y1="9" x2="12" y2="13" /><line x1="12" y1="17" x2="12.01" y2="17" />
      </svg>
    );
  }
  if (kind === "opportunity") {
    return (
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
        <polyline points="23 6 13.5 15.5 8.5 10.5 1 18" /><polyline points="17 6 23 6 23 12" />
      </svg>
    );
  }
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 2 22 12 12 22 2 12Z" />
    </svg>
  );
}

function iconClasses(kind: string) {
  if (kind === "risk") return "bg-danger-soft text-danger";
  if (kind === "opportunity") return "bg-success-soft text-success";
  return "bg-accent-soft text-accent-strong";
}

function detailHref(signal: IntelligenceSignal): string | null {
  if (signal.detail_kind === "risk" && signal.detail_id) return `/intelligence/risks/${signal.detail_id}`;
  if (signal.detail_kind === "opportunity" && signal.detail_id) return `/intelligence/opportunities/${signal.detail_id}`;
  return null;
}

// The one card for "a material area from the Business State Snapshot" --
// presented as an intelligent element of the system (icon, reasoning trail,
// confidence), not a table row. Shared by Home's AI Priorities feed and
// every Business Domain / Data entity page's own `intelligence` list.
export default function PriorityCard({ signal }: { signal: IntelligenceSignal }) {
  const href = detailHref(signal);
  const tone = impactTone(signal.impact);
  const label = signal.interpretation_type
    ? valueLabel("signal", signal.interpretation_type)
    : valueLabel("signal", signal.kind);

  const body = (
    <div className="flex items-start gap-4">
      <div className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-xl ${iconClasses(signal.kind)}`}>
        {kindIcon(signal.kind)}
      </div>
      <div className="min-w-0 flex-1">
        <div className="flex items-center justify-between gap-3">
          <p className="truncate font-semibold text-[14.5px] text-text">{signal.title}</p>
          <Badge label={label} tone={tone} />
        </div>
        {signal.explanation && <p className="mt-1.5 text-[13.5px] leading-relaxed text-text-soft">{signal.explanation}</p>}
        {signal.recommendation && (
          <p className="mt-1.5 text-[13px] text-text-soft">
            <span className="font-medium text-text">Recommandation&nbsp;: </span>
            {signal.recommendation}
          </p>
        )}
        <div className="mt-3 flex items-center justify-between">
          <ReasoningTrail kind={signal.kind} />
          <span className="text-[11.5px] text-text-faint">confiance {valueLabel("confidence", signal.confidence)}</span>
        </div>
      </div>
    </div>
  );

  if (href) {
    return (
      <Link href={href}>
        <Card className="p-5 transition-colors hover:border-border-strong">{body}</Card>
      </Link>
    );
  }

  return <Card className="p-5">{body}</Card>;
}
