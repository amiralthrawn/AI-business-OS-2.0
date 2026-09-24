import Link from "next/link";
import CandidateActions from "@/components/people/CandidateActions";
import SkillsGapActions from "@/components/people/SkillsGapActions";
import BasisBadge from "@/components/objects/BasisBadge";
import SectionLabel from "@/components/objects/SectionLabel";
import WorkspaceTabs from "@/components/objects/WorkspaceTabs";
import Badge from "@/components/ui/Badge";
import Card from "@/components/ui/Card";
import EmptyState from "@/components/ui/EmptyState";
import ErrorBanner from "@/components/ui/ErrorBanner";
import PageHeader from "@/components/ui/PageHeader";
import { getApplications, getCandidates, getEmployees, getMe, getSkillsGap } from "@/lib/api";
import { can, fmtMoneyRange } from "@/lib/objects";
import type { ValueBasis } from "@/lib/types";

export const dynamic = "force-dynamic";

// Équipe (V2.1): a small people layer -- who works here, what it costs (for
// authorised profiles), what they work on; and recruitment driven by the
// company's declared needs. Not an HR system (brain/people.md).
export default async function PeoplePage({ searchParams }: { searchParams: Promise<{ tab?: string; candidate?: string }> }) {
  const sp = await searchParams;
  const tab = sp.tab === "recruitment" ? "recruitment" : "employees";
  const me = await getMe().catch(() => null);
  const canWrite = can(me?.permissions, "write:people");

  return (
    <main className="space-y-8 p-8 md:p-12">
      <PageHeader title="Équipe" description="Les personnes, leur travail, leur coût et leur contribution estimée — et les compétences qui manquent." />
      <WorkspaceTabs active={tab} tabs={[{ key: "employees", label: "Employés", href: "/people" }, { key: "recruitment", label: "Compétences & recrutement", href: "/people?tab=recruitment" }]} />
      {tab === "employees" ? <Employees /> : <Recruitment canWrite={canWrite} highlight={sp.candidate} />}
    </main>
  );
}

async function Employees() {
  let employees;
  try {
    employees = await getEmployees();
  } catch (err) {
    return <ErrorBanner message={err instanceof Error ? err.message : "Accès refusé."} />;
  }
  if (employees.length === 0) return <EmptyState message="Aucun employé enregistré." />;
  return (
    <div className="space-y-3">
      {employees.some((e) => e.data_basis === "simulated") && <p className="text-[12px] text-text-faint">Les fiches marquées « Simulé » sont des données de démonstration.</p>}
      <ul className="space-y-2">
        {employees.map((e) => (
          <li key={e.id}>
            <Link href={`/people/${e.id}`} className="flex flex-wrap items-center gap-x-5 gap-y-1.5 rounded-xl border border-border bg-surface px-4 py-3 text-[13px] transition-colors hover:border-border-strong">
              <span className="min-w-[180px] flex-1">
                <span className="font-medium text-text">{e.full_name}</span>
                <span className="ml-2 text-text-faint">{[e.job_title, e.department].filter(Boolean).join(" · ")}</span>
              </span>
              {e.data_basis === "simulated" && <BasisBadge basis="simulated" />}
              <span className="text-text-soft">{e.tasks.open} tâche(s) ouverte(s){e.tasks.overdue ? ` · ${e.tasks.overdue} en retard` : ""}</span>
              {e.cost ? (
                <span className="flex items-center gap-1.5 text-text-soft">
                  ≈ <span className="num">{fmtMoneyRange(e.cost.total_min, e.cost.total_max)}</span> / an <BasisBadge basis={e.cost.basis as ValueBasis} confidence={e.cost.confidence} />
                </span>
              ) : (
                <span className="text-[12px] text-text-faint">Coût : accès réservé</span>
              )}
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}

async function Recruitment({ canWrite, highlight }: { canWrite: boolean; highlight?: string }) {
  const [gap, candidates, applications] = await Promise.all([getSkillsGap().catch(() => null), getCandidates().catch(() => []), getApplications().catch(() => [])]);
  return (
    <div className="space-y-10">
      <section>
        <SectionLabel>Compétences manquantes</SectionLabel>
        {!gap ? (
          <ErrorBanner message="Analyse indisponible." />
        ) : (
          <div className="space-y-3">
            <p className="text-[12.5px] text-text-faint">
              Besoins déclarés par l&rsquo;entreprise comparés aux compétences de l&rsquo;équipe ({gap.team_size} personnes) et à la charge observée
              {gap.open_tasks_per_person !== null ? ` (${gap.open_tasks_per_person} tâches ouvertes par personne)` : ""}.
            </p>
            {gap.gaps.length === 0 && <EmptyState message="Aucune compétence manquante parmi les besoins déclarés." />}
            {gap.gaps.map((g) => (
              <Card key={g.need_id} className="p-5">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-[14px] font-semibold text-text">{g.skill}</span>
                  <Badge label={`Priorité ${g.priority}`} tone={g.priority === "high" ? "danger" : "warning"} />
                  <Badge label={`Couverture : ${g.coverage}`} tone="neutral" />
                </div>
                {g.recommendation && (
                  <div className="mt-3 space-y-1 text-[13px] text-text-soft">
                    <p><span className="font-medium text-text">Profil suggéré :</span> {g.recommendation.profile} — compétences : {g.recommendation.skills.join(", ")}</p>
                    <p><span className="font-medium text-text">Pourquoi :</span> {g.recommendation.justification}</p>
                    <p><span className="font-medium text-text">Impact attendu :</span> {g.recommendation.impact}</p>
                  </div>
                )}
              </Card>
            ))}
            {gap.covered.length > 0 && <p className="text-[12px] text-text-faint">Besoins couverts : {gap.covered.map((c) => `${c.skill} (${c.holders.join(", ")})`).join(" · ")}</p>}
            {canWrite && <SkillsGapActions />}
          </div>
        )}
      </section>

      <section>
        <SectionLabel>Candidatures reçues</SectionLabel>
        {applications.length > 0 && (
          <ul className="mb-4 space-y-2">
            {applications.map((a) => (
              <li key={a.id} className="flex flex-wrap items-center gap-3 rounded-xl border border-dashed border-border-strong bg-surface-alt px-4 py-3 text-[13px]">
                <Link href={`/communications?message=${a.id}`} className="flex-1 text-text hover:underline">{a.subject ?? "(sans objet)"}</Link>
                <span className="text-text-faint">{a.from_address}</span>
                {canWrite && <CandidateActions mode="extract" communicationId={a.id} />}
              </li>
            ))}
          </ul>
        )}
        {candidates.length === 0 ? (
          <EmptyState message="Aucun candidat pour l'instant." hint="Les emails de candidature sont repérés dans Communications ; créez la fiche en un clic." />
        ) : (
          <div className="space-y-3">
            {candidates.map((c) => (
              <Card key={c.id} className={`p-5 ${highlight === c.id ? "border-accent" : ""}`}>
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-[14px] font-semibold text-text">{c.full_name}</span>
                  {c.applied_for && <span className="text-[13px] text-text-soft">· {c.applied_for}</span>}
                  <BasisBadge basis={c.basis as ValueBasis} />
                  <Badge label={{ new: "Nouveau", shortlisted: "Présélectionné", interview_proposed: "Entretien proposé", rejected: "Écarté", hired: "Recruté" }[c.status] ?? c.status} tone="accent" />
                  {c.communication_id && <Link href={`/communications?message=${c.communication_id}`} className="text-[12px] text-accent-strong hover:underline">Voir l&rsquo;email</Link>}
                </div>
                <p className="mt-2 text-[12.5px] text-text-soft">
                  Compétences déclarées : {c.skills.join(", ") || "aucune reconnue"}
                  {c.years_experience !== null ? ` · ${c.years_experience} an(s) d'expérience` : ""} · extraction par {c.extracted_by === "rules" ? "règles" : c.extracted_by}
                </p>
                <ul className="mt-2 space-y-1 text-[12.5px]">
                  {c.matches.map((m) => (
                    <li key={m.need_id}>
                      Besoin « {m.need} »{m.need_is_gap ? " (non couvert)" : ""} : correspondance <span className="font-semibold">{m.match}</span>
                      {m.matched_skills.length > 0 && <span className="text-text-faint"> — {m.matched_skills.join(", ")}</span>}
                    </li>
                  ))}
                </ul>
                <p className="mt-1 text-[11px] text-text-faint">Correspondance calculée sur les compétences déclarées, non vérifiées — une aide de lecture, pas une décision.</p>
                {canWrite && <div className="mt-3"><CandidateActions mode="manage" candidateId={c.id} status={c.status} /></div>}
              </Card>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
