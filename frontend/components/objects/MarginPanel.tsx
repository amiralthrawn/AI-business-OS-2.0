import Link from "next/link";
import Badge from "@/components/ui/Badge";
import Card from "@/components/ui/Card";
import BasisBadge from "@/components/objects/BasisBadge";
import SectionLabel from "@/components/objects/SectionLabel";
import { COST_BASIS_LABEL, COST_KIND_LABEL, fmtMoney, fmtMoneyRange, fmtPctRange } from "@/lib/objects";
import type { DocumentMargin, MarginView } from "@/lib/types";

function View({ title, view, hint }: { title: string; view: MarginView; hint: string }) {
  const basis = COST_BASIS_LABEL[view.cost_basis];
  return (
    <Card className="p-6">
      <div className="flex items-center justify-between gap-3">
        <p className="text-[13px] text-text-soft">{title}</p>
        <Badge label={basis.label} tone={basis.tone} />
      </div>
      <p className="mt-2 figure text-[24px]">{fmtMoneyRange(view.margin_min, view.margin_max)}</p>
      <p className="text-[12.5px] text-text-faint">
        <span className="num">{fmtPctRange(view.margin_pct_min, view.margin_pct_max)}</span> · coûts <span className="num">{fmtMoneyRange(view.cost_min, view.cost_max)}</span> · CA <span className="num">{fmtMoney(view.revenue)}</span>
      </p>
      <p className="mt-2 text-[11.5px] text-text-faint">{hint}</p>
    </Card>
  );
}

// Planned vs current margin of a sales document, walking its whole deal:
// every cost carries its nature, ranges stay ranges, and the gap is explained.
export default function MarginPanel({ margin }: { margin: DocumentMargin }) {
  return (
    <section>
      <SectionLabel>Marge</SectionLabel>
      <div className="grid gap-4 md:grid-cols-2">
        <View title="Prévue au chiffrage" view={margin.planned} hint="Coûts connus avant engagement : devis fournisseur, catalogue ou coût de référence." />
        <View title="Actuelle" view={margin.current} hint="Meilleure source disponible : facture validée > commande fournisseur > devis > catalogue." />
      </div>

      {margin.variances.length > 0 && (
        <Card className="mt-4 p-5">
          <p className="mb-2 text-[12.5px] font-semibold text-text-soft">Pourquoi l&rsquo;écart</p>
          <ul className="space-y-1.5 text-[13px]">
            {margin.variances.map((v, i) => (
              <li key={i} className="flex items-baseline gap-3">
                <span className={`w-[90px] shrink-0 text-right font-mono font-semibold ${v.delta > 0 ? "text-danger" : "text-success"}`}>
                  {v.delta > 0 ? "−" : "+"}
                  {fmtMoney(Math.abs(v.delta))}
                </span>
                <span className="text-text-soft">{v.explanation}</span>
              </li>
            ))}
          </ul>
        </Card>
      )}

      <Card className="mt-4 overflow-x-auto p-0">
        <table className="w-full min-w-[640px] text-[12.5px]">
          <thead className="text-left text-text-faint">
            <tr className="border-b border-border">
              <th className="px-4 py-2.5 font-medium">Ligne</th>
              <th className="px-4 py-2.5 font-medium">Coût prévu</th>
              <th className="px-4 py-2.5 font-medium">Coût actuel</th>
              <th className="px-4 py-2.5 text-right font-medium">Marge ligne</th>
            </tr>
          </thead>
          <tbody>
            {margin.lines.map((l) => (
              <tr key={l.line_id} className="border-b border-border last:border-0">
                <td className="px-4 py-2.5 text-text">
                  {l.product_id ? <Link href={`/data/products/${l.product_id}`} className="hover:underline">{l.product_name}</Link> : l.product_name} × {l.quantity}
                </td>
                <td className="px-4 py-2.5">
                  <div className="flex flex-wrap items-center gap-1.5">
                    <span className="num">{l.planned.unit_cost !== null ? fmtMoney(l.planned.unit_cost, true) : "—"}</span>
                    <BasisBadge basis={l.planned.basis} />
                  </div>
                  <p className="text-[11px] text-text-faint">{l.planned.source_label}</p>
                </td>
                <td className="px-4 py-2.5">
                  <div className="flex flex-wrap items-center gap-1.5">
                    <span className="num">{l.current.unit_cost !== null ? fmtMoney(l.current.unit_cost, true) : "—"}</span>
                    <BasisBadge basis={l.current.basis} />
                  </div>
                  <p className="text-[11px] text-text-faint">
                    {l.current.document_id ? <Link href={`/documents/${l.current.document_id}`} className="hover:underline">{l.current.source_label} · {l.current.document_number}</Link> : l.current.source_label}
                  </p>
                </td>
                <td className="px-4 py-2.5 text-right font-mono font-semibold">{l.margin !== null ? fmtMoney(l.margin) : "—"}</td>
              </tr>
            ))}
            {margin.cost_items.map((c) => (
              <tr key={c.kind} className="border-b border-border last:border-0">
                <td className="px-4 py-2.5 text-text-soft" title={c.labels.join(" · ")}>{COST_KIND_LABEL[c.kind] ?? c.kind}</td>
                <td className="px-4 py-2.5">
                  {c.planned ? (
                    <span className="num flex items-center gap-1.5">{fmtMoneyRange(c.planned.min, c.planned.max)} <BasisBadge basis={c.planned.basis} /></span>
                  ) : (
                    <span className="text-text-faint">non prévu</span>
                  )}
                </td>
                <td className="px-4 py-2.5">
                  {c.current ? <span className="num flex items-center gap-1.5">{fmtMoneyRange(c.current.min, c.current.max)} <BasisBadge basis={c.current.basis} /></span> : "—"}
                </td>
                <td />
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
      {(margin.missing.length > 0 || margin.allocation_note) && (
        <div className="mt-3 space-y-1 text-[12px] text-text-faint">
          {margin.missing.map((m) => <p key={m}>⚠ {m}</p>)}
          {margin.allocation_note && <p>{margin.allocation_note}</p>}
        </div>
      )}
    </section>
  );
}
