"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import ObjectPicker from "@/components/objects/ObjectPicker";
import Button from "@/components/ui/Button";
import Card from "@/components/ui/Card";
import Chip from "@/components/ui/Chip";
import { createDocument } from "@/lib/api";
import type { DocumentKind, KindMeta, NewLineInput } from "@/lib/types";

type Party = { id: string; title: string } | null;
type DraftLine = { key: number; product: Party; newProductName: string; newProductSku: string; quantity: string; unitPrice: string };

const field = "w-full rounded-xl border-[1.5px] border-border-strong px-4 py-2.5 text-[14px] outline-none focus:border-accent";
const CREATABLE: DocumentKind[] = ["customer_request", "customer_quote", "customer_order", "purchase_request", "supplier_quote", "purchase_order"];

// Create a commercial document: pick an existing customer/supplier/product or
// create one on the spot (the backend reuses an existing one with the same
// name/reference -- never a duplicate), then land on the new document's page.
export default function DocumentCreateForm({
  kinds,
  initialKind,
  initialCustomer,
  initialSupplier,
  initialProduct,
}: {
  kinds: KindMeta[];
  initialKind: DocumentKind;
  initialCustomer: Party;
  initialSupplier: Party;
  initialProduct: Party;
}) {
  const router = useRouter();
  const [kind, setKind] = useState<DocumentKind>(initialKind);
  const meta = kinds.find((k) => k.kind === kind)!;
  const [customer, setCustomer] = useState<Party>(initialCustomer);
  const [newCustomer, setNewCustomer] = useState("");
  const [supplier, setSupplier] = useState<Party>(initialSupplier);
  const [title, setTitle] = useState("");
  const [externalRef, setExternalRef] = useState("");
  const [lines, setLines] = useState<DraftLine[]>([{ key: 1, product: initialProduct, newProductName: "", newProductSku: "", quantity: "1", unitPrice: "" }]);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const needsSupplier = ["supplier_quote", "purchase_order"].includes(kind);
  const isSales = meta.domain === "sales";

  function updateLine(key: number, patch: Partial<DraftLine>) {
    setLines((ls) => ls.map((l) => (l.key === key ? { ...l, ...patch } : l)));
  }

  async function submit() {
    setSaving(true);
    setError(null);
    try {
      const payloadLines: NewLineInput[] = lines
        .filter((l) => l.product || l.newProductName.trim())
        .map((l) => ({
          ...(l.product ? { product_id: l.product.id } : { new_product: { name: l.newProductName.trim(), sku: l.newProductSku.trim() || undefined } }),
          quantity: Number(l.quantity.replace(",", ".")) || 1,
          ...(l.unitPrice ? { unit_price: Number(l.unitPrice.replace(",", ".")) } : {}),
        }));
      const doc = await createDocument({
        kind,
        ...(isSales ? (customer ? { customer_id: customer.id } : newCustomer.trim() ? { new_customer: { name: newCustomer.trim(), status: "prospect" } } : {}) : {}),
        ...(!isSales && supplier ? { supplier_id: supplier.id } : {}),
        title: title.trim() || undefined,
        external_reference: externalRef.trim() || undefined,
        lines: payloadLines,
      });
      router.push(`/documents/${doc.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Une erreur est survenue.");
      setSaving(false);
    }
  }

  return (
    <Card className="max-w-3xl space-y-7 p-8">
      <div>
        <label className="mb-2 block text-[13px] font-semibold text-text">Type de document</label>
        <div className="flex flex-wrap gap-2">
          {kinds.filter((k) => CREATABLE.includes(k.kind)).map((k) => (
            <Chip key={k.kind} label={k.label} selected={k.kind === kind} onClick={() => setKind(k.kind)} />
          ))}
        </div>
      </div>

      {isSales ? (
        <div>
          <label className="mb-2 block text-[13px] font-semibold text-text">Client</label>
          {customer ? (
            <div className="flex items-center justify-between rounded-xl border-[1.5px] border-accent bg-accent-soft px-4 py-2.5 text-[14px]">
              <span className="font-medium text-accent-strong">{customer.title}</span>
              <button type="button" onClick={() => setCustomer(null)} className="text-[12px] text-text-soft hover:text-text">Changer</button>
            </div>
          ) : (
            <div className="grid gap-3 md:grid-cols-2">
              <ObjectPicker types={["customer"]} placeholder="Client existant…" onPick={(c) => setCustomer({ id: c.id, title: c.title })} />
              <input className={field} placeholder="…ou nouveau client (prospect)" value={newCustomer} onChange={(e) => setNewCustomer(e.target.value)} />
            </div>
          )}
        </div>
      ) : (
        <div>
          <label className="mb-2 block text-[13px] font-semibold text-text">Fournisseur {needsSupplier ? "" : <span className="font-normal text-text-faint">(facultatif pour une demande d&rsquo;achat : vous consulterez ensuite plusieurs fournisseurs)</span>}</label>
          {supplier ? (
            <div className="flex items-center justify-between rounded-xl border-[1.5px] border-accent bg-accent-soft px-4 py-2.5 text-[14px]">
              <span className="font-medium text-accent-strong">{supplier.title}</span>
              <button type="button" onClick={() => setSupplier(null)} className="text-[12px] text-text-soft hover:text-text">Changer</button>
            </div>
          ) : (
            <ObjectPicker types={["supplier"]} placeholder="Fournisseur…" onPick={(s) => setSupplier({ id: s.id, title: s.title })} />
          )}
        </div>
      )}

      <div className="grid gap-3 md:grid-cols-2">
        <div>
          <label className="mb-2 block text-[13px] font-semibold text-text">Objet</label>
          <input className={field} placeholder="ex. Séminaire de printemps" value={title} onChange={(e) => setTitle(e.target.value)} />
        </div>
        <div>
          <label className="mb-2 block text-[13px] font-semibold text-text">Référence externe</label>
          <input className={field} placeholder={isSales ? "N° de demande / commande du client" : "N° du fournisseur"} value={externalRef} onChange={(e) => setExternalRef(e.target.value)} />
        </div>
      </div>

      <div>
        <label className="mb-2 block text-[13px] font-semibold text-text">Produits / prestations</label>
        <div className="space-y-3">
          {lines.map((line) => (
            <div key={line.key} className="grid items-start gap-2 md:grid-cols-[1fr_90px_120px_auto]">
              {line.product ? (
                <div className="flex items-center justify-between rounded-xl border border-border bg-surface-alt px-3 py-2.5 text-[13.5px]">
                  <span className="truncate">{line.product.title}</span>
                  <button type="button" onClick={() => updateLine(line.key, { product: null })} className="text-[12px] text-text-faint hover:text-text">×</button>
                </div>
              ) : (
                <div className="space-y-1.5">
                  <ObjectPicker types={["product"]} placeholder="Produit existant…" onPick={(p) => updateLine(line.key, { product: { id: p.id, title: p.title } })} />
                  <div className="flex gap-1.5">
                    <input className="flex-1 rounded-lg border border-border px-3 py-1.5 text-[12.5px] outline-none focus:border-accent" placeholder="…ou nouveau produit" value={line.newProductName} onChange={(e) => updateLine(line.key, { newProductName: e.target.value })} />
                    <input className="w-28 rounded-lg border border-border px-3 py-1.5 text-[12.5px] outline-none focus:border-accent" placeholder="Référence" value={line.newProductSku} onChange={(e) => updateLine(line.key, { newProductSku: e.target.value })} />
                  </div>
                </div>
              )}
              <input className={`${field} py-2`} placeholder="Qté" value={line.quantity} onChange={(e) => updateLine(line.key, { quantity: e.target.value })} />
              <input className={`${field} py-2`} placeholder={isSales ? "Prix (catalogue)" : "Prix (conditions)"} value={line.unitPrice} onChange={(e) => updateLine(line.key, { unitPrice: e.target.value })} />
              <button type="button" onClick={() => setLines((ls) => ls.filter((l) => l.key !== line.key))} className="px-2 py-2.5 text-[12px] text-text-faint hover:text-danger" aria-label="Retirer la ligne">Retirer</button>
            </div>
          ))}
        </div>
        <button type="button" onClick={() => setLines((ls) => [...ls, { key: Date.now(), product: null, newProductName: "", newProductSku: "", quantity: "1", unitPrice: "" }])} className="mt-3 text-[13px] font-medium text-accent-strong hover:underline">
          + Ajouter une ligne
        </button>
        <p className="mt-2 text-[11.5px] text-text-faint">Prix laissé vide : le prix catalogue (vente) ou les conditions du fournisseur (achat) sont repris, avec leur nature. Sans source, il reste « inconnu ».</p>
      </div>

      {error && <p className="text-[13px] text-danger">{error}</p>}
      <div className="flex gap-3">
        <Button onClick={submit} loading={saving}>Créer {meta.label.toLowerCase()}</Button>
        <Button variant="ghost" onClick={() => router.back()}>Annuler</Button>
      </div>
    </Card>
  );
}
