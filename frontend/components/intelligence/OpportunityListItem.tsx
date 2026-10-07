import Link from "next/link";
import ReasoningTrail from "@/components/intelligence/ReasoningTrail";
import Badge from "@/components/ui/Badge";
import Card from "@/components/ui/Card";
import type { OpportunityRead } from "@/lib/types";
import { valueLabel } from "@/lib/labels";


export default function OpportunityListItem({ opportunity }: { opportunity: OpportunityRead }) {
  return (
    <Link href={`/intelligence/opportunities/${opportunity.id}`}>
      <Card className="p-5 transition-colors hover:border-border-strong">
        <div className="flex items-center justify-between gap-3">
          <p className="font-semibold text-[14.5px] text-text">{opportunity.title}</p>
          <Badge label={valueLabel("signalStatus", opportunity.status)} tone="success" />
        </div>
        <div className="mt-2.5 flex items-center justify-between">
          <ReasoningTrail kind="opportunity" compact />
          {opportunity.related_entity_type && (
            <p className="text-[12.5px] text-text-faint">{valueLabel("entity", opportunity.related_entity_type)}</p>
          )}
        </div>
      </Card>
    </Link>
  );
}
