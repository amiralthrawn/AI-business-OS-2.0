import Link from "next/link";
import { notFound } from "next/navigation";
import CreditNotePanel from "@/components/billing/CreditNotePanel";
import FulfilmentPanel from "@/components/billing/FulfilmentPanel";
import OrderPaymentCard from "@/components/billing/OrderPaymentCard";
import SettlementPanel from "@/components/billing/SettlementPanel";
import BenchmarkPanel from "@/components/objects/BenchmarkPanel";
import DocumentLines from "@/components/objects/DocumentLines";
import MarginPanel from "@/components/objects/MarginPanel";
import ObjectActions from "@/components/objects/ObjectActions";
import ObjectAskAI from "@/components/objects/ObjectAskAI";
import ObjectBreadcrumb from "@/components/objects/ObjectBreadcrumb";
import ObjectSignals from "@/components/objects/ObjectSignals";
import ObjectTimeline from "@/components/objects/ObjectTimeline";
import RelatedObjects from "@/components/objects/RelatedObjects";
import SectionLabel from "@/components/objects/SectionLabel";
import SourcingPanel from "@/components/objects/SourcingPanel";
import Badge from "@/components/ui/Badge";
import Card from "@/components/ui/Card";
import { getDocument, getMe, getObjectContext, getSourcing } from "@/lib/api";
import { can, fmtDate, fmtMoney, statusTone } from "@/lib/objects";
import type { DocumentDetail, DocumentKind } from "@/lib/types";

export const dynamic = "force-dynamic";

const WRITE_PERMISSION: Record<DocumentKind, string> = {
  customer_request: "write:sales",
  customer_quote: "write:sales",
  customer_order: "write:sales",
  customer_delivery: "write:operations",
  customer_invoice: "write:finance",
  purchase_request: "write:procurement",
  supplier_quote: "write:procurement",
  purchase_order: "write:procurement",
  reception: "write:operations",
  supplier_invoice: "write:finance",
  customer_credit_note: "write:sales",
  supplier_credit_note: "write:procurement",
};

const DATE_LABELS: Partial<Record<DocumentKind, string>> = {
  customer_quote: "Valable jusqu'au",
  customer_order: "Livraison souhaitée",
  purchase_order: "Livraison promise",
  reception: "Attendue le",
  customer_invoice: "Échéance",
  supplier_invoice: "Échéance",
  customer_delivery: "Livraison prévue",
};

const AI_SUGGESTIONS: Partial<Record<DocumentKind, string[]>> = {
  customer_order: ["Pourquoi cette commande est-elle moins rentable que prévu ?", "Quels objets sont liés à cette commande ?"],
  customer_quote: ["Quelle marge sur ce devis ?", "Quels risques concernent ce devis ?"],
  customer_request: ["Quelle marge peut-on espérer sur cette affaire ?"],
  purchase_request: ["Quel fournisseur contacter pour cette demande ?"],
  purchase_order: ["Quels risques concernent cette commande fournisseur ?"],
  customer_invoice: ["Où en est le règlement de cette facture ?"],
  customer_credit_note: ["Pourquoi cet avoir a-t-il été proposé ?"],
};

function sectionFor(doc: DocumentDetail) {
  return doc.domain === "sales"
    ? { label: "Ventes", href: "/business/sales?tab=deals" }
    : { label: "Achats", href: "/business/procurement?tab=requests" };
}

export default async function DocumentPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  let doc: DocumentDetail;
  try {
    doc = await getDocument(id);
  } catch {
    notFound();
  }
  const [context, me] = await Promise.all([getObjectContext("commercial_document", id), getMe().catch(() => null)]);
  const canEdit = can(me?.permissions, WRITE_PERMISSION[doc.kind]);
  const sourcing = doc.kind === "purchase_request" ? await getSourcing(doc.id).catch(() => null) : null;
  const dateLabel = DATE_LABELS[doc.kind];

  return (
    <main className="space-y-10 p-8 md:p-12">
      <ObjectBreadcrumb section={sectionFor(doc)} chain={context.breadcrumb} />

      {/* OBJET -- quoi, avec qui, où en est-il */}
      <div className="animate-reveal flex flex-wrap items-start justify-between gap-6">
        <div>
          <p className="text-[12.5px] font-semibold uppercase tracking-wide text-text-faint">{doc.kind_label}</p>
          <h1 className="mt-1.5 font-display text-[28px] italic text-text">
            {doc.number}
            {doc.title && <span className="text-text-soft"> · {doc.title}</span>}
          </h1>
          <div className="mt-3 flex flex-wrap items-center gap-2 text-[13px] text-text-soft">
            <Badge label={doc.status_label} tone={statusTone(doc.status)} />
            {doc.party && (
              <Link href={doc.party.href} className="font-medium text-text hover:underline">
                {doc.party.name}
              </Link>
            )}
            {doc.party?.status === "prospect" && <Badge label="Prospect" tone="warning" />}
            {doc.source === "simulated" && <Badge label="Données de démonstration" tone="danger" />}
            {doc.contact && <span>· {doc.contact.name}</span>}
          </div>
        </div>
        <Card className="grid min-w-[280px] grid-cols-2 gap-x-6 gap-y-2 p-5 text-[12.5px]">
          <span className="text-text-faint">Montant</span>
          <span className="text-right font-mono font-semibold text-text">{doc.total !== null ? fmtMoney(doc.total) : "Incomplet"}</span>
          <span className="text-text-faint">Émis le</span>
          <span className="num text-right">{fmtDate(doc.issued_at)}</span>
          {dateLabel && (
            <>
              <span className="text-text-faint">{dateLabel}</span>
              <span className="num text-right">{fmtDate(doc.due_at)}</span>
            </>
          )}
          {doc.completed_at && (
            <>
              <span className="text-text-faint">Réalisé le</span>
              <span className="num text-right">{fmtDate(doc.completed_at)}</span>
            </>
          )}
          {doc.follow_up_at && (
            <>
              <span className="text-text-faint">Relance prévue</span>
              <span className="num text-right">{fmtDate(doc.follow_up_at)}</span>
            </>
          )}
          {doc.external_reference && (
            <>
              <span className="text-text-faint">Réf. externe</span>
              <span className="text-right font-mono">{doc.external_reference}</span>
            </>
          )}
          {doc.payment_terms && (
            <>
              <span className="text-text-faint">Conditions</span>
              <span className="text-right">{doc.payment_terms}</span>
            </>
          )}
          {(doc.carrier || doc.tracking_number) && (
            <>
              <span className="text-text-faint">Transporteur</span>
              <span className="text-right">
                {doc.carrier}
                {doc.tracking_number && <span className="num block text-text-faint">{doc.tracking_number}</span>}
              </span>
            </>
          )}
        </Card>
      </div>

      {/* ACTIONS -- que puis-je faire maintenant */}
      <ObjectActions objectType="commercial_document" objectId={doc.id} actions={context.actions} />

      {/* L'AFFAIRE -- d'où vient ce document, où va-t-il */}
      {doc.chain.length > 1 && (
        <section>
          <SectionLabel>L&rsquo;affaire complète</SectionLabel>
          <ol className="flex flex-wrap items-center gap-2">
            {doc.chain.map((d, i) => (
              <li key={d.id} className="flex items-center gap-2">
                {i > 0 && <span className="text-border-strong">→</span>}
                <Link
                  href={`/documents/${d.id}`}
                  className={`rounded-lg border px-3 py-1.5 text-[12.5px] transition-colors ${d.id === doc.id ? "border-accent bg-accent-soft font-semibold text-accent-strong" : "border-border bg-surface hover:border-border-strong"}`}
                  title={`${d.kind_label} · ${d.status_label}`}
                >
                  <span className="font-mono">{d.number}</span>
                  <span className="ml-1.5 text-text-faint">{d.party?.name ?? d.kind_label}</span>
                </Link>
              </li>
            ))}
          </ol>
        </section>
      )}

      <DocumentLines doc={doc} canEdit={canEdit} />

      {/* V2.2 -- paiements, livraisons, avoirs (brain/billing.md) */}
      {doc.settlement && <SettlementPanel settlement={doc.settlement} docId={doc.id} canWrite={can(me?.permissions, "write:finance")} />}
      {doc.payment && <OrderPaymentCard payment={doc.payment} partyName={doc.party?.name} />}
      {(doc.kind === "customer_order" || doc.kind === "purchase_order") && (
        <FulfilmentPanel fulfilment={doc.fulfilment} docId={doc.id} lines={doc.lines} canReport={false} isPhysicalDoc={false} />
      )}
      {(doc.kind === "customer_delivery" || doc.kind === "reception") && (
        <FulfilmentPanel
          fulfilment={doc.fulfilment}
          docId={doc.id}
          lines={doc.lines}
          canReport={can(me?.permissions, "write:operations") && (doc.status === "delivered" || doc.status === "received")}
          isPhysicalDoc
        />
      )}
      {doc.credit && (
        <CreditNotePanel credit={doc.credit} kind={doc.kind} docId={doc.id} canSales={can(me?.permissions, "write:sales")} canFinance={can(me?.permissions, "write:finance")} />
      )}

      {doc.margin && <MarginPanel margin={doc.margin} />}

      {doc.benchmarks?.map((b) => (
        <BenchmarkPanel key={b.product_id} initial={b} purchaseRequestId={doc.id} canAct={can(me?.permissions, "write:procurement")} />
      ))}

      {sourcing && <SourcingPanel purchaseRequestId={doc.id} initial={sourcing} canAct={can(me?.permissions, "write:procurement")} />}

      <ObjectSignals signals={context.intelligence} />

      <RelatedObjects groups={context.related} exclude={["commercial_document"]} />

      <ObjectAskAI objectType="commercial_document" objectId={doc.id} suggestions={AI_SUGGESTIONS[doc.kind] ?? ["Que faut-il savoir sur ce document ?"]} />

      <ObjectTimeline entries={context.timeline} />
    </main>
  );
}
