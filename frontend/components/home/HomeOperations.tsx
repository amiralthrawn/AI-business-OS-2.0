import Link from "next/link";
import Card from "@/components/ui/Card";
import { getFollowUps, getTasks, listDocuments } from "@/lib/api";
import { fmtMoney } from "@/lib/objects";

// V2: the day-to-day operations waiting on someone, each a link into the
// right workspace tab -- the Command Center points to the objects, it does
// not duplicate them.
export default async function HomeOperations() {
  const [deals, purchaseRequests, followUps, tasks] = await Promise.all([
    listDocuments({ kind: ["customer_request"], open_only: true }).catch(() => []),
    listDocuments({ kind: ["purchase_request"], open_only: true }).catch(() => []),
    getFollowUps().catch(() => null),
    getTasks().catch(() => []),
  ]);
  const overdue = followUps?.items.filter((i) => i.overdue_days > 0).length ?? 0;
  const emailsToValidate = tasks.filter((t) => t.status === "pending_validation" && t.pending_action === "send_email").length;
  const pipeline = deals.reduce((sum, d) => sum + (d.total ?? 0), 0);

  const cards = [
    { href: "/business/sales?tab=deals", label: "Affaires en cours", value: String(deals.length), hint: pipeline ? `${fmtMoney(pipeline)} chiffrés` : "Aucune chiffrée" },
    { href: "/business/sales?tab=followups", label: "Relances en retard", value: String(overdue), hint: `${followUps?.items.length ?? 0} à surveiller`, alert: overdue > 0 },
    { href: "/business/procurement?tab=requests", label: "Demandes d'achat ouvertes", value: String(purchaseRequests.length), hint: "Comparaison fournisseurs" },
    { href: "/actions/tasks", label: "Emails à valider", value: String(emailsToValidate), hint: "Rien ne part sans validation", alert: emailsToValidate > 0 },
  ];

  return (
    <section>
      <span className="mb-5 block text-[11.5px] font-bold tracking-wide text-text-faint uppercase">Opérations en cours</span>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {cards.map((c) => (
          <Link key={c.href} href={c.href}>
            <Card className="h-full p-5 transition-colors hover:border-border-strong">
              <p className="text-[12.5px] text-text-soft">{c.label}</p>
              <p className={`mt-1.5 figure text-[24px] ${c.alert ? "text-danger" : "text-text"}`}>{c.value}</p>
              <p className="text-[11.5px] text-text-faint">{c.hint}</p>
            </Card>
          </Link>
        ))}
      </div>
    </section>
  );
}
