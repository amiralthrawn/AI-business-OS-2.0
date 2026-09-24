import DocumentCreateForm from "@/components/objects/DocumentCreateForm";
import ObjectBreadcrumb from "@/components/objects/ObjectBreadcrumb";
import PageHeader from "@/components/ui/PageHeader";
import { getDocumentsMeta, getObjectContext } from "@/lib/api";
import type { DocumentKind, ObjectType } from "@/lib/types";

export const dynamic = "force-dynamic";

async function party(type: ObjectType, id: string | undefined) {
  if (!id) return null;
  try {
    const ctx = await getObjectContext(type, id);
    return { id, title: ctx.object.title };
  } catch {
    return null;
  }
}

// Reached from a context action ("Nouveau devis" on a customer, "Lancer une
// demande d'achat" on a product...), so the form arrives pre-filled.
export default async function NewDocumentPage({ searchParams }: { searchParams: Promise<Record<string, string | undefined>> }) {
  const sp = await searchParams;
  const meta = await getDocumentsMeta();
  const kind = (meta.kinds.some((k) => k.kind === sp.kind) ? sp.kind : "customer_quote") as DocumentKind;
  const [customer, supplier, product] = await Promise.all([party("customer", sp.customer_id), party("supplier", sp.supplier_id), party("product", sp.product_id)]);
  const domain = meta.kinds.find((k) => k.kind === kind)!.domain;

  return (
    <main className="space-y-8 p-8 md:p-12">
      <ObjectBreadcrumb
        section={domain === "sales" ? { label: "Ventes", href: "/business/sales?tab=deals" } : { label: "Achats", href: "/business/procurement?tab=requests" }}
        chain={[]}
      />
      <PageHeader title="Nouveau document" description="Chaque document est numéroté, relié à ses objets (client, fournisseur, produits) et à la suite de l'affaire." />
      <DocumentCreateForm kinds={meta.kinds} initialKind={kind} initialCustomer={customer} initialSupplier={supplier} initialProduct={product} />
    </main>
  );
}
