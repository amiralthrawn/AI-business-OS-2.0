import Link from "next/link";
import ReasoningTrail from "@/components/intelligence/ReasoningTrail";
import Badge, { type BadgeTone } from "@/components/ui/Badge";
import Card from "@/components/ui/Card";
import type { RiskRead } from "@/lib/types";
import { valueLabel } from "@/lib/labels";


function severityTone(severity: string): BadgeTone {
  if (severity === "critical" || severity === "high") return "danger";
  if (severity === "medium") return "warning";
  return "success";
}

export default function RiskListItem({ risk }: { risk: RiskRead }) {
  return (
    <Link href={`/intelligence/risks/${risk.id}`}>
      <Card className="p-5 transition-colors hover:border-border-strong">
        <div className="flex items-center justify-between gap-3">
          <p className="font-semibold text-[14.5px] text-text">{risk.title}</p>
          <Badge label={valueLabel("severity", risk.severity)} tone={severityTone(risk.severity)} />
        </div>
        <div className="mt-2.5 flex items-center justify-between">
          <ReasoningTrail kind="risk" compact />
          <p className="text-[12.5px] text-text-faint">
            {valueLabel("signalStatus", risk.status)}
            {risk.related_entity_type && ` · ${valueLabel("entity", risk.related_entity_type)}`}
          </p>
        </div>
      </Card>
    </Link>
  );
}
