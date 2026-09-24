import Link from "next/link";
import BasisBadge from "@/components/objects/BasisBadge";
import SectionLabel from "@/components/objects/SectionLabel";
import StockImport from "@/components/objects/StockImport";
import WorkspaceTabs from "@/components/objects/WorkspaceTabs";
import Card from "@/components/ui/Card";
import EmptyState from "@/components/ui/EmptyState";
import ErrorBanner from "@/components/ui/ErrorBanner";
import PageHeader from "@/components/ui/PageHeader";
import { getCatalogProducts, getMe, getStock } from "@/lib/api";
import { can, fmtDate, fmtMoney, fmtNumber } from "@/lib/objects";
import type { CatalogProduct, StockRow } from "@/lib/types";

export const dynamic = "force-dynamic";

const STOCK_KINDS: { kind: StockRow["kind"]; label: string; hint: string }[] = [
  { kind: "physical", label: "Stock physique", hint: "Ce que nous détenons (compté)." },
  { kind: "supplier", label: "Stock fournisseurs", hint: "Ce que les fournisseurs déclarent pouvoir livrer." },
  { kind: "potential", label: "Stock potentiel", hint: "Disponibilités annoncées ailleurs (site, place de marché) — le moins fiable." },
];

// Catalogue & stock (V2): the product is the central object -- its suppliers
// and their terms, its stock, its documents are on the product page; this
// workspace lists products and the three kinds of stock side by side (never summed).
export default async function CatalogPage({ searchParams }: { searchParams: Promise<{ tab?: string }> }) {
  const { tab = "products" } = await searchParams;
  const active = tab === "stock" ? "stock" : "products";
  const me = await getMe().catch(() => null);

  return (
    <main className="space-y-8 p-8 md:p-12">
      <PageHeader title="Catalogue & stock" description="Produits et prestations, fournisseurs capables de les fournir, conditions et stocks." />
      <WorkspaceTabs
        active={active}
        tabs={[
          { key: "products", label: "Produits", href: "/data/products" },
          { key: "stock", label: "Stock", href: "/data/products?tab=stock" },
        ]}
      />
      {active === "products" ? <Products /> : <Stock canImport={can(me?.permissions, "write:catalog")} />}
    </main>
  );
}

async function Products() {
  let products: CatalogProduct[] = [];
  try {
    products = await getCatalogProducts();
  } catch (err) {
    return <ErrorBanner message={err instanceof Error ? err.message : "Impossible de charger le catalogue."} />;
  }
  if (products.length === 0) return <EmptyState message="Aucun produit pour l'instant." />;
  return (
    <ul className="space-y-2">
      {products.map((p) => {
        const physical = p.stock.physical.reduce((sum, s) => sum + s.quantity, 0);
        return (
          <li key={p.id}>
            <Link href={`/data/products/${p.id}`} className="flex flex-wrap items-center gap-x-5 gap-y-1.5 rounded-xl border border-border bg-surface px-4 py-3 text-[13px] transition-colors hover:border-border-strong">
              <span className="min-w-[200px] flex-1 font-medium text-text">
                {p.name} {p.sku && <span className="ml-1 font-mono text-[12px] text-text-faint">{p.sku}</span>}
              </span>
              <span className="text-text-soft">{p.suppliers.length} fournisseur(s)</span>
              <span className="flex items-center gap-1.5 text-text-soft">
                Prix de vente <span className="num">{fmtMoney(p.sale_price)}</span>
                {p.sale_price !== null && <BasisBadge basis={p.sale_price_basis} />}
              </span>
              <span className="text-text-soft">{p.stock.physical.length ? `${fmtNumber(physical)} en stock` : "Stock physique inconnu"}</span>
            </Link>
          </li>
        );
      })}
    </ul>
  );
}

async function Stock({ canImport }: { canImport: boolean }) {
  const rows = await getStock().catch(() => [] as StockRow[]);
  return (
    <div className="space-y-8">
      {STOCK_KINDS.map(({ kind, label, hint }) => {
        const items = rows.filter((r) => r.kind === kind);
        return (
          <section key={kind}>
            <SectionLabel>{label}</SectionLabel>
            <p className="-mt-2 mb-3 text-[12px] text-text-faint">{hint}</p>
            {items.length === 0 ? (
              <EmptyState message="Aucune position." />
            ) : (
              <Card className="overflow-x-auto p-0">
                <table className="w-full min-w-[640px] text-[12.5px]">
                  <thead className="text-left text-text-faint">
                    <tr className="border-b border-border">
                      <th className="px-4 py-2.5 font-medium">Produit</th>
                      <th className="px-4 py-2.5 font-medium">Quantité</th>
                      <th className="px-4 py-2.5 font-medium">{kind === "supplier" ? "Fournisseur" : "Emplacement"}</th>
                      <th className="px-4 py-2.5 font-medium">Au</th>
                      <th className="px-4 py-2.5 font-medium">Source</th>
                    </tr>
                  </thead>
                  <tbody>
                    {items.map((r) => (
                      <tr key={r.id} className="border-b border-border last:border-0">
                        <td className="px-4 py-2.5"><Link href={`/data/products/${r.product_id}`} className="text-text hover:underline">{r.product_name}</Link></td>
                        <td className="px-4 py-2.5"><span className="flex items-center gap-1.5">{fmtNumber(r.quantity)} <BasisBadge basis={r.basis} /></span></td>
                        <td className="px-4 py-2.5">{kind === "supplier" && r.supplier_id ? <Link href={`/data/suppliers/${r.supplier_id}`} className="hover:underline">{r.supplier_name}</Link> : r.location ?? "—"}</td>
                        <td className="num px-4 py-2.5 text-text-faint">{fmtDate(r.as_of)}</td>
                        <td className="px-4 py-2.5 font-mono text-[11.5px] text-text-faint">{r.source}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </Card>
            )}
          </section>
        );
      })}
      {canImport && <StockImport />}
    </div>
  );
}
