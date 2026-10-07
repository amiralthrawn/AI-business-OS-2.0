import Link from "next/link";
import Card from "@/components/ui/Card";
import { getComplianceRequests, getEmployees, getMe, getOwnership, getSkillsGap, getTreasury } from "@/lib/api";
import { can, fmtMoneyRange } from "@/lib/objects";
import { valueLabel } from "@/lib/labels";

// V2.1 "Vue dirigeant": the director-level signals, each shown only to a
// profile allowed to see it and each a link into its space. Home stays an
// aggregator -- every number comes from an existing endpoint.
export default async function HomeDirector() {
  const me = await getMe().catch(() => null);
  const p = me?.permissions;
  const [treasury, ownership, employees, gap, compliance] = await Promise.all([
    can(p, "view:treasury") ? getTreasury().catch(() => null) : null,
    can(p, "view:ownership") ? getOwnership().catch(() => null) : null,
    can(p, "view:people") ? getEmployees().catch(() => null) : null,
    can(p, "view:people") ? getSkillsGap().catch(() => null) : null,
    can(p, "view:compliance") ? getComplianceRequests().catch(() => null) : null,
  ]);

  const cards: { href: string; label: string; value: string; hint: string; alert?: boolean }[] = [];
  if (treasury) {
    const p90 = treasury.projection.at(-1);
    cards.push({ href: "/direction", label: "Trésorerie à 90 jours", value: p90 ? fmtMoneyRange(p90.low, p90.high) : "—", hint: treasury.cash_basis === "simulated" ? "données simulées" : "projection déterministe", alert: treasury.below_min_cash });
  }
  if (ownership?.valuation.estimated_min != null) {
    cards.push({ href: "/direction?tab=ownership", label: "Valeur estimée", value: fmtMoneyRange(ownership.valuation.estimated_min, ownership.valuation.estimated_max), hint: `estimation · confiance ${valueLabel("confidence", ownership.valuation.confidence)}` });
  }
  if (employees) {
    const withCost = employees.filter((e) => e.cost && e.cost.basis !== "unknown");
    const costLabel = withCost.length ? `≈ ${fmtMoneyRange(withCost.reduce((s, e) => s + e.cost!.total_min, 0), withCost.reduce((s, e) => s + e.cost!.total_max, 0))} / an` : `${employees.length} personnes`;
    cards.push({ href: "/people", label: "Équipe", value: costLabel, hint: `${employees.length} personne(s)${gap ? ` · ${gap.gaps.length} compétence(s) manquante(s)` : ""}`, alert: !!gap && gap.gaps.some((g) => g.priority === "high") });
  }
  if (compliance) {
    const overdue = compliance.filter((c) => c.overdue).length;
    const open = compliance.filter((c) => c.open).length;
    cards.push({ href: "/actions/compliance", label: "Conformité", value: `${open} ouverte(s)`, hint: overdue ? `${overdue} échéance(s) dépassée(s)` : "aucune échéance dépassée", alert: overdue > 0 });
  }
  if (cards.length === 0) return null;

  return (
    <section>
      <span className="mb-5 block text-[11.5px] font-bold tracking-wide text-text-faint uppercase">Vue dirigeant</span>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {cards.map((c) => (
          <Link key={c.href} href={c.href}>
            <Card className="h-full p-5 transition-colors hover:border-border-strong">
              <p className="text-[12.5px] text-text-soft">{c.label}</p>
              <p className={`mt-1.5 figure text-[20px] ${c.alert ? "text-danger" : "text-text"}`}>{c.value}</p>
              <p className="text-[11.5px] text-text-faint">{c.hint}</p>
            </Card>
          </Link>
        ))}
      </div>
    </section>
  );
}
