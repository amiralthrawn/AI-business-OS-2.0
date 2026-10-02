import Link from "next/link";
import SectionLabel from "@/components/objects/SectionLabel";
import Badge from "@/components/ui/Badge";
import Card from "@/components/ui/Card";
import { fmtDate, fmtMoney } from "@/lib/objects";
import type { OrderPayment } from "@/lib/types";

// The payment position of an order, read from its invoices (never typed in):
// "2 / 3 échéances réglées · réglé 8 000 € · reste 4 000 €".
export default function OrderPaymentCard({ payment: p, partyName }: { payment: OrderPayment; partyName?: string | null }) {
  return (
    <section>
      <SectionLabel>Paiements</SectionLabel>
      <Card className="p-5">
        {p.state === "not_invoiced" ? (
          <p className="text-[13px] text-text-soft">
            Commande non facturée : aucun montant n&rsquo;est encore dû.
            {p.invoices.length > 0 && " Facture(s) en brouillon : " + p.invoices.map((i) => i.number).join(", ") + "."}
          </p>
        ) : (
          <>
            <div className="flex flex-wrap items-center gap-2">
              {partyName && <span className="text-[13.5px] font-semibold text-text">{partyName}</span>}
              <Badge label={p.state_label} tone={p.state === "paid" ? "success" : p.is_late ? "danger" : p.state === "partially_paid" ? "accent" : "neutral"} />
              {p.installments_count! > 1 && (
                <span className="num text-[12.5px] text-text-soft">
                  {p.installments_paid} / {p.installments_count} échéances réglées
                </span>
              )}
            </div>
            <div className="mt-4 grid grid-cols-2 gap-4 sm:grid-cols-4">
              <div>
                <p className="text-[12px] text-text-soft">Commande</p>
                <p className="figure mt-0.5 text-[20px]">{fmtMoney(p.order_total, true)}</p>
              </div>
              <div>
                <p className="text-[12px] text-text-soft">Montant réglé</p>
                <p className="figure mt-0.5 text-[20px]">{fmtMoney(p.paid, true)}</p>
              </div>
              <div>
                <p className="text-[12px] text-text-soft">Avoirs imputés</p>
                <p className="figure mt-0.5 text-[20px]">{fmtMoney(p.credited, true)}</p>
              </div>
              <div>
                <p className="text-[12px] text-text-soft">Reste à payer</p>
                <p className={`figure mt-0.5 text-[20px] ${p.is_late ? "text-danger" : ""}`}>{fmtMoney(p.remaining, true)}</p>
              </div>
            </div>
            {p.next_due && (
              <p className="mt-3 text-[12.5px] text-text-soft">
                Prochaine échéance : <span className="num">{fmtDate(p.next_due.due_at)}</span> — <span className="num font-medium text-text">{fmtMoney(p.next_due.remaining, true)}</span>
                {p.next_due.state === "overdue" && <span className="text-danger"> (en retard de {p.next_due.days_late} j)</span>}
              </p>
            )}
            <p className="mt-2 text-[12px] text-text-faint">
              Facture{p.invoices.length > 1 ? "s" : ""} :{" "}
              {p.invoices.map((i, idx) => (
                <span key={i.id}>
                  {idx > 0 && ", "}
                  <Link href={`/documents/${i.id}#reglements`} className="num text-text-soft hover:underline">{i.number}</Link> ({i.status_label})
                </span>
              ))}
            </p>
          </>
        )}
      </Card>
    </section>
  );
}
