import Link from "next/link";
import EntityListItem from "@/components/data/EntityListItem";
import TransactionRow from "@/components/data/TransactionRow";
import PriorityCard from "@/components/intelligence/PriorityCard";
import DocumentList from "@/components/objects/DocumentList";
import FollowUpList from "@/components/objects/FollowUpList";
import SectionLabel from "@/components/objects/SectionLabel";
import WorkspaceTabs from "@/components/objects/WorkspaceTabs";
import Card from "@/components/ui/Card";
import EmptyState from "@/components/ui/EmptyState";
import ErrorBanner from "@/components/ui/ErrorBanner";
import MonthlyLineChart from "@/components/ui/MonthlyLineChart";
import PageHeader from "@/components/ui/PageHeader";
import StatCard from "@/components/ui/StatCard";
import { getFollowUps, getMe, getProcurementOverview, listDocuments } from "@/lib/api";
import { formatEUR } from "@/lib/labels";
import { can } from "@/lib/objects";
import type { ProcurementOverview } from "@/lib/types";

export const dynamic = "force-dynamic";

const TABS = [
  { key: "overview", label: "Vue d'ensemble" },
  { key: "requests", label: "Demandes d'achat" },
  { key: "quotes", label: "Devis fournisseurs" },
  { key: "orders", label: "Commandes & réceptions" },
  { key: "invoices", label: "Factures" },
  { key: "followups", label: "Relances" },
  { key: "suppliers", label: "Fournisseurs" },
];

// Procurement workspace (V2): a purchase request opens its supplier
// benchmark; the chosen supplier becomes a supplier quote or a PO derived
// from it, so the chain request -> quotes -> PO -> reception -> invoice stays
// traceable (brain/transactional_model.md).
export default async function ProcurementPage({ searchParams }: { searchParams: Promise<{ tab?: string }> }) {
  const { tab = "overview" } = await searchParams;
  const active = TABS.some((t) => t.key === tab) ? tab : "overview";
  const [me, followUps] = await Promise.all([getMe().catch(() => null), getFollowUps().catch(() => null)]);
  const procurementFollowUps = followUps?.items.filter((i) => i.object.domain === "procurement") ?? [];

  return (
    <main className="space-y-8 p-8 md:p-12">
      <PageHeader
        title="Achats"
        description="Demandes d'achat, consultation et comparaison des fournisseurs, commandes, réceptions et factures."
        action={
          can(me?.permissions, "write:procurement") ? (
            <Link href="/documents/new?kind=purchase_request" className="rounded-xl bg-text px-4 py-2.5 text-[13.5px] font-semibold text-surface hover:bg-text/90">Nouvelle demande d&rsquo;achat</Link>
          ) : undefined
        }
      />
      <WorkspaceTabs
        active={active}
        tabs={TABS.map((t) => ({ ...t, href: `/business/procurement?tab=${t.key}`, count: t.key === "followups" ? procurementFollowUps.length : undefined }))}
      />

      {active === "overview" && <Overview />}
      {active === "requests" && (
        <div className="space-y-3">
          <p className="text-[12.5px] text-text-faint">Ouvrez une demande pour comparer ses fournisseurs (prix, délais en fourchette, performance réelle, disponibilité) et agir.</p>
          <DocumentList documents={await listDocuments({ kind: ["purchase_request"] })} empty="Aucune demande d'achat." showKind={false} />
        </div>
      )}
      {active === "quotes" && <DocumentList documents={await listDocuments({ kind: ["supplier_quote"] })} empty="Aucun devis fournisseur." showKind={false} />}
      {active === "orders" && (
        <div className="space-y-8">
          <DocumentList documents={await listDocuments({ kind: ["purchase_order"] })} empty="Aucune commande fournisseur." showKind={false} />
          <section>
            <SectionLabel>Réceptions</SectionLabel>
            <DocumentList documents={await listDocuments({ kind: ["reception"] })} empty="Aucune réception." showKind={false} />
          </section>
        </div>
      )}
      {active === "invoices" && <DocumentList documents={await listDocuments({ kind: ["supplier_invoice"] })} empty="Aucune facture fournisseur." showKind={false} />}
      {active === "followups" && followUps && <FollowUpList items={procurementFollowUps} note={followUps.note} canDraft={can(me?.permissions, "write:communications")} />}
      {active === "suppliers" && <Suppliers />}
    </main>
  );
}

async function Suppliers() {
  let overview: ProcurementOverview | null = null;
  try {
    overview = await getProcurementOverview();
  } catch {
    return <ErrorBanner message="Impossible de charger les fournisseurs." />;
  }
  return (
    <ul className="space-y-3">
      {overview.suppliers.length === 0 ? (
        <EmptyState message="Aucun fournisseur pour l'instant." />
      ) : (
        overview.suppliers.map((supplier) => (
          <li key={supplier.id}>
            <EntityListItem
              href={`/data/suppliers/${supplier.id}`}
              name={supplier.name}
              subtitle={`${supplier.country ?? "Pays inconnu"} · ${supplier.product_count} produit${supplier.product_count !== 1 ? "s" : ""} · ${supplier.transaction_count} transaction${supplier.transaction_count !== 1 ? "s" : ""}`}
              signalCount={supplier.signal_count}
              topSignalTitle={supplier.top_signal?.title}
            />
          </li>
        ))
      )}
    </ul>
  );
}

async function Overview() {
  let overview: ProcurementOverview | null = null;
  let error: string | null = null;
  try {
    overview = await getProcurementOverview();
  } catch (err) {
    error = err instanceof Error ? err.message : "Impossible de charger la vue Achats.";
  }
  if (error) return <ErrorBanner message={error} />;
  if (!overview) return null;
  return (
    <>
      <section className="grid max-w-xl gap-6 sm:grid-cols-2">
        <StatCard label="Fournisseurs" value={overview.supplier_count} />
        <StatCard label="Dépenses totales" value={formatEUR(overview.total_spend)} />
      </section>

      <section>
        <SectionLabel>Évolution des achats (12 derniers mois)</SectionLabel>
        <Card className="p-6">
          <MonthlyLineChart series={[{ key: "purchases", label: "Achats", color: "var(--color-accent)", points: overview.monthly_purchases }]} />
        </Card>
      </section>

      {overview.intelligence.length > 0 && (
        <section>
          <SectionLabel>Intelligence</SectionLabel>
          <div className="space-y-3">
            {overview.intelligence.map((signal, i) => (
              <PriorityCard key={i} signal={signal} />
            ))}
          </div>
        </section>
      )}

      <section>
        <SectionLabel>Activité récente</SectionLabel>
        <ul className="space-y-2">
          {overview.recent_transactions.length === 0 ? (
            <EmptyState message="Aucune transaction pour l'instant." />
          ) : (
            overview.recent_transactions.map((t) => <TransactionRow key={t.id} transaction={t} party="supplier" linkParty />)
          )}
        </ul>
      </section>
    </>
  );
}
