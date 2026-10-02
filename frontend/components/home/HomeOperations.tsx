import Link from "next/link";
import Card from "@/components/ui/Card";
import { getBillingOverview, getFollowUps, getTasks, listDocuments } from "@/lib/api";
import { fmtMoney } from "@/lib/objects";

// V2: the day-to-day operations waiting on someone, each a link into the
// right workspace tab -- the Command Center points to the objects, it does
// not duplicate them.
export default async function HomeOperations() {
  const [deals, purchaseRequests, followUps, tasks, billing] = await Promise.all([
    listDocuments({ kind: ["customer_request"], open_only: true }).catch(() => []),
    listDocuments({ kind: ["purchase_request"], open_only: true }).catch(() => []),
    getFollowUps().catch(() => null),
    getTasks().catch(() => []),
    // V2.2 -- visible to profiles that can see Finance (backend view:finance).
    getBillingOverview().catch(() => null),
  ]);
  const overdue = followUps?.items.filter((i) => i.overdue_days > 0).length ?? 0;
  const emailsToValidate = tasks.filter((t) => t.status === "pending_validation" && t.pending_action === "send_email").length;
  const pipeline = deals.reduce((sum, d) => sum + (d.total ?? 0), 0);

  const cards = [
    { href: "/business/sales?tab=deals", label: "Affaires en cours", value: String(deals.length), hint: pipeline ? `${fmtMoney(pipeline)} chiffrés` : "Aucune chiffrée" },
    { href: "/business/sales?tab=followups", label: "Relances en retard", value: String(overdue), hint: `${followUps?.items.length ?? 0} à surveiller`, alert: overdue > 0 },
    { href: "/business/procurement?tab=requests", label: "Demandes d'achat ouvertes", value: String(purchaseRequests.length), hint: "Comparaison fournisseurs" },
    { href: "/actions/tasks", label: "Emails à valider", value: String(emailsToValidate), hint: "Rien ne part sans validation", alert: emailsToValidate > 0 },
  ];
  // Money and goods waiting on someone: what is late to collect, the credit
  // notes to handle (validation, imputation, refund), the orders the customer
  // has not confirmed yet, the deliveries to watch.
  const creditsToHandle = billing?.credit_notes.filter((c) => c.needs_action) ?? [];
  const creditValidations = creditsToHandle.filter((c) => c.validation_task_id).length;
  const deliveriesLate = billing?.deliveries_to_watch.filter((d) => d.is_late || d.nonconforming > 0).length ?? 0;
  const billingCards = billing
    ? [
        { href: "/business/finance#encaissements", label: "À encaisser en retard", value: fmtMoney(billing.receivables.overdue), hint: `${billing.receivables.overdue_invoices.length} facture(s) · ${fmtMoney(billing.receivables.outstanding)} à encaisser au total`, alert: billing.receivables.overdue > 0 },
        { href: "/business/finance#encaissements", label: "Avoirs à traiter", value: String(creditsToHandle.length), hint: creditValidations ? `${creditValidations} validation(s) interne(s) en attente` : "Réponses clients, imputations, remboursements", alert: creditValidations > 0 },
        { href: "/business/sales?tab=orders", label: "Commandes à confirmer", value: String(billing.orders_awaiting_confirmation.length), hint: `${billing.orders_awaiting_confirmation.filter((o) => o.status === "sent").length} sans accusé de réception` },
        { href: "/business/procurement?tab=orders", label: "Livraisons à surveiller", value: String(billing.deliveries_to_watch.length), hint: deliveriesLate ? `${deliveriesLate} en retard ou non conforme(s)` : "Partielles ou en transit", alert: deliveriesLate > 0 },
      ]
    : [];

  return (
    <section>
      <span className="mb-5 block text-[11.5px] font-bold tracking-wide text-text-faint uppercase">Opérations en cours</span>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {[...cards, ...billingCards].map((c) => (
          <Link key={c.label} href={c.href}>
            <Card className="h-full p-5 transition-colors hover:border-border-strong">
              <p className="text-[12.5px] text-text-soft">{c.label}</p>
              <p className={`mt-1.5 figure text-[24px] ${c.alert ? "text-danger" : "text-text"}`}>{c.value}</p>
              <p className="text-[11.5px] text-text-faint">{c.hint}</p>
            </Card>
          </Link>
        ))}
      </div>
    </section>
  );
}
