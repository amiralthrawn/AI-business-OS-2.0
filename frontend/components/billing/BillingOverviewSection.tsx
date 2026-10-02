import Link from "next/link";
import SectionLabel from "@/components/objects/SectionLabel";
import Badge from "@/components/ui/Badge";
import Card from "@/components/ui/Card";
import EmptyState from "@/components/ui/EmptyState";
import { fmtDate, fmtMoney } from "@/lib/objects";
import type { BillingOverview } from "@/lib/types";

const REF_LABELS: Record<string, string> = {
  customer_receivable: "Comptes clients",
  supplier_payable: "Comptes fournisseurs",
  bank: "Banque",
  purchases: "Achats",
  sales: "Ventes",
};

// Finance's day-to-day follow-up (MICRO), computed at read time from the
// invoices, recorded payments and imputed credit notes -- the same derived
// numbers as each customer/supplier page and each order.
export default function BillingOverviewSection({ data }: { data: BillingOverview }) {
  const r = data.receivables;
  const creditsToHandle = data.credit_notes.filter((c) => c.needs_action);
  return (
    <section id="encaissements" className="scroll-mt-6 space-y-5">
      <SectionLabel>Encaissements, règlements et avoirs</SectionLabel>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {[
          { label: "À encaisser", value: r.outstanding, hint: "Reste dû sur les factures clients émises" },
          { label: "dont en retard", value: r.overdue, hint: "Échéances clients dépassées non réglées", tone: r.overdue > 0 ? "text-danger" : "" },
          { label: "À payer aux fournisseurs", value: data.payables.outstanding, hint: "Reste dû sur les factures fournisseurs reçues" },
          { label: "Remboursements dus", value: data.refunds_due, hint: "Avoirs imputés sur des factures déjà payées", tone: data.refunds_due > 0 ? "text-warning" : "" },
        ].map((t) => (
          <div key={t.label} title={t.hint}>
            <Card className="h-full p-5">
              <p className="text-[12.5px] text-text-soft">{t.label}</p>
              <p className={`figure mt-1 text-[22px] ${t.tone ?? ""}`}>{fmtMoney(t.value, true)}</p>
            </Card>
          </div>
        ))}
      </div>

      <div className="grid gap-5 lg:grid-cols-2">
        <Card className="min-w-0 p-5">
          <p className="mb-3 text-[13px] font-semibold text-text">Échéances clients</p>
          {r.upcoming.length === 0 ? (
            <EmptyState message="Aucune échéance en cours." />
          ) : (
            <ul className="space-y-1.5">
              {r.upcoming.map((u) => (
                <li key={`${u.invoice_id}-${u.due_at}`}>
                  <Link href={`/documents/${u.invoice_id}#reglements`} className="flex flex-wrap items-center gap-x-3 gap-y-1 rounded-xl border border-border px-3 py-2 text-[12.5px] transition-colors hover:border-border-strong">
                    <span className={`num w-[88px] ${u.state === "overdue" ? "text-danger" : "text-text-faint"}`}>{fmtDate(u.due_at)}</span>
                    <span className="min-w-0 flex-1 truncate text-text">
                      {u.party} · <span className="num">{u.invoice_number}</span>
                      {u.label && <span className="text-text-faint"> · {u.label}</span>}
                    </span>
                    {u.state === "overdue" && <Badge label={`+${u.days_late} j`} tone="danger" />}
                    <span className="num font-semibold text-text">{fmtMoney(u.amount, true)}</span>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </Card>

        <Card className="min-w-0 p-5">
          <p className="mb-3 text-[13px] font-semibold text-text">Avoirs et réclamations à suivre</p>
          {creditsToHandle.length === 0 ? (
            <EmptyState message="Aucun avoir en attente." />
          ) : (
            <ul className="space-y-1.5">
              {creditsToHandle.map((c) => (
                <li key={c.id}>
                  <Link href={`/documents/${c.id}#avoir`} className="flex flex-wrap items-center gap-x-3 gap-y-1 rounded-xl border border-border px-3 py-2 text-[12.5px] transition-colors hover:border-border-strong">
                    <span className="num font-medium text-text">{c.number}</span>
                    <span className="min-w-0 flex-1 truncate text-text-soft">{c.party}</span>
                    <Badge label={c.validation_task_id ? "Validation en attente" : c.refund_due > 0 ? `Remboursement dû ${fmtMoney(c.refund_due, true)}` : c.status_label} tone={c.validation_task_id || c.refund_due > 0 ? "warning" : "accent"} />
                    <span className="num font-semibold text-text">{fmtMoney(c.amount, true)}</span>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>

      {data.unallocated_payments.length > 0 && (
        <Card className="p-5">
          <p className="text-[13px] font-semibold text-text">Paiements à rapprocher</p>
          <p className="mb-3 text-[11.5px] text-text-faint">Mouvements réels enregistrés sans facture associée : à rattacher à la bonne facture (le solde du tiers les compte déjà s&rsquo;il est connu).</p>
          <ul className="space-y-1.5 text-[12.5px]">
            {data.unallocated_payments.map((p) => (
              <li key={p.id} className="flex flex-wrap items-center gap-3 rounded-xl border border-border px-3 py-2">
                <span className="num w-[88px] text-text-faint">{fmtDate(p.occurred_at)}</span>
                <span className="min-w-0 flex-1 truncate text-text">
                  {p.label}
                  {p.counterparty ? <span className="text-text-faint"> · {p.counterparty}</span> : <span className="text-text-faint"> · tiers non identifié</span>}
                </span>
                {p.simulated && <Badge label="Simulé" tone="danger" />}
                <span className={`num font-semibold ${p.direction === "in" ? "text-success" : "text-text"}`}>
                  {p.direction === "in" ? "+" : "−"}
                  {fmtMoney(p.amount, true)}
                </span>
              </li>
            ))}
          </ul>
        </Card>
      )}

      <Card className="p-5">
        <div className="flex flex-wrap items-center gap-2">
          <p className="text-[13px] font-semibold text-text">Références comptables</p>
          <Badge label={data.accounting_refs.status === "configured" ? "Configurées" : "À confirmer avec le comptable"} tone={data.accounting_refs.status === "configured" ? "success" : "warning"} />
        </div>
        <ul className="mt-3 grid gap-2 text-[12.5px] sm:grid-cols-2 lg:grid-cols-5">
          {Object.entries(data.accounting_refs.examples).map(([key, ex]) => {
            const configured = data.accounting_refs.configured[key];
            return (
              <li key={key} className="rounded-xl border border-border px-3 py-2">
                <p className="text-text-soft">{REF_LABELS[key] ?? key}</p>
                <p className="num text-[14px] font-semibold text-text">{configured ?? <span className="text-text-faint">ex. {ex.account}</span>}</p>
              </li>
            );
          })}
        </ul>
        <p className="mt-2 text-[11.5px] text-text-faint">{data.accounting_refs.note}</p>
      </Card>
      <p className="text-[11.5px] text-text-faint">{data.method}</p>
    </section>
  );
}
