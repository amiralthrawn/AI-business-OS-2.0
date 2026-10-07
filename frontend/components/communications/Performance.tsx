import Link from "next/link";
import BasisBadge from "@/components/objects/BasisBadge";
import SectionLabel from "@/components/objects/SectionLabel";
import Badge from "@/components/ui/Badge";
import Card from "@/components/ui/Card";
import EmptyState from "@/components/ui/EmptyState";
import { formatDateFR, formatMonthFR } from "@/lib/labels";
import type { CampaignPerformance, CampaignView, CommunicationRow, FollowUpPerformance } from "@/lib/types";
import { valueLabel } from "@/lib/labels";

const PURPOSE: Record<string, string> = {
  reply: "Réponses",
  follow_up: "Relances",
  send_quote: "Envois de devis",
  order_confirmation: "Confirmations de commande",
  rfq_price: "Demandes de prix",
  rfq_availability: "Demandes de disponibilité",
  rfq_lead_time: "Demandes de délai",
  rfq_terms: "Demandes de conditions",
  rfq_documents: "Demandes de documents",
  send_purchase_order: "Commandes fournisseur",
  brochure: "Brochures",
  nda: "NDA",
  purchase_request: "Demandes d'achat",
  generic: "Emails",
  interview_invite: "Propositions d'entretien",
  expert_request: "Demandes d'intervention",
};

function hours(h: number | null): string {
  if (h === null) return "—";
  return h < 48 ? `${h.toFixed(1)} h` : `${(h / 24).toFixed(1)} j`;
}

const messageHref = (m: CommunicationRow) => `/communications?tab=${m.direction === "inbound" ? "inbox" : "sent"}&message=${m.id}`;

// Follow-up performance: each stage counted separately (a draft is not a
// validation, a validation is not a send, a send is not a reply, a reply is
// not an order). Rates only above a minimum sample.
export function FollowUpPerformancePanel({ perf }: { perf: FollowUpPerformance }) {
  const stages = [
    { label: "Préparés", value: perf.prepared, hint: `dont ${perf.draft} brouillon(s)` },
    { label: "En attente de validation", value: perf.pending_validation },
    { label: "Validés (humain)", value: perf.validated },
    { label: "Envoyés", value: perf.sent, hint: "envoi simulé en démonstration" },
    { label: "Réponses reçues", value: perf.replies_received },
    { label: "Commandes liées", value: perf.orders_linked.length, hint: "via un document concerné" },
  ];
  const max = Math.max(1, ...stages.map((s) => s.value));
  const insufficient = `Données insuffisantes : ${perf.sent} envoi(s), minimum ${perf.min_sample}`;
  return (
    <section>
      <SectionLabel>Performance des relances et suivis</SectionLabel>
      <div className="grid gap-4 lg:grid-cols-[1.2fr_1fr]">
        <Card className="p-5">
          <ul className="space-y-2">
            {stages.map((s, i) => (
              <li key={s.label} className="group grid grid-cols-[150px_1fr_40px] items-center gap-3 text-[12.5px]">
                <span className="text-text-soft group-hover:text-text">{s.label}</span>
                <span className="relative h-[14px] rounded-full bg-surface-sunken">
                  {s.value > 0 && (
                    <span
                      className="animate-reveal absolute inset-y-0 left-0 rounded-full bg-accent opacity-80 transition-opacity group-hover:opacity-100"
                      style={{ width: `${(s.value / max) * 100}%`, animationDelay: `${i * 70}ms` }}
                      title={s.hint}
                    />
                  )}
                </span>
                <span className="num text-right font-semibold text-text">{s.value}</span>
              </li>
            ))}
          </ul>
          <p className="mt-3 text-[11.5px] leading-relaxed text-text-faint">{perf.method}</p>
        </Card>
        <div className="grid grid-cols-2 gap-3">
          {[
            { label: "Taux de réponse", value: perf.reply_rate !== null ? `${Math.round(perf.reply_rate * 100)} %` : null },
            { label: "Délai moyen de leur réponse", value: perf.avg_reply_delay_hours !== null ? hours(perf.avg_reply_delay_hours) : null },
            { label: "Notre délai moyen de réponse", value: perf.avg_our_response_hours !== null ? hours(perf.avg_our_response_hours) : null, empty: "Moins de 3 réponses envoyées" },
            { label: "En attente", value: `${perf.awaiting_their_reply} / ${perf.awaiting_our_reply}`, hint: "leur réponse / la nôtre" },
          ].map((k) => (
            <Card key={k.label} className="p-4">
              <p className="text-[12px] text-text-soft">{k.label}</p>
              {k.value !== null ? (
                <p className="figure mt-1 text-[20px]">{k.value}</p>
              ) : (
                <p className="mt-1.5 text-[12px] text-text-faint">{k.empty ?? insufficient}</p>
              )}
              {k.hint && <p className="text-[11px] text-text-faint">{k.hint}</p>}
            </Card>
          ))}
        </div>
      </div>
      {perf.orders_linked.length > 0 && (
        <p className="mt-3 text-[12.5px] text-text-soft">
          Commandes reliées :{" "}
          {perf.orders_linked.map((o, i) => (
            <span key={o.document_id}>
              {i > 0 && ", "}
              <Link href={`/documents/${o.document_id}`} className="num font-medium text-text hover:underline">{o.number ?? "commande"}</Link>
            </span>
          ))}
        </p>
      )}
      {perf.by_purpose.length > 0 && (
        <Card className="mt-4 overflow-x-auto p-0">
          <table className="w-full min-w-[420px] text-[12.5px]">
            <thead className="text-left text-text-faint">
              <tr className="border-b border-border">
                <th className="px-4 py-2 font-medium">Type</th>
                <th className="px-4 py-2 text-right font-medium">Préparés</th>
                <th className="px-4 py-2 text-right font-medium">Envoyés</th>
                <th className="px-4 py-2 text-right font-medium">Réponses</th>
              </tr>
            </thead>
            <tbody>
              {perf.by_purpose.map((b) => (
                <tr key={b.purpose} className="border-b border-border last:border-0 hover:bg-surface-alt">
                  <td className="px-4 py-2 text-text">{PURPOSE[b.purpose] ?? b.purpose}</td>
                  <td className="num px-4 py-2 text-right">{b.prepared}</td>
                  <td className="num px-4 py-2 text-right">{b.sent}</td>
                  <td className="num px-4 py-2 text-right">{b.replied}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}
    </section>
  );
}

function Metric({ label, value }: { label: string; value: number | null }) {
  return (
    <div className="rounded-lg bg-surface-sunken px-3 py-2">
      <p className="text-[11px] text-text-faint">{label}</p>
      <p className={value === null ? "text-[12px] text-text-faint" : "num text-[14px] font-semibold text-text"}>{value === null ? "Non disponible" : value}</p>
    </div>
  );
}

// Deterministic recommendations, each with the data used and its limits.
function recommendations(c: CampaignView, proposals: CommunicationRow[]) {
  const recs: { title: string; data: string; limit: string; action?: { label: string; href: string } }[] = [];
  if (c.metrics.budget === null)
    recs.push({
      title: "Enregistrer le budget réel de la campagne",
      data: "Aucun montant de budget dans les messages ni dans les documents.",
      limit: "Sans budget, ni ROI ni coût par prospect ne peuvent être calculés.",
    });
  if (c.declared.length && c.observed)
    recs.push({
      title: "Vérifier le résultat annoncé avant de le reprendre",
      data: `Déclaré : +${c.declared[0].value_pct} % (rapport interne). Observé : ${c.observed.inbound_requests} demande(s) en ${formatMonthFR(c.observed.period, false)}, ${c.observed.previous_inbound_requests} le mois précédent.`,
      limit: c.observed.previous_inbound_requests === 0 ? "Aucune demande enregistrée le mois précédent : la hausse ne peut pas être vérifiée." : "Toutes les demandes sont comptées, pas seulement celles venues de la campagne.",
    });
  recs.push({
    title: "Ajouter une source aux demandes entrantes (formulaire, code de suivi)",
    data: "Aucune demande n'est reliée à une campagne dans la base.",
    limit: "Tant que ce lien n'existe pas, prospects et ventes restent non attribués.",
  });
  if (proposals.length)
    recs.push({
      title: "Répondre à la proposition d'agence après comparaison",
      data: `${proposals.length} proposition(s) reçue(s), sans montant structuré.`,
      limit: "La réponse est un brouillon ; l'envoi passe par votre validation.",
      action: { label: "Ouvrir la proposition", href: messageHref(proposals[0]) },
    });
  return recs;
}

function CampaignCard({ c, proposals }: { c: CampaignView; proposals: CommunicationRow[] }) {
  const o = c.observed;
  return (
    <Card className="p-6">
      <div className="flex flex-wrap items-center gap-2">
        <p className="text-[15px] font-semibold text-text">Campagne {c.name}</p>
        <Badge label="Identifiée dans les messages" tone="neutral" />
      </div>

      <div className="mt-4 grid gap-3 md:grid-cols-2">
        <div className="rounded-xl border border-border p-4">
          <p className="flex items-center gap-2 text-[12px] text-text-soft">Résultat annoncé <BasisBadge basis="declared" /></p>
          {c.declared.length ? (
            <>
              <p className="figure mt-1 text-[20px]">+{c.declared[0].value_pct} %</p>
              <p className="mt-1 text-[12px] text-text-faint">« {c.declared[0].text} »</p>
              {c.reports[0] && <Link href={messageHref(c.reports[0])} className="mt-1 inline-block text-[12px] font-medium text-accent hover:underline">Voir le rapport</Link>}
            </>
          ) : (
            <p className="mt-1 text-[12px] text-text-faint">Aucun chiffre annoncé.</p>
          )}
        </div>
        <div className="rounded-xl border border-border p-4">
          <p className="flex items-center gap-2 text-[12px] text-text-soft">Demandes entrantes constatées <BasisBadge basis="observed" /></p>
          {o ? (
            <>
              <p className="mt-1 flex items-baseline gap-2">
                <span className="figure text-[20px]">{o.inbound_requests}</span>
                <span className="text-[12px] text-text-faint">
                  en {formatMonthFR(o.period, false)} · <span className="num">{o.previous_inbound_requests}</span> en {formatMonthFR(o.previous_period, false)}
                </span>
              </p>
              <p className="mt-1 text-[12px] text-text-faint">
                {o.change_pct !== null ? <>Évolution constatée : <span className="num">{o.change_pct > 0 ? "+" : ""}{Math.round(o.change_pct * 100)} %</span>. </> : "Comparaison impossible : pas de demande enregistrée le mois précédent. "}
                {o.note}
              </p>
            </>
          ) : (
            <p className="mt-1 text-[12px] text-text-faint">Période de la campagne inconnue : en attente de données.</p>
          )}
        </div>
      </div>

      <div className="mt-4 grid grid-cols-2 gap-2 sm:grid-cols-3">
        <Metric label="Budget" value={c.metrics.budget} />
        <Metric label="Prospects attribués" value={c.metrics.prospects_attributed} />
        <Metric label="Opportunités attribuées" value={c.metrics.opportunities_attributed} />
        <Metric label="Ventes attribuées" value={c.metrics.sales_attributed} />
        <Metric label="ROI" value={c.metrics.roi} />
        <Metric label="Coût par prospect" value={c.metrics.cost_per_prospect} />
      </div>
      <ul className="mt-2 space-y-0.5 text-[11.5px] text-text-faint">
        {c.limits.map((l) => <li key={l}>· {l}</li>)}
      </ul>

      <div className="mt-5">
        <p className="text-[12.5px] font-semibold text-text-soft">Retours de l&rsquo;équipe</p>
        {c.feedback.length === 0 && c.tasks.length === 0 ? (
          <p className="mt-1 text-[12px] text-text-faint">Aucun retour enregistré.</p>
        ) : (
          <ul className="mt-1.5 space-y-1 text-[12.5px]">
            {c.feedback.map((f) => (
              <li key={f.id}>
                <Link href={messageHref(f)} className="text-text hover:underline">{f.subject}</Link>{" "}
                <span className="num text-[11.5px] text-text-faint">{formatDateFR(f.occurred_at)}</span>
              </li>
            ))}
            {c.tasks.map((t) => (
              <li key={t.id}>
                <Link href="/actions/tasks" className="text-text hover:underline">{t.title}</Link> <span className="text-[11.5px] text-text-faint">tâche · {valueLabel("taskStatus", t.status)}</span>
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className="mt-5">
        <p className="text-[12.5px] font-semibold text-text-soft">Recommandations <span className="font-normal text-text-faint">(règles explicites, sans modèle de langage)</span></p>
        <ul className="mt-2 space-y-2">
          {recommendations(c, proposals).map((r) => (
            <li key={r.title} className="rounded-xl border border-border px-4 py-3 text-[12.5px]">
              <p className="font-medium text-text">{r.title}</p>
              <p className="mt-0.5 text-text-soft"><span className="text-text-faint">Données utilisées : </span>{r.data}</p>
              <p className="text-text-soft"><span className="text-text-faint">Limite : </span>{r.limit}</p>
              {r.action && <Link href={r.action.href} className="mt-1 inline-block font-medium text-accent hover:underline">{r.action.label} →</Link>}
            </li>
          ))}
        </ul>
        <p className="mt-2 text-[11.5px] text-text-faint">Aucune campagne n&rsquo;est lancée ni modifiée automatiquement : un changement de budget, de campagne ou un message passe par un brouillon ou une tâche à valider.</p>
      </div>
    </Card>
  );
}

// Marketing campaign performance, built only from what exists: declared
// report figures, observed request counts, and explicit "non disponible".
export function CampaignPerformancePanel({ data }: { data: CampaignPerformance }) {
  return (
    <section className="space-y-4">
      {data.campaigns.length === 0 ? (
        <EmptyState message="Aucune campagne identifiée." hint="Une campagne apparaît ici dès qu'un rapport ou un message la mentionne. Aucun compte publicitaire n'est connecté." />
      ) : (
        data.campaigns.map((c) => <CampaignCard key={c.name} c={c} proposals={data.agency_proposals} />)
      )}
      {data.agency_proposals.length > 0 && (
        <Card className="p-5">
          <p className="text-[12.5px] font-semibold text-text-soft">Propositions d&rsquo;agences reçues</p>
          <ul className="mt-2 space-y-1 text-[12.5px]">
            {data.agency_proposals.map((p) => (
              <li key={p.id} className="flex flex-wrap items-center gap-2">
                <Link href={messageHref(p)} className="text-text hover:underline">{p.subject}</Link>
                <span className="num text-[11.5px] text-text-faint">{formatDateFR(p.occurred_at)}</span>
                {p.source?.startsWith("simulated") && <Badge label="Simulé" tone="danger" />}
              </li>
            ))}
          </ul>
        </Card>
      )}
      <p className="text-[11.5px] text-text-faint">{data.method}</p>
    </section>
  );
}
