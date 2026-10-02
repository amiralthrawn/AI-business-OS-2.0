import Link from "next/link";
import { notFound } from "next/navigation";
import CreateTaskButton from "@/components/actions/CreateTaskButton";
import ContactCard from "@/components/data/ContactCard";
import PriorityCard from "@/components/intelligence/PriorityCard";
import Card from "@/components/ui/Card";
import EmptyState from "@/components/ui/EmptyState";
import { TRANSACTION_STATUS_LABEL, TRANSACTION_TYPE_LABEL, formatEUR } from "@/lib/labels";
import { getObjectContext, getSupplier, getSupplierAccount, listDocuments } from "@/lib/api";
import AccountPanel from "@/components/billing/AccountPanel";
import DocumentList from "@/components/objects/DocumentList";
import ObjectActions from "@/components/objects/ObjectActions";
import ObjectBreadcrumb from "@/components/objects/ObjectBreadcrumb";
import ObjectTimeline from "@/components/objects/ObjectTimeline";
import RelatedObjects from "@/components/objects/RelatedObjects";
import SectionLabel from "@/components/objects/SectionLabel";

export const dynamic = "force-dynamic";

export default async function SupplierDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;

  let supplier;
  try {
    supplier = await getSupplier(id);
  } catch {
    notFound();
  }
  // V2: the object's relations, actions and documents (brain/navigation_v2.md).
  const [context, documents, account] = await Promise.all([getObjectContext("supplier", id), listDocuments({ supplier_id: id }), getSupplierAccount(id).catch(() => null)]);

  return (
    <main className="space-y-8 p-8 md:p-12">
      <ObjectBreadcrumb section={{ label: "Achats · Fournisseurs", href: "/business/procurement?tab=suppliers" }} chain={context.breadcrumb} />

      <div className="animate-reveal flex items-start justify-between gap-4">
        <div>
          <p className="text-[12.5px] font-semibold uppercase tracking-wide text-text-faint">{supplier.country ?? "Pays inconnu"}</p>
          <h1 className="mt-1.5 font-display text-[28px] italic text-text">{supplier.name}</h1>
        </div>
        <CreateTaskButton defaultTitle={`Suivre ${supplier.name}`} relatedEntityType="supplier" relatedEntityId={supplier.id} />
      </div>

      <ObjectActions objectType="supplier" objectId={supplier.id} actions={context.actions} />

      {account && account.statement.length > 0 && <AccountPanel account={account} />}

      <section>
        <SectionLabel>Affaires et documents</SectionLabel>
        <DocumentList documents={documents} empty="Aucun document commercial pour l'instant." />
      </section>

      {supplier.contacts.length > 0 && (
        <section>
          <span className="mb-4 block text-[11.5px] font-bold tracking-wide text-text-faint uppercase">Contact</span>
          <div className="grid gap-4 sm:grid-cols-2">
            {supplier.contacts.map((contact) => (
              <ContactCard key={contact.id} contact={contact} entityName={supplier.name} entityType="supplier" entityId={supplier.id} />
            ))}
          </div>
        </section>
      )}

      {supplier.intelligence.length > 0 && (
        <section>
          <span className="mb-4 block text-[11.5px] font-bold tracking-wide text-text-faint uppercase">Intelligence</span>
          <div className="space-y-3">
            {supplier.intelligence.map((signal, i) => (
              <PriorityCard key={i} signal={signal} />
            ))}
          </div>
        </section>
      )}

      <section className="grid gap-5 sm:grid-cols-2">
        <Card className="p-6">
          <p className="text-[13px] text-text-soft">Performance de livraison</p>
          <p className="mt-2 text-[15px] font-semibold text-text">
            {supplier.delivery_trend === "deteriorating" ? "En dégradation" : supplier.delivery_trend === "improving" ? "En amélioration" : supplier.delivery_trend === "stable" ? "Stable" : "Données insuffisantes"}
          </p>
          {supplier.recent_avg_delay_days !== null && (
            <p className="num mt-1 text-[12px] text-text-faint">{supplier.recent_avg_delay_days.toFixed(1)} jours de retard moyen récemment</p>
          )}
        </Card>
        <Card className="p-6">
          <p className="text-[13px] text-text-soft">Plus ancien message sans réponse</p>
          <p className="num mt-2 text-[15px] font-semibold text-text">
            {supplier.unanswered_message_age_days !== null ? `${supplier.unanswered_message_age_days.toFixed(1)} jours` : "Aucun"}
          </p>
        </Card>
      </section>

      <section>
        <span className="mb-4 block text-[11.5px] font-bold tracking-wide text-text-faint uppercase">Produits ({supplier.products.length})</span>
        {supplier.products.length === 0 ? (
          <EmptyState message="Aucun produit." />
        ) : (
          <ul className="space-y-2">
            {supplier.products.map((product) => (
              <li key={product.id}>
                <Link href={`/data/products/${product.id}`}>
                  <Card className="p-3.5 text-[13.5px] transition-colors hover:border-border-strong">
                    {product.name} {product.sku && <span className="text-text-faint">({product.sku})</span>}
                  </Card>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section>
        <span className="mb-4 block text-[11.5px] font-bold tracking-wide text-text-faint uppercase">Transactions récentes</span>
        {supplier.transactions.length === 0 ? (
          <EmptyState message="Aucune transaction." />
        ) : (
          <ul className="space-y-2">
            {supplier.transactions.map((t) => (
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

      {supplier.communications.length > 0 && (
        <section>
          <span className="mb-4 block text-[11.5px] font-bold tracking-wide text-text-faint uppercase">Communications récentes</span>
          <ul className="space-y-2">
            {supplier.communications.map((c) => (
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
