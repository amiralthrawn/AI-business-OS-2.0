import Link from "next/link";
import EntityListItem from "@/components/data/EntityListItem";
import TransactionRow from "@/components/data/TransactionRow";
import PriorityCard from "@/components/intelligence/PriorityCard";
import DealPipeline from "@/components/objects/DealPipeline";
import DocumentList from "@/components/objects/DocumentList";
import FollowUpList from "@/components/objects/FollowUpList";
import SectionLabel from "@/components/objects/SectionLabel";
import WorkspaceTabs from "@/components/objects/WorkspaceTabs";
import Badge from "@/components/ui/Badge";
import Card from "@/components/ui/Card";
import EmptyState from "@/components/ui/EmptyState";
import ErrorBanner from "@/components/ui/ErrorBanner";
import MonthlyLineChart from "@/components/ui/MonthlyLineChart";
import PageHeader from "@/components/ui/PageHeader";
import StatCard from "@/components/ui/StatCard";
import { getCustomers, getFollowUps, getMe, getSalesOverview, listDocuments } from "@/lib/api";
import { formatEUR } from "@/lib/labels";
import { can } from "@/lib/objects";
import type { SalesOverview } from "@/lib/types";

export const dynamic = "force-dynamic";

const TABS = [
  { key: "overview", label: "Vue d'ensemble" },
  { key: "deals", label: "Affaires" },
  { key: "quotes", label: "Devis" },
  { key: "orders", label: "Commandes" },
  { key: "followups", label: "Relances" },
  { key: "customers", label: "Clients" },
];

// Sales workspace (V2): one entry in the navigation, the sales objects as
// sub-tabs. Each document/customer opens its own page, where everything
// related is one click away (brain/navigation_v2.md).
export default async function SalesPage({ searchParams }: { searchParams: Promise<{ tab?: string }> }) {
  const { tab = "overview" } = await searchParams;
  const active = TABS.some((t) => t.key === tab) ? tab : "overview";
  const [me, followUps] = await Promise.all([getMe().catch(() => null), getFollowUps().catch(() => null)]);
  const salesFollowUps = followUps?.items.filter((i) => i.object.domain !== "procurement") ?? [];
  const canWrite = can(me?.permissions, "write:sales");

  return (
    <main className="space-y-8 p-8 md:p-12">
      <PageHeader
        title="Ventes"
        description="Demandes clients, devis, commandes et relances — chaque affaire reliée à ses clients, produits, achats et échanges."
        action={
          canWrite ? (
            <div className="flex gap-2">
              <Link href="/documents/new?kind=customer_request" className="rounded-xl border-[1.5px] border-border-strong px-4 py-2.5 text-[13.5px] font-semibold text-text hover:border-text-faint">Nouvelle demande</Link>
              <Link href="/documents/new?kind=customer_quote" className="rounded-xl bg-text px-4 py-2.5 text-[13.5px] font-semibold text-surface hover:bg-text/90">Nouveau devis</Link>
            </div>
          ) : undefined
        }
      />
      <WorkspaceTabs
        active={active}
        tabs={TABS.map((t) => ({ ...t, href: `/business/sales?tab=${t.key}`, count: t.key === "followups" ? salesFollowUps.length : undefined }))}
      />

      {active === "overview" && <Overview />}
      {active === "deals" && <DealPipeline deals={await listDocuments({ kind: ["customer_request"] })} />}
      {active === "quotes" && <DocumentList documents={await listDocuments({ kind: ["customer_quote"] })} empty="Aucun devis." showKind={false} />}
      {active === "orders" && <Orders />}
      {active === "followups" && followUps && <FollowUpList items={salesFollowUps} note={followUps.note} canDraft={can(me?.permissions, "write:communications")} />}
      {active === "customers" && <Customers />}
    </main>
  );
}

// Orders, with the ones still waiting for the customer on top (transmitted /
// acknowledged, not confirmed), then deliveries, invoices and credit notes.
async function Orders() {
  const orders = await listDocuments({ kind: ["customer_order"] }).catch(() => []);
  const waiting = orders.filter((o) => o.status === "sent" || o.status === "acknowledged");
  return (
    <div className="space-y-8">
      {waiting.length > 0 && (
        <section>
          <SectionLabel>En attente de confirmation client</SectionLabel>
          <p className="mb-3 text-[12.5px] text-text-faint">« Transmise » : le client n&rsquo;a pas encore accusé réception. « Réception accusée » : il l&rsquo;a reçue mais ne l&rsquo;a pas encore confirmée. Rien n&rsquo;est considéré comme confirmé sans son retour enregistré.</p>
          <DocumentList documents={waiting} empty="" showKind={false} />
        </section>
      )}
      <DocumentList documents={orders} empty="Aucune commande client." showKind={false} />
      <section>
        <SectionLabel>Livraisons, factures et avoirs clients</SectionLabel>
        <DocumentList documents={await listDocuments({ kind: ["customer_delivery", "customer_invoice", "customer_credit_note"] })} empty="Aucune livraison, facture ni avoir." />
      </section>
    </div>
  );
}

async function Customers() {
  const customers = await getCustomers().catch(() => []);
  const deals = await listDocuments({ kind: ["customer_request"], open_only: true }).catch(() => []);
  const prospects = deals.filter((d) => d.party?.status === "prospect");
  return (
    <div className="space-y-8">
      <ul className="space-y-3">
        {customers.length === 0 ? (
          <EmptyState message="Aucun client pour l'instant." />
        ) : (
          customers.map((c) => (
            <li key={c.id}>
              <EntityListItem href={`/data/customers/${c.id}`} name={c.name} subtitle={`${c.country ?? "Pays inconnu"} · ${c.transaction_count} transaction(s)`} signalCount={c.signal_count} topSignalTitle={c.top_signal?.title} />
            </li>
          ))
        )}
      </ul>
      {prospects.length > 0 && (
        <section>
          <SectionLabel>Prospects avec une demande en cours</SectionLabel>
          <ul className="space-y-2">
            {prospects.map((d) => (
              <li key={d.id} className="flex items-center gap-3 rounded-xl border border-border bg-surface px-4 py-3 text-[13px]">
                <Badge label="Prospect" tone="warning" />
                <Link href={d.party!.href} className="font-medium text-text hover:underline">{d.party!.name}</Link>
                <Link href={`/documents/${d.id}`} className="text-text-soft hover:underline">{d.number} · {d.title}</Link>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}

async function Overview() {
  let overview: SalesOverview | null = null;
  let error: string | null = null;
  try {
    overview = await getSalesOverview();
  } catch (err) {
    error = err instanceof Error ? err.message : "Impossible de charger la vue Ventes.";
  }
  if (error) return <ErrorBanner message={error} />;
  if (!overview) return null;
  return (
    <>
      <section className="grid max-w-xl gap-6 sm:grid-cols-2">
        <StatCard label="Clients" value={overview.customer_count} />
        <StatCard label="Chiffre d'affaires" value={formatEUR(overview.total_revenue)} />
      </section>

      <section>
        <SectionLabel>Évolution des ventes (12 derniers mois)</SectionLabel>
        <Card className="p-6">
          <MonthlyLineChart series={[{ key: "sales", label: "Ventes", color: "var(--color-success)", points: overview.monthly_sales }]} />
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
            overview.recent_transactions.map((t) => <TransactionRow key={t.id} transaction={t} party="customer" linkParty />)
          )}
        </ul>
      </section>
    </>
  );
}
