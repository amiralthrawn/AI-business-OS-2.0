import Link from "next/link";
import { notFound } from "next/navigation";
import CreateTaskButton from "@/components/actions/CreateTaskButton";
import ContactCard from "@/components/data/ContactCard";
import PriorityCard from "@/components/intelligence/PriorityCard";
import Card from "@/components/ui/Card";
import EmptyState from "@/components/ui/EmptyState";
import { TRANSACTION_STATUS_LABEL, TRANSACTION_TYPE_LABEL, formatEUR } from "@/lib/labels";
import { getCustomer, getCustomerAccount, getObjectContext, listDocuments } from "@/lib/api";
import AccountPanel from "@/components/billing/AccountPanel";
import DocumentList from "@/components/objects/DocumentList";
import ObjectActions from "@/components/objects/ObjectActions";
import ObjectBreadcrumb from "@/components/objects/ObjectBreadcrumb";
import ObjectTimeline from "@/components/objects/ObjectTimeline";
import RelatedObjects from "@/components/objects/RelatedObjects";
import SectionLabel from "@/components/objects/SectionLabel";

export const dynamic = "force-dynamic";

export default async function CustomerDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;

  let customer;
  try {
    customer = await getCustomer(id);
  } catch {
    notFound();
  }
  // V2: the object's relations, actions and documents (brain/navigation_v2.md).
  const [context, documents, account] = await Promise.all([
    getObjectContext("customer", id),
    listDocuments({ customer_id: id }),
    // V2.2: one balance, derived (backend app.billing) -- hidden if the profile has no right to it.
    getCustomerAccount(id).catch(() => null),
  ]);

  return (
    <main className="space-y-8 p-8 md:p-12">
      <ObjectBreadcrumb section={{ label: "Ventes · Clients", href: "/business/sales?tab=customers" }} chain={context.breadcrumb} />

      <div className="animate-reveal flex items-start justify-between gap-4">
        <div>
          <p className="text-[12.5px] font-semibold uppercase tracking-wide text-text-faint">{customer.country ?? "Pays inconnu"}</p>
          <h1 className="mt-1.5 font-display text-[28px] italic text-text">{customer.name}</h1>
        </div>
        <CreateTaskButton defaultTitle={`Suivre ${customer.name}`} relatedEntityType="customer" relatedEntityId={customer.id} />
      </div>

      <ObjectActions objectType="customer" objectId={customer.id} actions={context.actions} />

      {account && <AccountPanel account={account} />}

      <section>
        <SectionLabel>Affaires et documents</SectionLabel>
        <DocumentList documents={documents} empty="Aucun document commercial pour l'instant." />
      </section>

      {customer.contacts.length > 0 && (
        <section>
          <span className="mb-4 block text-[11.5px] font-bold tracking-wide text-text-faint uppercase">Contact</span>
          <div className="grid gap-4 sm:grid-cols-2">
            {customer.contacts.map((contact) => (
              <ContactCard key={contact.id} contact={contact} entityName={customer.name} entityType="customer" entityId={customer.id} />
            ))}
          </div>
        </section>
      )}

      {customer.intelligence.length > 0 && (
        <section>
          <span className="mb-4 block text-[11.5px] font-bold tracking-wide text-text-faint uppercase">Intelligence</span>
          <div className="space-y-3">
            {customer.intelligence.map((signal, i) => (
              <PriorityCard key={i} signal={signal} />
            ))}
          </div>
        </section>
      )}

      <section className="grid gap-5 sm:grid-cols-2">
        <Card className="p-6">
          <p className="text-[13px] text-text-soft">Tendance de revenu</p>
          <p className="mt-2 text-[15px] font-semibold text-text">
            {customer.revenue_trend === "growing" ? "En croissance" : customer.revenue_trend === "declining" ? "En déclin" : customer.revenue_trend === "stable" ? "Stable" : "Données insuffisantes"}
          </p>
          {customer.recent_revenue !== null && <p className="mt-1 text-[12px] text-text-faint"><span className="num">{formatEUR(customer.recent_revenue)}</span> récemment</p>}
        </Card>
        <Card className="p-6">
          <p className="text-[13px] text-text-soft">Plus ancien message sans réponse</p>
          <p className="num mt-2 text-[15px] font-semibold text-text">
            {customer.unanswered_message_age_days !== null ? `${customer.unanswered_message_age_days.toFixed(1)} jours` : "Aucun"}
          </p>
        </Card>
      </section>

      <section>
        <span className="mb-4 block text-[11.5px] font-bold tracking-wide text-text-faint uppercase">Transactions récentes</span>
        {customer.transactions.length === 0 ? (
          <EmptyState message="Aucune transaction." />
        ) : (
          <ul className="space-y-2">
            {customer.transactions.map((t) => (
              <li key={t.id} className="flex items-center justify-between rounded-xl border border-border bg-surface px-4 py-3 text-[13px]">
                <span className="text-text-soft">
                  {TRANSACTION_TYPE_LABEL[t.type] ?? t.type} &middot; {TRANSACTION_STATUS_LABEL[t.status] ?? t.status}
                </span>
                <span className="font-mono font-semibold text-text">{formatEUR(t.amount)}</span>
              </li>
            ))}
          </ul>
        )}
      </section>

      {customer.communications.length > 0 && (
        <section>
          <span className="mb-4 block text-[11.5px] font-bold tracking-wide text-text-faint uppercase">Communications récentes</span>
          <ul className="space-y-2">
            {customer.communications.map((c) => (
              <li key={c.id} className="rounded-xl border border-border bg-surface px-4 py-3 text-[13px] transition-colors hover:border-border-strong">
                <Link href={`/communications?message=${c.id}`} className="block">
                <span className="text-[11px] uppercase text-text-faint">
                  {c.channel} &middot; {c.direction === "inbound" ? "reçu" : "envoyé"}
                </span>
                <p className="mt-0.5 text-text-soft">{c.subject ?? "(pas d'objet)"}</p>
                </Link>
              </li>
            ))}
          </ul>
        </section>
      )}
      <RelatedObjects groups={context.related} exclude={["commercial_document", "transaction", "communication", "contact"]} />
      <ObjectTimeline entries={context.timeline} />
    </main>
  );
}
