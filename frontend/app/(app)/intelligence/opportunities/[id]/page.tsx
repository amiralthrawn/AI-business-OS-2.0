import Link from "next/link";
import { notFound } from "next/navigation";
import CreateTaskButton from "@/components/actions/CreateTaskButton";
import TaskActionButtons from "@/components/actions/TaskActionButtons";
import ContactCard from "@/components/data/ContactCard";
import { ActionResult, Level, impactBadges, tasksFor } from "@/components/intelligence/AnalysisLevels";
import DecisionOptions from "@/components/intelligence/DecisionOptions";
import ReasoningTrail from "@/components/intelligence/ReasoningTrail";
import Badge from "@/components/ui/Badge";
import { getHomeView, getOpportunity, getTasks } from "@/lib/api";
import { valueLabel } from "@/lib/labels";
import { entityHref, findPriorityFor, resolveEntityWithContact } from "@/lib/related-entity";

export const dynamic = "force-dynamic";

// An Opportunity read in three levels (brain/decisions.md #57), same shape
// as a Risk: what is happening -> why it matters / what the OS recommends ->
// what can be done and what really happened.
export default async function OpportunityDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;

  let opportunity;
  try {
    opportunity = await getOpportunity(id);
  } catch {
    notFound();
  }

  const [tasks, home, related] = await Promise.all([
    getTasks().catch(() => []),
    getHomeView().catch(() => null),
    resolveEntityWithContact(opportunity.related_entity_type, opportunity.related_entity_id),
  ]);
  const entityName = related.name;
  const subjectTasks = tasksFor(tasks, opportunity.related_entity_type, opportunity.related_entity_id);
  const pendingTask = subjectTasks.find((t) => t.status === "pending_validation" && t.pending_action !== null);
  const priority = home ? findPriorityFor(home, "opportunity", opportunity.id) : null;
  // Not among the current priorities: the Decision Intelligence analysis of
  // the same subject (DecisionProposed, re-hydrated by GET /home), if any.
  const decision =
    !priority && home
      ? home.decisions.find((d) => d.type === "opportunity" && d.entity_type === opportunity.related_entity_type && d.entity_id === opportunity.related_entity_id) ?? null
      : null;
  const href = opportunity.related_entity_type ? entityHref(opportunity.related_entity_type, opportunity.related_entity_id ?? "") : null;

  return (
    <main className="mx-auto max-w-3xl space-y-8 p-8 md:p-12">
      <Link href="/intelligence/opportunities" className="text-[13px] text-text-faint hover:text-text">
        &larr; Retour aux opportunités
      </Link>

      <div className="animate-reveal">
        <div className="flex flex-wrap items-center gap-2">
          <Badge label="Opportunité" tone="success" />
          <Badge label={valueLabel("signalStatus", opportunity.status)} tone="neutral" />
        </div>
        <h1 className="mt-2 font-display text-[28px] italic text-text">{opportunity.title}</h1>
        <div className="mt-3">
          <ReasoningTrail kind="opportunity" />
        </div>
      </div>

      <div className="space-y-6">
        <Level n={1} title="Objet — ce qui se passe" question="Qu'est-ce qui a été constaté ?">
          <p className="whitespace-pre-wrap text-[14px] leading-relaxed text-text">{opportunity.description ?? "Aucun détail enregistré pour cette opportunité."}</p>
          {opportunity.related_entity_type && (
            <p className="mt-3 text-[13px] text-text-soft">
              Concerne&nbsp;:{" "}
              {href && entityName ? (
                <Link href={href} className="font-semibold text-accent-strong hover:underline">
                  {entityName}
                </Link>
              ) : (
                valueLabel("entity", opportunity.related_entity_type)
              )}{" "}
              <span className="text-text-faint">({valueLabel("entity", opportunity.related_entity_type)})</span>
            </p>
          )}
        </Level>

        <Level n={2} title="Analyse & solution" question="Pourquoi est-ce important, et que recommande l'OS ?">
          {priority ? (
            <div className="space-y-3">
              {impactBadges(priority)}
              {priority.explanation && <p className="whitespace-pre-wrap text-[14px] leading-relaxed text-text">{priority.explanation}</p>}
              <p className="text-[13.5px] text-text">
                <span className="font-semibold">Ce que l&rsquo;OS recommande&nbsp;: </span>
                {priority.recommendation ?? "pas assez d'information pour recommander une action — à suivre."}
              </p>
              {priority.decision_options && priority.decision_options.length > 0 && (
                <div>
                  <p className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-text-faint">Options étudiées</p>
                  <DecisionOptions options={priority.decision_options} chosen={priority.recommendation} entityType={opportunity.related_entity_type} entityId={opportunity.related_entity_id} />
                </div>
              )}
            </div>
          ) : decision ? (
            <div className="space-y-3">
              {impactBadges({ confidence: decision.confidence })}
              {decision.recommendation.reasoning && <p className="whitespace-pre-wrap text-[14px] leading-relaxed text-text">{decision.recommendation.reasoning}</p>}
              <p className="text-[13.5px] text-text">
                <span className="font-semibold">Ce que l&rsquo;OS recommande&nbsp;: </span>
                {decision.recommendation.chosen_option ?? "pas assez d'information pour recommander une action — la situation reste à surveiller."}
              </p>
              {decision.options.length > 0 && (
                <div>
                  <p className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-text-faint">Options étudiées</p>
                  <DecisionOptions options={decision.options} chosen={decision.recommendation.chosen_option} entityType={opportunity.related_entity_type} entityId={opportunity.related_entity_id} />
                </div>
              )}
              <p className="text-[11.5px] text-text-faint">Analyse produite par l&rsquo;Intelligence décisionnelle le <span className="num">{new Date(decision.occurred_at).toLocaleDateString("fr-FR")}</span>.</p>
            </div>
          ) : (
            <p className="text-[13.5px] text-text-soft">L&rsquo;OS n&rsquo;a pas encore produit d&rsquo;analyse pour cette opportunité : elle n&rsquo;est pas parmi les priorités actuelles ou les données sont insuffisantes.</p>
          )}
        </Level>

        <Level n={3} title="Action & résultat" question="Que pouvez-vous faire, et qu'est-ce qui a réellement été obtenu ?" tone="muted">
          <div className="space-y-4">
            {pendingTask && (
              <div>
                <p className="mb-1.5 text-[12.5px] text-text-soft">Une action proposée attend votre décision — rien n&rsquo;est exécuté sans validation :</p>
                <TaskActionButtons taskId={pendingTask.id} taskTitle={pendingTask.title} />
              </div>
            )}
            {related.contact && entityName && opportunity.related_entity_type && (
              <ContactCard contact={related.contact} entityName={entityName} entityType={opportunity.related_entity_type} entityId={opportunity.related_entity_id!} />
            )}
            <CreateTaskButton defaultTitle={opportunity.title} relatedEntityType={opportunity.related_entity_type ?? undefined} relatedEntityId={opportunity.related_entity_id ?? undefined} />
            <div>
              <p className="mb-1.5 text-[11px] font-semibold uppercase tracking-wide text-text-faint">Résultat</p>
              <ActionResult tasks={subjectTasks} />
            </div>
          </div>
        </Level>
      </div>
    </main>
  );
}
