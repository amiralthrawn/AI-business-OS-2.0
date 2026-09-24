import Link from "next/link";
import SectionLabel from "@/components/objects/SectionLabel";
import Badge from "@/components/ui/Badge";
import Card from "@/components/ui/Card";
import EmptyState from "@/components/ui/EmptyState";
import { COST_BASIS_LABEL, fmtMoneyRange, fmtPctRange } from "@/lib/objects";
import type { OrderMarginRow } from "@/lib/types";

// Finance's per-order view (V2): planned vs current margin of each customer
// order, from the same engine as the order page. "Marge réelle" only when
// every cost is observed; otherwise the badge says what it is.
export default function OrderMargins({ rows }: { rows: OrderMarginRow[] }) {
  return (
    <section>
      <SectionLabel>Marge par commande client</SectionLabel>
      {rows.length === 0 ? (
        <EmptyState message="Aucune commande client pour l'instant." hint="Les marges par commande apparaissent dès qu'une commande est saisie dans Ventes." />
      ) : (
        <Card className="overflow-x-auto p-0">
          <table className="w-full min-w-[720px] text-[12.5px]">
            <thead className="text-left text-text-faint">
              <tr className="border-b border-border">
                <th className="px-4 py-2.5 font-medium">Commande</th>
                <th className="px-4 py-2.5 font-medium">Client</th>
                <th className="px-4 py-2.5 font-medium">Marge prévue</th>
                <th className="px-4 py-2.5 font-medium">Marge actuelle</th>
                <th className="px-4 py-2.5 font-medium">Nature</th>
              </tr>
            </thead>
            <tbody>
              {rows.map(({ document, planned, current }) => {
                const basis = COST_BASIS_LABEL[current.cost_basis];
                const worse = current.margin_max < planned.margin_min;
                return (
                  <tr key={document.id} className="border-b border-border last:border-0">
                    <td className="px-4 py-2.5"><Link href={`/documents/${document.id}`} className="font-mono font-semibold text-text hover:underline">{document.number}</Link></td>
                    <td className="px-4 py-2.5">{document.party ? <Link href={document.party.href} className="hover:underline">{document.party.name}</Link> : "—"}</td>
                    <td className="num px-4 py-2.5">{fmtMoneyRange(planned.margin_min, planned.margin_max)} <span className="text-text-faint">({fmtPctRange(planned.margin_pct_min, planned.margin_pct_max)})</span></td>
                    <td className={`num px-4 py-2.5 font-semibold ${worse ? "text-danger" : "text-text"}`}>
                      {fmtMoneyRange(current.margin_min, current.margin_max)} <span className="font-normal text-text-faint">({fmtPctRange(current.margin_pct_min, current.margin_pct_max)})</span>
                    </td>
                    <td className="px-4 py-2.5"><Badge label={basis.label} tone={basis.tone} /></td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </Card>
      )}
      <p className="mt-2 text-[12px] text-text-faint">
        Écritures comptables détaillées : <Link href="/data/transactions" className="text-accent-strong hover:underline">journal des transactions</Link> — chaque écriture issue d&rsquo;un document renvoie vers lui.
      </p>
    </section>
  );
}
