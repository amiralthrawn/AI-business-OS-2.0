import Badge, { type BadgeTone } from "@/components/ui/Badge";
import { valueLabel } from "@/lib/labels";
import type { TaskRead } from "@/lib/types";

// An Intelligence analysis read in three levels, for a business user
// (brain/decisions.md #57):
//   1 OBJET          what is happening (observed facts)
//   2 ANALYSE        why it matters, what the OS recommends (and with what confidence)
//   3 ACTION         what the user can do -- and the RESULT, only from what
//                    really happened (a task validated, executed, rejected...)
// Nothing here simulates an action or an outcome.

export function Level({ n, title, question, children, tone = "default" }: { n: 1 | 2 | 3; title: string; question: string; children: React.ReactNode; tone?: "default" | "muted" }) {
  return (
    <section className="relative pl-11">
      <span
        aria-hidden
        className={`absolute left-0 top-0 flex h-7 w-7 items-center justify-center rounded-full text-[12px] font-bold ${n === 3 ? "bg-text text-surface" : "bg-accent text-white"}`}
      >
        {n}
      </span>
      {n < 3 && <span aria-hidden className="absolute bottom-[-20px] left-[13px] top-8 w-px bg-border-strong" />}
      <p className="text-[11px] font-bold uppercase tracking-wide text-text-faint">{title}</p>
      <p className="text-[12px] text-text-faint">{question}</p>
      <div className={`mt-3 rounded-2xl border border-border p-5 ${tone === "muted" ? "bg-surface-alt" : "bg-surface shadow-card"}`}>{children}</div>
    </section>
  );
}

const OUTCOME: Record<string, { label: string; tone: BadgeTone; detail: string }> = {
  executed: { label: "Exécutée", tone: "success", detail: "Validée par une personne puis exécutée par l'OS." },
  done: { label: "Réalisée", tone: "success", detail: "Marquée comme faite par l'équipe." },
  in_progress: { label: "En cours", tone: "accent", detail: "Action engagée, pas encore terminée : pas de résultat final." },
  open: { label: "À faire", tone: "accent", detail: "Action décidée, pas encore réalisée : pas de résultat à ce stade." },
  pending_validation: { label: "En attente de validation", tone: "warning", detail: "Rien n'est exécuté tant qu'une personne n'a pas validé." },
  rejected: { label: "Rejetée", tone: "neutral", detail: "La proposition a été rejetée : aucune action exécutée." },
  cancelled: { label: "Annulée", tone: "neutral", detail: "Action annulée : aucun résultat." },
};

/** The RESULT, read from the tasks really attached to this subject. */
export function ActionResult({ tasks }: { tasks: TaskRead[] }) {
  if (tasks.length === 0) {
    return <p className="text-[13px] text-text-soft">Aucune action engagée : aucun résultat à ce stade.</p>;
  }
  const ordered = [...tasks].sort((a, b) => b.created_at.localeCompare(a.created_at));
  return (
    <ul className="space-y-2">
      {ordered.map((t) => {
        const o = OUTCOME[t.status] ?? { label: valueLabel("taskStatus", t.status), tone: "neutral" as BadgeTone, detail: "" };
        return (
          <li key={t.id} className="rounded-xl border border-border bg-surface-alt px-3.5 py-2.5">
            <div className="flex flex-wrap items-center gap-2">
              <Badge label={o.label} tone={o.tone} />
              <span className="text-[13px] font-medium text-text">{t.title}</span>
              <span className="num ml-auto text-[11.5px] text-text-faint">{new Date(t.created_at).toLocaleDateString("fr-FR")}</span>
            </div>
            {o.detail && <p className="mt-1 text-[12px] text-text-faint">{o.detail}</p>}
          </li>
        );
      })}
    </ul>
  );
}

export function tasksFor(tasks: TaskRead[], entityType: string | null | undefined, entityId: string | null | undefined): TaskRead[] {
  if (!entityType || !entityId) return [];
  return tasks.filter((t) => t.related_entity_type === entityType && t.related_entity_id === entityId);
}

export function impactBadges(item: { impact?: string | null; urgency?: string | null; confidence?: string | null }) {
  return (
    <div className="flex flex-wrap gap-1.5">
      {item.impact && <Badge label={`impact ${valueLabel("severity", item.impact)}`} tone={item.impact === "high" ? "danger" : item.impact === "medium" ? "warning" : "neutral"} />}
      {item.urgency && <Badge label={`urgence ${valueLabel("severity", item.urgency)}`} tone={item.urgency === "high" ? "danger" : item.urgency === "medium" ? "warning" : "neutral"} />}
      {item.confidence && <Badge label={`confiance ${valueLabel("confidence", item.confidence)}`} tone="neutral" />}
    </div>
  );
}
