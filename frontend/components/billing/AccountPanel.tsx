import Link from "next/link";
import SectionLabel from "@/components/objects/SectionLabel";
import Badge from "@/components/ui/Badge";
import Card from "@/components/ui/Card";
import { fmtDate, fmtMoney } from "@/lib/objects";
import type { AccountStatementEntry, PartyAccount } from "@/lib/types";

const KIND_LABEL: Record<AccountStatementEntry["kind"], string> = {
  invoice: "Facture",
  payment: "Règlement",
  unallocated_payment: "Paiement à rapprocher",
  credit_note: "Avoir imputé",
  refund: "Remboursement",
};

// One balance per customer/supplier, derived from invoices, payments,
// imputed credit notes and refunds (backend app.billing.party_account) --
// the same numbers as the orders and Finance. The statement below is the
// explanation of every euro of the balance.
export default function AccountPanel({ account: a, title }: { account: PartyAccount; title?: string }) {
  const isCustomer = a.party_type === "customer";
  const balanceLabel = isCustomer ? (a.balance >= 0 ? "Doit à l'entreprise" : "Nous lui devons") : a.balance >= 0 ? "Nous lui devons" : "Nous doit";
  const tiles: { label: string; value: number; hint: string; tone?: string }[] = [
    { label: isCustomer ? "Facturé" : "Facturé par le fournisseur", value: a.invoiced, hint: "Factures émises (hors brouillons et annulées)" },
    { label: isCustomer ? "Payé" : "Réglé", value: a.paid, hint: "Paiements enregistrés et rapprochés d'une facture" },
    { label: "Reste à payer", value: a.outstanding, hint: "Somme des restes dus des factures ouvertes" },
    { label: "En retard", value: a.overdue, hint: "Échéances dépassées et non réglées", tone: a.overdue > 0 ? "text-danger" : "" },
  ];
  return (
    <section>
      <SectionLabel>{title ?? (isCustomer ? "Compte client" : "Compte fournisseur")}</SectionLabel>
      <Card className="p-5">
        <div className="flex flex-wrap items-baseline gap-3">
          <p className="text-[12.5px] text-text-soft">{balanceLabel}</p>
          <p className={`figure text-[26px] ${a.balance < 0 ? "text-warning" : a.overdue > 0 ? "text-danger" : ""}`}>{fmtMoney(Math.abs(a.balance), true)}</p>
          {a.is_up_to_date && <Badge label="Compte à jour" tone="success" />}
          {a.has_simulated && <Badge label="Données simulées" tone="danger" />}
        </div>
        <div className="mt-4 grid grid-cols-2 gap-4 sm:grid-cols-4">
          {tiles.map((t) => (
            <div key={t.label} title={t.hint}>
              <p className="text-[12px] text-text-soft">{t.label}</p>
              <p className={`num mt-0.5 text-[15px] font-semibold ${t.tone ?? "text-text"}`}>{fmtMoney(t.value, true)}</p>
            </div>
          ))}
        </div>
        <ul className="mt-4 space-y-1 text-[12.5px] text-text-soft">
          {a.next_due && (
            <li>
              Prochaine échéance : <span className="num font-medium text-text">{fmtMoney(a.next_due.remaining, true)}</span> le <span className="num">{fmtDate(a.next_due.due_at)}</span> ·{" "}
              <Link href={`/documents/${a.next_due.invoice_id}#reglements`} className="num hover:underline">{a.next_due.invoice_number}</Link>
              {a.next_due.state === "overdue" && <span className="text-danger"> — en retard de {a.next_due.days_late} j</span>}
            </li>
          )}
          {a.unallocated > 0 && <li>Paiements reçus à rapprocher d&rsquo;une facture : <span className="num font-medium text-text">{fmtMoney(a.unallocated, true)}</span></li>}
          {a.refund_due > 0 && <li className="text-warning">Remboursement dû au client (avoir imputé sur une facture déjà payée) : <span className="num font-semibold">{fmtMoney(a.refund_due, true)}</span></li>}
          {a.credit_on_account > 0 && <li>Crédit disponible sur le compte : <span className="num font-medium text-text">{fmtMoney(a.credit_on_account, true)}</span></li>}
          {a.pending_credit_notes.map((p) => (
            <li key={p.id}>
              Avoir <Link href={`/documents/${p.id}#avoir`} className="num hover:underline">{p.number}</Link> — <span className="num">{fmtMoney(p.amount, true)}</span> · {p.status_label} <span className="text-text-faint">(non déduit)</span>
            </li>
          ))}
        </ul>

        {a.open_invoices.length > 0 && (
          <ul className="mt-4 space-y-1.5">
            {a.open_invoices.map((i) => (
              <li key={i.id}>
                <Link href={`/documents/${i.id}#reglements`} className="flex flex-wrap items-center gap-3 rounded-xl border border-border bg-surface-alt px-4 py-2 text-[12.5px] transition-colors hover:border-border-strong">
                  <span className="num font-medium text-text">{i.number}</span>
                  <Badge label={i.state_label} tone={i.is_late ? "danger" : "accent"} />
                  {i.installments_count > 1 && <span className="num text-text-faint">{i.installments_paid}/{i.installments_count} échéances</span>}
                  <span className="num ml-auto font-semibold text-text">reste {fmtMoney(i.remaining, true)}</span>
                </Link>
              </li>
            ))}
          </ul>
        )}

        {a.statement.length > 0 && (
          <details className="group mt-4">
            <summary className="cursor-pointer list-none text-[12.5px] font-medium text-accent hover:underline">
              <span className="group-open:hidden">Voir les {a.statement.length} opérations qui expliquent le solde</span>
              <span className="hidden group-open:inline">Masquer le relevé</span>
            </summary>
            <div className="mt-3 overflow-x-auto">
              <table className="w-full min-w-[560px] text-[12.5px]">
                <thead className="text-left text-text-faint">
                  <tr className="border-b border-border">
                    <th className="py-2 pr-3 font-medium">Date</th>
                    <th className="py-2 pr-3 font-medium">Opération</th>
                    <th className="py-2 pr-3 font-medium">Réf. compte</th>
                    <th className="py-2 pr-3 text-right font-medium">Montant</th>
                    <th className="py-2 text-right font-medium">Solde</th>
                  </tr>
                </thead>
                <tbody>
                  {a.statement.map((e, i) => (
                    <tr key={i} className="border-b border-border last:border-0 hover:bg-surface-alt" title={e.note ?? undefined}>
                      <td className="num py-2 pr-3 text-text-faint">{fmtDate(e.date)}</td>
                      <td className="py-2 pr-3 text-text">
                        <span className="text-text-faint">{KIND_LABEL[e.kind]} · </span>
                        {e.document_id ? <Link href={`/documents/${e.document_id}`} className="hover:underline">{e.label}</Link> : e.label}
                        {e.simulated && <span className="ml-1.5 text-[10.5px] text-danger">simulé</span>}
                        {e.note && <span className="block text-[11px] text-text-faint">{e.note}</span>}
                      </td>
                      <td className="num py-2 pr-3 text-text-faint">{e.account_ref ?? "—"}</td>
                      <td className={`num py-2 pr-3 text-right ${e.amount < 0 ? "text-success" : "text-text"}`}>
                        {e.amount > 0 ? "+" : "−"}
                        {fmtMoney(Math.abs(e.amount), true)}
                      </td>
                      <td className="num py-2 text-right font-medium text-text">{fmtMoney(e.balance, true)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <p className="mt-2 text-[11.5px] text-text-faint">{a.method} Les références de compte (ex. 411, 512) ne s&rsquo;affichent qu&rsquo;une fois configurées avec votre comptable.</p>
            </div>
          </details>
        )}
        {a.statement.length === 0 && <p className="mt-3 text-[12.5px] text-text-faint">Aucune facture émise ni paiement enregistré pour l&rsquo;instant.</p>}
      </Card>
    </section>
  );
}
