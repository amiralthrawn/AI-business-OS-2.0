import Link from "next/link";
import { notFound } from "next/navigation";
import PriorityCard from "@/components/intelligence/PriorityCard";
import BasisBadge from "@/components/objects/BasisBadge";
import BenchmarkPanel from "@/components/objects/BenchmarkPanel";
import ObjectActions from "@/components/objects/ObjectActions";
import ObjectAskAI from "@/components/objects/ObjectAskAI";
import ObjectBreadcrumb from "@/components/objects/ObjectBreadcrumb";
import ObjectTimeline from "@/components/objects/ObjectTimeline";
import RelatedObjects from "@/components/objects/RelatedObjects";
import SectionLabel from "@/components/objects/SectionLabel";
import Badge from "@/components/ui/Badge";
import Card from "@/components/ui/Card";
import EmptyState from "@/components/ui/EmptyState";
import { TRANSACTION_STATUS_LABEL, TRANSACTION_TYPE_LABEL, formatEUR, formatPercent } from "@/lib/labels";
import { getBenchmark, getCatalogProduct, getMe, getObjectContext, getProduct } from "@/lib/api";
import { can, fmtDate, fmtDaysRange, fmtMoney, fmtNumber } from "@/lib/objects";

export const dynamic = "force-dynamic";

// The product as the central object (V2): who can supply it and on which
// terms, how much exists where, which deals it is in, how it performs, what
// to do next -- all from one page.
export default async function ProductDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;

  let product;
  try {
    product = await getProduct(id);
  } catch {
    notFound();
  }
  const [catalog, context, benchmark, me] = await Promise.all([
    getCatalogProduct(id),
    getObjectContext("product", id),
    getBenchmark(id, 1).catch(() => null),
    getMe().catch(() => null),
  ]);

  return (
    <main className="space-y-10 p-8 md:p-12">
      <ObjectBreadcrumb section={{ label: "Catalogue", href: "/data/products" }} chain={context.breadcrumb} />

      <div className="animate-reveal flex flex-wrap items-start justify-between gap-6">
        <div>
          <p className="text-[12.5px] font-semibold uppercase tracking-wide text-text-faint">{product.sku ?? "Pas de référence"}</p>
          <h1 className="mt-1.5 font-display text-[28px] italic text-text">{product.name}</h1>
          <p className="mt-1 text-[13px] text-text-faint">{[catalog.brand, catalog.manufacturer, catalog.category].filter(Boolean).join(" · ")}</p>
        </div>
        <Card className="grid min-w-[280px] grid-cols-[auto_1fr] items-center gap-x-6 gap-y-2 p-5 text-[12.5px]">
          <span className="text-text-faint">Prix de vente</span>
          <span className="flex items-center justify-end gap-1.5 font-mono font-semibold">{fmtMoney(catalog.sale_price, true)} {catalog.sale_price !== null && <BasisBadge basis={catalog.sale_price_basis} />}</span>
          <span className="text-text-faint">Coût de référence</span>
          <span className="flex items-center justify-end gap-1.5 font-mono font-semibold">{fmtMoney(catalog.unit_cost, true)} <BasisBadge basis={catalog.unit_cost_basis} /></span>
          <span className="text-text-faint">Tendance de marge</span>
          <span className="text-right">
            {product.margin_trend === "deteriorating" ? "En baisse" : product.margin_trend === "improving" ? "En hausse" : product.margin_trend === "stable" ? "Stable" : "Données insuffisantes"}
            {product.recent_margin_pct !== null && <span className="text-text-faint"> · <span className="num">{formatPercent(product.recent_margin_pct * 100)}</span></span>}
          </span>
        </Card>
      </div>

      <ObjectActions objectType="product" objectId={id} actions={context.actions} />

      <section>
        <SectionLabel>Fournisseurs et conditions</SectionLabel>
        {catalog.suppliers.length === 0 ? (
          <EmptyState message="Aucun fournisseur rattaché." hint="Un fournisseur est rattaché automatiquement dès qu'il chiffre ou livre ce produit." />
        ) : (
          <Card className="overflow-x-auto p-0">
            <table className="w-full min-w-[760px] text-[12.5px]">
              <thead className="text-left text-text-faint">
                <tr className="border-b border-border">
                  <th className="px-4 py-2.5 font-medium">Fournisseur</th>
                  <th className="px-4 py-2.5 font-medium">Prix</th>
                  <th className="px-4 py-2.5 font-medium">Délai</th>
                  <th className="px-4 py-2.5 font-medium">MOQ / SPQ</th>
                  <th className="px-4 py-2.5 font-medium">Paiement · origine</th>
                  <th className="px-4 py-2.5 font-medium">Normes</th>
                </tr>
              </thead>
              <tbody>
                {catalog.suppliers.map((s) => (
                  <tr key={s.id} className="border-b border-border last:border-0">
                    <td className="px-4 py-2.5">
                      <Link href={`/data/suppliers/${s.supplier_id}`} className="font-medium text-text hover:underline">{s.supplier_name}</Link>
                      {s.is_preferred && <span className="ml-2"><Badge label="Préféré" tone="accent" /></span>}
                      {s.supplier_reference && <p className="font-mono text-[11px] text-text-faint">réf. {s.supplier_reference}</p>}
                    </td>
                    <td className="px-4 py-2.5">
                      <span className="num flex items-center gap-1.5">{fmtMoney(s.unit_price, true)} {s.unit_price !== null && <BasisBadge basis={s.price_basis} />}</span>
                      <p className="num text-[11px] text-text-faint">{s.last_confirmed_at ? `confirmé le ${fmtDate(s.last_confirmed_at)}` : "jamais reconfirmé"}</p>
                    </td>
                    <td className="px-4 py-2.5"><span className="num flex items-center gap-1.5">{fmtDaysRange(s.lead_time_min_days, s.lead_time_max_days)} {s.lead_time_min_days !== null && <BasisBadge basis={s.lead_time_basis} />}</span></td>
                    <td className="px-4 py-2.5">{s.moq ?? "—"} / {s.spq ?? "—"}</td>
                    <td className="px-4 py-2.5">{s.payment_terms ?? "—"} · {s.country_of_origin ?? "—"}</td>
                    <td className="px-4 py-2.5">{s.certifications.length ? s.certifications.join(", ") : "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Card>
        )}
      </section>

      <section>
        <SectionLabel>Stock</SectionLabel>
        <div className="grid gap-4 md:grid-cols-3">
          {([
            ["physical", "Physique"],
            ["supplier", "Chez les fournisseurs"],
            ["potential", "Potentiel"],
          ] as const).map(([kind, label]) => (
            <Card key={kind} className="p-5">
              <p className="text-[13px] text-text-soft">{label}</p>
              {catalog.stock[kind].length === 0 ? (
                <p className="mt-2 text-[13px] text-text-faint">Inconnu</p>
              ) : (
                <ul className="mt-2 space-y-1.5">
                  {catalog.stock[kind].map((s) => (
                    <li key={s.id} className="flex flex-wrap items-center gap-1.5 text-[13px]">
                      <span className="font-mono font-semibold text-text">{fmtNumber(s.quantity)}</span>
                      <BasisBadge basis={s.basis} />
                      <span className="text-[11.5px] text-text-faint">{s.supplier_name ?? s.location ?? ""} · <span className="num">{fmtDate(s.as_of)}</span></span>
                    </li>
                  ))}
                </ul>
              )}
            </Card>
          ))}
        </div>
      </section>

      {benchmark && benchmark.candidates.length > 0 && <BenchmarkPanel initial={benchmark} canAct={can(me?.permissions, "write:procurement")} />}

      {product.intelligence.length > 0 && (
        <section>
          <SectionLabel>Intelligence</SectionLabel>
          <div className="space-y-3">
            {product.intelligence.map((signal, i) => (
              <PriorityCard key={i} signal={signal} />
            ))}
          </div>
        </section>
      )}

      <RelatedObjects groups={context.related} exclude={["supplier", "transaction"]} />

      <section>
        <SectionLabel>Transactions récentes</SectionLabel>
        {product.transactions.length === 0 ? (
          <EmptyState message="Aucune transaction." />
        ) : (
          <ul className="space-y-2">
            {product.transactions.map((t) => (
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

      <ObjectAskAI objectType="product" objectId={id} suggestions={[`Quel fournisseur contacter pour ${product.name} ?`]} />
      <ObjectTimeline entries={context.timeline} />
    </main>
  );
}
