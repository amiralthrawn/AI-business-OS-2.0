import Link from "next/link";
import { ActionResult } from "@/components/intelligence/AnalysisLevels";
import DecisionOptions from "@/components/intelligence/DecisionOptions";
import Badge, { type BadgeTone } from "@/components/ui/Badge";
import Card from "@/components/ui/Card";
import { valueLabel } from "@/lib/labels";
import { entityHref } from "@/lib/related-entity";
import type { DecisionSummary, TaskRead } from "@/lib/types";

function confidenceTone(confidence: string): BadgeTone {
  if (confidence === "high") return "success";
  if (confidence === "medium") return "warning";
  return "neutral";
}

const STEP = "flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-[10.5px] font-bold";

// One `DecisionProposed` Event Log entry (HomeService.get_decisions), read in
// three levels: OBJET (what is happening) -> ANALYSE & SOLUTION (why it
// matters, what the OS recommends, the options and their trade-offs) ->
// ACTION & RÉSULTAT (turn an option into a real task; the result shown is
// only what the tasks attached to the subject really became).
export default function DecisionCard({ decision, tasks = [] }: { decision: DecisionSummary; tasks?: TaskRead[] }) {
  const href = decision.entity_type && decision.entity_id ? entityHref(decision.entity_type, decision.entity_id) : null;
  const hasOptions = decision.options.length > 0;

  return (
    <Card className="space-y-5 p-6">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-wrap items-center gap-2">
          <Badge label={valueLabel("signal", decision.type)} tone="accent" />
          <Badge label={valueLabel("domain", decision.domain)} tone="neutral" />
          <Badge label={`confiance ${valueLabel("confidence", decision.confidence)}`} tone={confidenceTone(decision.confidence)} />
        </div>
        <span className="num text-[11.5px] text-text-faint">{new Date(decision.occurred_at).toLocaleDateString("fr-FR")}</span>
      </div>

      <div className="flex gap-3">
        <span className={`${STEP} bg-accent text-white`}>1</span>
        <div className="min-w-0">
          <p className="text-[11px] font-bold uppercase tracking-wide text-text-faint">Objet — ce qui se passe</p>
          <p className="mt-1 text-[15px] font-semibold text-text">{decision.problem}</p>
          {href && (
            <Link href={href} className="mt-1 inline-block text-[12.5px] font-medium text-accent-strong hover:underline">
              Voir la fiche {valueLabel("entity", decision.entity_type)} →
            </Link>
          )}
        </div>
      </div>

      <div className="flex gap-3">
        <span className={`${STEP} bg-accent text-white`}>2</span>
        <div className="min-w-0 flex-1 space-y-2.5">
          <p className="text-[11px] font-bold uppercase tracking-wide text-text-faint">Analyse &amp; solution — pourquoi c&rsquo;est important</p>
          {decision.recommendation.reasoning ? (
            <p className="text-[13px] leading-relaxed text-text-soft">{decision.recommendation.reasoning}</p>
          ) : (
            <p className="text-[13px] text-text-faint">Pas d&rsquo;analyse détaillée disponible.</p>
          )}
          <p className="text-[13px] text-text">
            <span className="font-semibold">Ce que l&rsquo;OS recommande&nbsp;: </span>
            {decision.recommendation.chosen_option ?? "pas assez d'information pour recommander une action — la situation reste à surveiller."}
          </p>
        </div>
      </div>

      <div className="flex gap-3">
        <span className={`${STEP} bg-text text-surface`}>3</span>
        <div className="min-w-0 flex-1 space-y-2.5">
          <p className="text-[11px] font-bold uppercase tracking-wide text-text-faint">Action &amp; résultat — ce que vous pouvez faire</p>
          {hasOptions ? (
            <DecisionOptions options={decision.options} chosen={decision.recommendation.chosen_option} entityType={decision.entity_type} entityId={decision.entity_id} />
          ) : (
            <p className="text-[12.5px] text-text-faint">Aucune option d&rsquo;action proposée pour l&rsquo;instant.</p>
          )}
          <div>
            <p className="mb-1.5 text-[11px] font-semibold uppercase tracking-wide text-text-faint">Résultat</p>
            <ActionResult tasks={tasks} />
          </div>
        </div>
      </div>
    </Card>
  );
}
