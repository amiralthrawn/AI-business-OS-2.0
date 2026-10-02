"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import BasisBadge from "@/components/objects/BasisBadge";
import ObjectPicker from "@/components/objects/ObjectPicker";
import SectionLabel from "@/components/objects/SectionLabel";
import Button from "@/components/ui/Button";
import Card from "@/components/ui/Card";
import { addCostItem, addDocumentLine, removeDocumentLine, updateDocumentLine } from "@/lib/api";
import { BASIS_LABEL, COST_KIND_LABEL, fmtDaysRange, fmtMoney, fmtMoneyRange } from "@/lib/objects";
import type { DocumentDetail, ValueBasis } from "@/lib/types";

const input = "rounded-lg border-[1.5px] border-border-strong px-2 py-1 text-[13px] outline-none focus:border-accent";

// Lines and extra costs of a document. Editable only while the document is
// (the backend enforces it too); every price shows its nature.
export default function DocumentLines({ doc, canEdit }: { doc: DocumentDetail; canEdit: boolean }) {
  const router = useRouter();
  const editable = doc.editable && canEdit;
  const procurement = doc.domain === "procurement";
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [draftEdits, setDraftEdits] = useState<Record<string, { quantity?: string; unit_price?: string }>>({});
  const [newProductName, setNewProductName] = useState("");
  const [cost, setCost] = useState({ kind: "transport", min: "", max: "", basis: "estimated" as ValueBasis, label: "" });

  async function run(fn: () => Promise<unknown>) {
    setBusy(true);
    setError(null);
    try {
      await fn();
      router.refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Une erreur est survenue.");
    } finally {
      setBusy(false);
    }
  }

  function saveLine(lineId: string) {
    const edit = draftEdits[lineId];
    if (!edit) return;
    const changes: Record<string, number> = {};
    if (edit.quantity !== undefined) changes.quantity = Number(edit.quantity.replace(",", "."));
    if (edit.unit_price !== undefined && edit.unit_price !== "") changes.unit_price = Number(edit.unit_price.replace(",", "."));
    run(async () => {
      await updateDocumentLine(doc.id, lineId, changes);
      setDraftEdits((d) => ({ ...d, [lineId]: {} }));
    });
  }

  return (
    <section className="space-y-4">
      <SectionLabel>Lignes</SectionLabel>
      <Card className="overflow-x-auto p-0">
        <table className="w-full min-w-[680px] text-[12.5px]">
          <thead className="text-left text-text-faint">
            <tr className="border-b border-border">
              <th className="px-4 py-2.5 font-medium">Produit</th>
              <th className="px-4 py-2.5 font-medium">Quantité</th>
              <th className="px-4 py-2.5 font-medium">{procurement ? "Prix d'achat unitaire" : "Prix de vente unitaire"}</th>
              {procurement ? <th className="px-4 py-2.5 font-medium">Délai · MOQ/SPQ</th> : <th className="px-4 py-2.5 font-medium">Coût prévu</th>}
              <th className="px-4 py-2.5 text-right font-medium">Total</th>
              {editable && <th />}
            </tr>
          </thead>
          <tbody>
            {doc.lines.map((line) => {
              const edit = draftEdits[line.id] ?? {};
              return (
                <tr key={line.id} className="border-b border-border last:border-0">
                  <td className="px-4 py-2.5 text-text">
                    {line.product_id ? <Link href={`/data/products/${line.product_id}`} className="hover:underline">{line.product_name}</Link> : line.description}
                    {line.product_sku && <span className="ml-1.5 text-text-faint">{line.product_sku}</span>}
                  </td>
                  <td className="px-4 py-2.5">
                    {editable ? (
                      <input className={`${input} w-20`} value={edit.quantity ?? String(line.quantity)} onChange={(e) => setDraftEdits((d) => ({ ...d, [line.id]: { ...edit, quantity: e.target.value } }))} />
                    ) : (
                      <span className="num">{`${line.quantity} ${line.unit ?? ""}`}</span>
                    )}
                  </td>
                  <td className="px-4 py-2.5">
                    <div className="flex flex-wrap items-center gap-1.5">
                      {editable ? (
                        <input className={`${input} w-24`} placeholder="—" value={edit.unit_price ?? (line.unit_price !== null ? String(line.unit_price) : "")} onChange={(e) => setDraftEdits((d) => ({ ...d, [line.id]: { ...edit, unit_price: e.target.value } }))} />
                      ) : (
                        <span className="num">{line.unit_price !== null ? fmtMoney(line.unit_price, true) : "Inconnu"}</span>
                      )}
                      <BasisBadge basis={line.price_basis} />
                    </div>
                  </td>
                  {procurement ? (
                    <td className="px-4 py-2.5">
                      <span className="num flex flex-wrap items-center gap-1.5">
                        {fmtDaysRange(line.lead_time_min_days, line.lead_time_max_days)}
                        {line.lead_time_min_days !== null && <BasisBadge basis={line.lead_time_basis} />}
                      </span>
                      {(line.moq || line.spq) && <p className="text-[11px] text-text-faint">MOQ {line.moq ?? "—"} · SPQ {line.spq ?? "—"}</p>}
                    </td>
                  ) : (
                    <td className="px-4 py-2.5">
                      {line.planned_unit_cost !== null && line.planned_cost_basis ? (
                        <span className="num flex flex-wrap items-center gap-1.5" title={line.planned_cost_source ?? undefined}>
                          {fmtMoney(line.planned_unit_cost, true)} <BasisBadge basis={line.planned_cost_basis} />
                        </span>
                      ) : (
                        <span className="text-text-faint">Inconnu</span>
                      )}
                    </td>
                  )}
                  <td className="px-4 py-2.5 text-right font-mono font-semibold">{line.total !== null ? fmtMoney(line.total) : "—"}</td>
                  {editable && (
                    <td className="whitespace-nowrap px-3 py-2.5 text-right">
                      {(edit.quantity !== undefined || edit.unit_price !== undefined) && (
                        <button type="button" disabled={busy} onClick={() => saveLine(line.id)} className="mr-2 text-[12px] font-semibold text-accent-strong hover:underline">Enregistrer</button>
                      )}
                      <button type="button" disabled={busy} onClick={() => run(() => removeDocumentLine(doc.id, line.id))} className="text-[12px] text-text-faint hover:text-danger">Retirer</button>
                    </td>
                  )}
                </tr>
              );
            })}
            {doc.lines.length === 0 && (
              <tr><td colSpan={6} className="px-4 py-4 text-center text-text-faint">Aucune ligne.</td></tr>
            )}
          </tbody>
        </table>
      </Card>

      {editable && (
        <div className="grid gap-3 md:grid-cols-2">
          <div>
            <p className="mb-1.5 text-[12px] font-medium text-text-soft">Ajouter un produit existant</p>
            <ObjectPicker types={["product"]} placeholder="Nom ou référence…" onPick={(p) => run(() => addDocumentLine(doc.id, { product_id: p.id, quantity: 1 }))} />
          </div>
          <div>
            <p className="mb-1.5 text-[12px] font-medium text-text-soft">…ou créer un produit</p>
            <div className="flex gap-2">
              <input className={`${input} flex-1 py-2`} placeholder="Nom du nouveau produit" value={newProductName} onChange={(e) => setNewProductName(e.target.value)} />
              <Button variant="ghost" disabled={!newProductName.trim() || busy} onClick={() => run(async () => { await addDocumentLine(doc.id, { new_product: { name: newProductName.trim() }, quantity: 1 }); setNewProductName(""); })}>
                Ajouter
              </Button>
            </div>
            <p className="mt-1 text-[11px] text-text-faint">Si ce nom ou cette référence existe déjà, le produit existant est réutilisé.</p>
          </div>
        </div>
      )}

      {/* Transport, customs... are costs of goods flows, not of a credit note. */}
      {(doc.cost_items.length > 0 || (canEdit && doc.kind !== "customer_credit_note" && doc.kind !== "supplier_credit_note")) && (
        <div>
          <p className="mb-2 text-[12.5px] font-semibold text-text-soft">Coûts annexes</p>
          {doc.cost_items.length > 0 && (
            <ul className="mb-3 space-y-1.5">
              {doc.cost_items.map((c) => (
                <li key={c.id} className="flex flex-wrap items-center gap-2 rounded-xl border border-border bg-surface px-4 py-2.5 text-[13px]">
                  <span className="text-text">{COST_KIND_LABEL[c.kind] ?? c.kind}</span>
                  {c.label && <span className="text-text-faint">{c.label}</span>}
                  <span className="ml-auto font-mono font-semibold">{fmtMoneyRange(c.amount_min, c.amount_max)}</span>
                  <BasisBadge basis={c.basis} confidence={c.confidence} />
                  {c.reference && <span className="text-[11.5px] text-text-faint">réf. {c.reference}</span>}
                </li>
              ))}
            </ul>
          )}
          {canEdit && (
            <div className="flex flex-wrap items-end gap-2 text-[12.5px]">
              <select className={input} value={cost.kind} onChange={(e) => setCost({ ...cost, kind: e.target.value })}>
                {Object.entries(COST_KIND_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
              </select>
              <input className={`${input} w-24`} placeholder="Min €" value={cost.min} onChange={(e) => setCost({ ...cost, min: e.target.value })} />
              <input className={`${input} w-24`} placeholder="Max € (option.)" value={cost.max} onChange={(e) => setCost({ ...cost, max: e.target.value })} />
              <select className={input} value={cost.basis} onChange={(e) => setCost({ ...cost, basis: e.target.value as ValueBasis })}>
                {(["estimated", "declared", "observed"] as ValueBasis[]).map((b) => <option key={b} value={b}>{BASIS_LABEL[b]}</option>)}
              </select>
              <input className={`${input} w-40`} placeholder="Libellé / transporteur" value={cost.label} onChange={(e) => setCost({ ...cost, label: e.target.value })} />
              <Button variant="ghost" disabled={!cost.min || busy} onClick={() => run(async () => {
                await addCostItem(doc.id, { kind: cost.kind, amount_min: Number(cost.min.replace(",", ".")), amount_max: cost.max ? Number(cost.max.replace(",", ".")) : undefined, basis: cost.basis, label: cost.label || undefined });
                setCost({ ...cost, min: "", max: "", label: "" });
              })}>
                Ajouter le coût
              </Button>
              <p className="w-full text-[11px] text-text-faint">Un coût « Réel » doit être un montant exact (facturé) ; une estimation peut être une fourchette.</p>
            </div>
          )}
        </div>
      )}
      {error && <p className="text-[12.5px] text-danger">{error}</p>}
    </section>
  );
}
