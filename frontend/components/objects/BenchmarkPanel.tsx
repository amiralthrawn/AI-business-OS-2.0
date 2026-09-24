"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import BasisBadge from "@/components/objects/BasisBadge";
import BenchmarkChart from "@/components/objects/BenchmarkChart";
import SectionLabel from "@/components/objects/SectionLabel";
import Badge from "@/components/ui/Badge";
import Button from "@/components/ui/Button";
import Card from "@/components/ui/Card";
import { createDraft, deriveDocument, getBenchmark } from "@/lib/api";
import { CONFIDENCE_LABEL, fmtMeasure } from "@/lib/objects";
import type { Benchmark, Measure, SupplierCandidate } from "@/lib/types";

const CRITERIA: { key: keyof SupplierCandidate; label: string }[] = [
  { key: "unit_price", label: "Prix unitaire" },
  { key: "order_quantity", label: "Quantité à commander" },
  { key: "total_cost", label: "Coût total" },
  { key: "lead_time_days", label: "Délai" },
  { key: "performance", label: "Performance livraison" },
  { key: "availability", label: "Disponibilité" },
  { key: "payment_terms", label: "Conditions de paiement" },
  { key: "origin_country", label: "Origine" },
];

function Cell({ m }: { m: Measure }) {
  return (
    <div>
      <div className="flex flex-wrap items-center gap-1.5">
        <span className="num text-text">{fmtMeasure(m)}</span>
        <BasisBadge basis={m.basis} confidence={m.confidence} />
      </div>
      {(m.text && (m.min !== null || m.value !== null)) || m.source ? (
        <p className="mt-0.5 text-[11px] text-text-faint">{[m.min !== null || m.value !== null ? m.text : null, m.source].filter(Boolean).join(" · ")}</p>
      ) : null}
    </div>
  );
}

// Supplier comparison with a recommended point. Acting on it stays one click
// away and always goes through the document chain (a supplier quote or a PO
// derived from the purchase request) or a draft email awaiting validation.
export default function BenchmarkPanel({
  initial,
  purchaseRequestId,
  canAct,
}: {
  initial: Benchmark;
  purchaseRequestId?: string;
  canAct: boolean;
}) {
  const router = useRouter();
  const [bench, setBench] = useState(initial);
  const [quantity, setQuantity] = useState(String(initial.quantity));
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function recompute() {
    const q = Number(quantity.replace(",", "."));
    if (!q || q <= 0) return;
    setBusy("qty");
    try {
      setBench(await getBenchmark(bench.product_id, q, purchaseRequestId));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Erreur");
    } finally {
      setBusy(null);
    }
  }

  async function act(key: string, fn: () => Promise<string>) {
    setBusy(key);
    setError(null);
    try {
      router.push(await fn());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Une erreur est survenue.");
      setBusy(null);
    }
  }

  return (
    <section>
      <SectionLabel id="benchmark">Comparaison fournisseurs · {bench.product_name}</SectionLabel>
      <Card className="p-6">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-2 text-[13px] text-text-soft">
            Quantité
            <input value={quantity} onChange={(e) => setQuantity(e.target.value)} className="w-20 rounded-lg border-[1.5px] border-border-strong px-2 py-1 text-[13px] outline-none focus:border-accent" />
            <Button variant="ghost" loading={busy === "qty"} onClick={recompute}>Recalculer</Button>
          </div>
          <span className="text-[12px] text-text-faint">
            Pondération : coût {bench.weights.total_cost * 100} % · délai {bench.weights.lead_time * 100} % · performance {bench.weights.performance * 100} % · disponibilité {bench.weights.availability * 100} %
          </span>
        </div>
        <div className="mt-5">
          <BenchmarkChart candidates={bench.candidates} />
        </div>
        <div className="mt-4 rounded-xl bg-surface-alt px-4 py-3 text-[13px] text-text-soft">
          <span className="font-semibold text-text">Recommandation ({CONFIDENCE_LABEL[bench.recommendation_confidence]}) : </span>
          {bench.explanation.join(" ")}
        </div>
      </Card>

      <Card className="mt-4 overflow-x-auto p-0">
        <table className="w-full min-w-[760px] text-[12.5px]">
          <thead>
            <tr className="border-b border-border text-left">
              <th className="px-4 py-3 font-medium text-text-faint">Critère</th>
              {bench.candidates.map((c) => (
                <th key={c.supplier_id} className="px-4 py-3 align-top">
                  <Link href={`/data/suppliers/${c.supplier_id}`} className="text-[13px] font-semibold text-text hover:underline">{c.supplier_name}</Link>
                  <div className="mt-1 flex flex-wrap gap-1.5">
                    {c.recommended && <Badge label="Recommandé" tone="accent" />}
                    {c.score !== null && <Badge label={`${Math.round(c.score)}/100`} tone="neutral" />}
                    {c.open_risks > 0 && <Badge label={`${c.open_risks} risque(s)`} tone="danger" />}
                  </div>
                  {c.quote_number && c.quote_id && (
                    <Link href={`/documents/${c.quote_id}`} className="mt-1 block text-[11.5px] font-normal text-text-faint hover:underline">Devis {c.quote_number}</Link>
                  )}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {CRITERIA.map(({ key, label }) => (
              <tr key={key} className="border-b border-border">
                <td className="px-4 py-2.5 text-text-soft">{label}</td>
                {bench.candidates.map((c) => (
                  <td key={c.supplier_id} className="px-4 py-2.5 align-top"><Cell m={c[key] as Measure} /></td>
                ))}
              </tr>
            ))}
            <tr className="border-b border-border">
              <td className="px-4 py-2.5 text-text-soft">Normes / environnement</td>
              {bench.candidates.map((c) => (
                <td key={c.supplier_id} className="px-4 py-2.5">{c.certifications.length ? c.certifications.join(", ") : <span className="text-text-faint">Non renseigné</span>}</td>
              ))}
            </tr>
            <tr>
              <td className="px-4 py-3 text-text-soft">Agir</td>
              {bench.candidates.map((c) => (
                <td key={c.supplier_id} className="space-y-1.5 px-4 py-3 align-top">
                  {purchaseRequestId && !c.quote_id && (
                    <Button variant="ghost" className="w-full" disabled={!canAct || busy !== null} loading={busy === `rfq-${c.supplier_id}`}
                      onClick={() => act(`rfq-${c.supplier_id}`, async () => {
                        const quote = await deriveDocument(purchaseRequestId, "supplier_quote", c.supplier_id);
                        const draft = await createDraft({ purpose: "rfq_price", object_type: "commercial_document", object_id: quote.id });
                        return `/communications?tab=drafts&message=${draft.id}`;
                      })}>
                      Demander un devis
                    </Button>
                  )}
                  {purchaseRequestId && (
                    <Button variant={c.recommended ? "primary" : "ghost"} className="w-full" disabled={!canAct || busy !== null} loading={busy === `po-${c.supplier_id}`}
                      onClick={() => act(`po-${c.supplier_id}`, async () => {
                        const po = await deriveDocument(c.quote_id ?? purchaseRequestId, "purchase_order", c.quote_id ? undefined : c.supplier_id);
                        return `/documents/${po.id}`;
                      })}>
                      Commander
                    </Button>
                  )}
                  {!purchaseRequestId && (
                    <Link href={`/documents/new?kind=purchase_request&product_id=${bench.product_id}`} className="block text-center text-[12px] text-accent-strong hover:underline">
                      Lancer une demande d&rsquo;achat
                    </Link>
                  )}
                </td>
              ))}
            </tr>
          </tbody>
        </table>
      </Card>
      {!canAct && purchaseRequestId && <p className="mt-2 text-[12px] text-text-faint">Votre rôle ne permet pas de consulter ou commander des fournisseurs.</p>}
      {error && <p className="mt-2 text-[12.5px] text-danger">{error}</p>}
    </section>
  );
}
