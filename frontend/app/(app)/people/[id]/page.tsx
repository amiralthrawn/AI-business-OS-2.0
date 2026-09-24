import Link from "next/link";
import { notFound } from "next/navigation";
import EmployeeActions from "@/components/people/EmployeeActions";
import BasisBadge from "@/components/objects/BasisBadge";
import ObjectBreadcrumb from "@/components/objects/ObjectBreadcrumb";
import ObjectTimeline from "@/components/objects/ObjectTimeline";
import RelatedObjects from "@/components/objects/RelatedObjects";
import SectionLabel from "@/components/objects/SectionLabel";
import Badge from "@/components/ui/Badge";
import Card from "@/components/ui/Card";
import EmptyState from "@/components/ui/EmptyState";
import { getEmployee, getMe, getObjectContext } from "@/lib/api";
import { CONFIDENCE_LABEL, can, fmtDate, fmtMoneyRange, yearsSince } from "@/lib/objects";
import type { Confidence, EmployeeDetail, ValueBasis } from "@/lib/types";

export const dynamic = "force-dynamic";

// One employee: EMPLOYEE -> COST -> TASKS -> CONTRIBUTION, with the
// decisions a manager can propose. Estimates are always labelled; there is no
// score and no ranking of people (brain/people.md).
export default async function EmployeePage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  let e: EmployeeDetail;
  try {
    e = await getEmployee(id);
  } catch {
    notFound();
  }
  const [context, me] = await Promise.all([getObjectContext("employee", id).catch(() => null), getMe().catch(() => null)]);
  const years = yearsSince(e.hired_at);

  return (
    <main className="space-y-10 p-8 md:p-12">
      <ObjectBreadcrumb section={{ label: "Équipe", href: "/people" }} chain={context?.breadcrumb ?? []} />
      <div className="animate-reveal flex flex-wrap items-start justify-between gap-6">
        <div>
          <p className="text-[12.5px] font-semibold uppercase tracking-wide text-text-faint">{e.department ?? "Département non renseigné"}</p>
          <h1 className="mt-1.5 font-display text-[28px] italic text-text">{e.full_name}</h1>
          <div className="mt-2 flex flex-wrap items-center gap-2 text-[13px] text-text-soft">
            <span>{e.job_title ?? "Poste non renseigné"}</span>
            <Badge label={{ active: "Actif", on_leave: "En congé", left: "Parti" }[e.status] ?? e.status} tone="success" />
            {e.data_basis === "simulated" && <BasisBadge basis="simulated" />}
          </div>
        </div>
        <Card className="grid min-w-[260px] grid-cols-2 gap-x-6 gap-y-2 p-5 text-[12.5px]">
          <span className="text-text-faint">Ancienneté</span><span className="text-right">{years ? `${years} an(s)` : "—"}</span>
          <span className="text-text-faint">Horaires</span><span className="text-right">{e.weekly_hours ? `${e.weekly_hours} h / sem.` : "—"}</span>
          <span className="text-text-faint">Congés restants</span><span className="text-right">{e.leave_days_remaining ?? "—"} j</span>
          <span className="text-text-faint">Compétences</span><span className="text-right">{e.skills.join(", ") || "—"}</span>
        </Card>
      </div>

      <EmployeeActions employeeId={e.id} canWrite={can(me?.permissions, "write:people")} canCost={e.can_view_costs} />

      <section>
        <SectionLabel>Coût pour l&rsquo;entreprise</SectionLabel>
        {!e.can_view_costs || !e.cost ? (
          <Card className="p-5 text-[13px] text-text-faint">Rémunération et coût : accès réservé aux profils autorisés par la direction.</Card>
        ) : (
          <Card className="p-6">
            <div className="flex flex-wrap items-center gap-3">
              <p className="figure text-[24px]">≈ {fmtMoneyRange(e.cost.total_min, e.cost.total_max)} / an</p>
              <BasisBadge basis={e.cost.basis as ValueBasis} />
              <span className="text-[12px] text-text-faint">{CONFIDENCE_LABEL[e.cost.confidence as Confidence]}</span>
            </div>
            <p className="mt-1 text-[12px] text-text-faint">{e.cost.explanation}</p>
            <ul className="mt-4 space-y-1.5 text-[13px]">
              {e.cost.lines.map((l, i) => (
                <li key={i} className="flex flex-wrap items-center gap-2">
                  <span className="min-w-[220px] text-text">{l.label}</span>
                  <span className="font-mono">{fmtMoneyRange(l.annual_min, l.annual_max)}</span>
                  <BasisBadge basis={l.basis as ValueBasis} />
                  {l.source && <span className="text-[11.5px] text-text-faint">{l.source}</span>}
                </li>
              ))}
            </ul>
            {e.cost.missing.map((m) => <p key={m} className="mt-1 text-[12px] text-text-faint">⚠ {m}</p>)}
          </Card>
        )}
      </section>

      <section>
        <SectionLabel>Contribution estimée</SectionLabel>
        <Card className="p-6">
          <p className="text-[13.5px] text-text">{e.contribution.statement}</p>
          <p className="mt-1 text-[12px] text-text-faint">Confiance : {CONFIDENCE_LABEL[e.contribution.confidence as Confidence] ?? e.contribution.confidence}. Estimation partielle, jamais un jugement sur la personne ni un classement.</p>
          <ul className="mt-4 space-y-1.5 text-[13px]">
            {e.contribution.components.map((c) => (
              <li key={c.label} className="flex flex-wrap items-center gap-2">
                <span className="min-w-[220px] text-text-soft">{c.label}</span>
                <span className="font-medium text-text">{c.value}</span>
                <BasisBadge basis={c.basis as ValueBasis} />
                {c.detail && <span className="text-[11.5px] text-text-faint">{c.detail}</span>}
              </li>
            ))}
          </ul>
        </Card>
      </section>

      {e.suggestions.length > 0 && (
        <section>
          <SectionLabel>Suggestions de l&rsquo;IA</SectionLabel>
          {e.suggestions.map((s) => (
            <Card key={s.title} className="p-5">
              <p className="text-[13.5px] font-semibold text-text">{s.title}</p>
              <p className="mt-1 text-[12.5px] text-text-soft">{s.reasons.join(" · ")}</p>
              <p className="mt-1 text-[11.5px] text-text-faint">{s.note}</p>
            </Card>
          ))}
        </section>
      )}

      <section>
        <SectionLabel>Tâches ({e.tasks.open} ouvertes · {e.tasks.done_recent} terminées sur {e.tasks.window_days} j)</SectionLabel>
        {e.task_list.length === 0 ? (
          <EmptyState message="Aucune tâche assignée." />
        ) : (
          <ul className="space-y-2">
            {e.task_list.map((t) => (
              <li key={t.id} className="flex items-center justify-between gap-3 rounded-xl border border-border bg-surface px-4 py-2.5 text-[13px]">
                <Link href={`/actions/tasks?task=${t.id}`} className="text-text hover:underline">{t.title}</Link>
                <span className="text-[12px] text-text-faint">{t.status} · échéance <span className="num">{fmtDate(t.due_at)}</span></span>
              </li>
            ))}
          </ul>
        )}
      </section>

      {e.decisions.length > 0 && (
        <section>
          <SectionLabel>Décisions</SectionLabel>
          <ul className="space-y-2">
            {e.decisions.map((d) => (
              <li key={d.id} className="flex items-center justify-between gap-3 rounded-xl border border-border bg-surface px-4 py-2.5 text-[13px]">
                <span className="text-text">{d.title}</span>
                <Badge label={d.status === "pending_validation" ? "En attente de validation" : d.status === "executed" ? "Appliquée" : d.status === "rejected" ? "Refusée" : d.status} tone={d.status === "executed" ? "success" : d.status === "pending_validation" ? "warning" : "neutral"} />
              </li>
            ))}
          </ul>
        </section>
      )}

      {context && <RelatedObjects groups={context.related} exclude={["task"]} />}
      {context && <ObjectTimeline entries={context.timeline} />}
    </main>
  );
}
