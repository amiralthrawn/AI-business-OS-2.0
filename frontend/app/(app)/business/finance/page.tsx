import PriorityCard from "@/components/intelligence/PriorityCard";
import TransactionRow from "@/components/data/TransactionRow";
import AnimatedNumber from "@/components/ui/AnimatedNumber";
import Badge from "@/components/ui/Badge";
import Card from "@/components/ui/Card";
import EmptyState from "@/components/ui/EmptyState";
import ErrorBanner from "@/components/ui/ErrorBanner";
import MonthlyLineChart from "@/components/ui/MonthlyLineChart";
import PageHeader from "@/components/ui/PageHeader";
import StatCard from "@/components/ui/StatCard";
import OrderMargins from "@/components/objects/OrderMargins";
import BillingOverviewSection from "@/components/billing/BillingOverviewSection";
import { getBillingOverview, getFinanceOverview, getOrderMargins } from "@/lib/api";
import { formatPercent } from "@/lib/labels";
import type { FinanceOverview, OrderMarginRow } from "@/lib/types";

export const dynamic = "force-dynamic";

export default async function FinancePage() {
  const orderMargins: OrderMarginRow[] = await getOrderMargins().catch(() => []);
  const billing = await getBillingOverview().catch(() => null);
  let overview: FinanceOverview | null = null;
  let error: string | null = null;
  try {
    overview = await getFinanceOverview();
  } catch (err) {
    error = err instanceof Error ? err.message : "Impossible de charger la vue Finance.";
  }

  return (
    <main className="space-y-10 p-8 md:p-12">
      <PageHeader title="Finance" description="Revenus, coûts et marge, calculés à partir de toutes les transactions du Data Core." />

      {error && <ErrorBanner message={error} />}
      {overview && (
        <>
          <section className="grid gap-6 md:grid-cols-3">
            <StatCard label="Chiffre d'affaires" value={<AnimatedNumber value={overview.total_revenue} format="EUR" />} />
            <StatCard label="Coûts" value={<AnimatedNumber value={overview.total_costs} format="EUR" />} />
            <StatCard
              label="Marge globale"
              value={
                overview.overall_margin_pct !== null ? (
                  <AnimatedNumber value={overview.overall_margin_pct * 100} format="percent" />
                ) : (
                  "N/A"
                )
              }
              emphasize={(overview.overall_margin_pct ?? 0) < 0}
            />
          </section>

          {billing && <BillingOverviewSection data={billing} />}

          <OrderMargins rows={orderMargins} />

          <section>
            <span className="mb-4 block text-[11.5px] font-bold tracking-wide text-text-faint uppercase">
              Achats ↘ Finance ↗ Ventes (12 derniers mois)
            </span>
            <Card className="p-6">
              <MonthlyLineChart
                series={[
                  { key: "purchases", label: "Achats", color: "var(--color-danger)", points: overview.monthly_purchases },
                  { key: "sales", label: "Ventes", color: "var(--color-success)", points: overview.monthly_sales },
                  {
                    key: "margin",
                    label: "Écart (Ventes − Achats)",
                    color: "var(--color-accent)",
                    points: overview.monthly_sales.map((sale, i) => ({
                      month: sale.month,
                      total_amount: sale.total_amount - (overview!.monthly_purchases[i]?.total_amount ?? 0),
                      transaction_count: sale.transaction_count + (overview!.monthly_purchases[i]?.transaction_count ?? 0),
                    })),
                  },
                ]}
              />
              <p className="mt-4 text-[12px] text-text-faint">
                L&rsquo;écart croît quand les ventes progressent plus vite que les achats (marge en amélioration), et se réduit dans le cas inverse
                (compression de marge).
              </p>
            </Card>
          </section>

          {overview.intelligence.length > 0 && (
            <section>
              <span className="mb-4 block text-[11.5px] font-bold tracking-wide text-text-faint uppercase">Intelligence</span>
              <div className="space-y-3">
                {overview.intelligence.map((signal, i) => (
                  <PriorityCard key={i} signal={signal} />
                ))}
              </div>
            </section>
          )}

          <section>
            <span className="mb-4 block text-[11.5px] font-bold tracking-wide text-text-faint uppercase">Marge par produit</span>
            {overview.products.length === 0 ? (
              <EmptyState message="Aucun produit n'a encore assez de données de vente." />
            ) : (
              <Card className="divide-y divide-border p-2">
                {overview.products.map((p) => (
                  <div key={p.id} className="flex items-center justify-between px-4 py-3.5">
                    <span className="text-[13.5px] font-medium text-text">{p.name}</span>
                    <div className="flex items-center gap-2.5">
                      {p.recent_margin_pct !== null && (
                        <span className="font-mono text-[13px] font-semibold text-text">{formatPercent(p.recent_margin_pct * 100)}</span>
                      )}
                      <Badge
                        label={p.margin_trend === "deteriorating" ? "En baisse" : p.margin_trend === "improving" ? "En hausse" : "Stable"}
                        tone={p.margin_trend === "deteriorating" ? "danger" : p.margin_trend === "improving" ? "success" : "neutral"}
                      />
                    </div>
                  </div>
                ))}
              </Card>
            )}
          </section>

          <section>
            <span className="mb-4 block text-[11.5px] font-bold tracking-wide text-text-faint uppercase">Transactions récentes</span>
            <ul className="space-y-2">
              {overview.recent_transactions.length === 0 ? (
                <EmptyState message="Aucune transaction pour l'instant." />
              ) : (
                overview.recent_transactions.map((t) => <TransactionRow key={t.id} transaction={t} party="auto" />)
              )}
            </ul>
          </section>
        </>
      )}
    </main>
  );
}
