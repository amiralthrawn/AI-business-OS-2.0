import Link from "next/link";
import { AccountForm, CashMonitor, FinanceSettingsForm } from "@/components/direction/DirectionActions";
import BasisBadge from "@/components/objects/BasisBadge";
import SectionLabel from "@/components/objects/SectionLabel";
import WorkspaceTabs from "@/components/objects/WorkspaceTabs";
import Badge from "@/components/ui/Badge";
import Card from "@/components/ui/Card";
import Donut from "@/components/ui/Donut";
import RangeBars from "@/components/ui/RangeBars";
import EmptyState from "@/components/ui/EmptyState";
import ErrorBanner from "@/components/ui/ErrorBanner";
import PageHeader from "@/components/ui/PageHeader";
import { getMe, getOwnership, getTreasury } from "@/lib/api";
import { CONFIDENCE_LABEL, can, fmtDate, fmtMoney, fmtMoneyRange } from "@/lib/objects";
import type { CashFlowItem, Confidence, ProjectionPoint, ValueBasis } from "@/lib/types";

export const dynamic = "force-dynamic";

const FLOW_STATUS: Record<string, { label: string; tone: "success" | "accent" | "warning" }> = {
  actual: { label: "Réel", tone: "success" },
  planned: { label: "Planifié", tone: "accent" },
  declared: { label: "Facturé", tone: "accent" },
  estimated: { label: "Estimé", tone: "warning" },
};

// The cards carry the figures; the bars compare the ranges on one scale
// (today is a single real point, each horizon a low–high range, never a midpoint).
function Projection({ points, now, minCash }: { points: ProjectionPoint[]; now?: number; minCash?: number | null }) {
  const bars = [
    ...(now !== undefined ? [{ label: "Aujourd’hui", low: now, high: now, display: fmtMoney(now) }] : []),
    ...points.map((p) => ({
      label: `Dans ${p.horizon_days} jours`,
      low: p.low,
      high: p.high,
      display: fmtMoneyRange(p.low, p.high),
      note: "bas : sans les encaissements estimés · haut : avec",
    })),
  ];
  return (
    <div className="space-y-4">
      {bars.length > 1 && (
        <Card className="p-5">
          <RangeBars bars={bars} reference={minCash} referenceLabel={minCash != null ? `Seuil minimum déclaré : ${fmtMoney(minCash)}` : undefined} />
        </Card>
      )}
      <div className="grid gap-4 sm:grid-cols-3">
        {points.map((p) => (
          <Card key={p.horizon_days} className="p-5">
            <p className="text-[12.5px] text-text-soft">Dans {p.horizon_days} jours</p>
            <p className="mt-1 figure text-[20px]">{fmtMoneyRange(p.low, p.high)}</p>
            <p className="text-[11.5px] text-text-faint">bas : sans les encaissements estimés</p>
          </Card>
        ))}
      </div>
    </div>
  );
}

function Flows({ flows }: { flows: CashFlowItem[] }) {
  if (flows.length === 0) return <EmptyState message="Aucun flux à venir." />;
  return (
    <ul className="space-y-1.5">
      {flows.map((f, i) => (
        <li key={i} className="flex flex-wrap items-center gap-3 rounded-xl border border-border bg-surface px-4 py-2.5 text-[13px]">
          <span className="num w-[92px] text-[12px] text-text-faint">{fmtDate(f.date)}</span>
          <span className="flex-1 text-text">
            {f.document_id ? (
              <Link href={`/documents/${f.document_id}`} className="hover:underline">
                {f.label}
              </Link>
            ) : (
              f.label
            )}
          </span>
          <Badge label={FLOW_STATUS[f.status]?.label ?? f.status} tone={FLOW_STATUS[f.status]?.tone ?? "neutral"} />
          <span className={`w-[110px] text-right font-mono font-semibold ${f.direction === "in" ? "text-success" : "text-text"}`}>
            {f.direction === "in" ? "+" : "−"}
            {fmtMoney(f.amount)}
          </span>
        </li>
      ))}
    </ul>
  );
}

// Direction (V2.1, brain/director_finance.md): treasury, accounts, ownership
// and an estimated value -- deterministic, labelled, and director-only by
// default (view:treasury / view:ownership). Not a bank.
export default async function DirectionPage({ searchParams }: { searchParams: Promise<{ tab?: string; account?: string }> }) {
  const sp = await searchParams;
  const me = await getMe().catch(() => null);
  const tabs = [
    can(me?.permissions, "view:treasury") && {
      key: "treasury",
      label: "Trésorerie",
      href: "/direction",
    },
    can(me?.permissions, "view:treasury") && {
      key: "accounts",
      label: "Comptes",
      href: "/direction?tab=accounts",
    },
    can(me?.permissions, "view:ownership") && {
      key: "ownership",
      label: "Capital & valorisation",
      href: "/direction?tab=ownership",
    },
  ].filter(Boolean) as { key: string; label: string; href: string }[];
  const active = tabs.find((t) => t.key === sp.tab)?.key ?? tabs[0]?.key;
  const canWrite = can(me?.permissions, "write:treasury");

  return (
    <main className="space-y-8 p-8 md:p-12">
      <PageHeader title="Direction" description="Trésorerie, comptes, capital et valeur estimée de l'entreprise — accès réservé." />
      {tabs.length === 0 ? (
        <ErrorBanner message="Votre profil n'a pas accès à cet espace." />
      ) : (
        <>
          <WorkspaceTabs tabs={tabs} active={active!} />
          {active === "treasury" && <Treasury canWrite={canWrite} />}
          {active === "accounts" && <Accounts canWrite={canWrite} selected={sp.account} />}
          {active === "ownership" && <Ownership canWrite={canWrite} />}
        </>
      )}
    </main>
  );
}

async function Treasury({ canWrite }: { canWrite: boolean }) {
  const t = await getTreasury().catch(() => null);
  if (!t) return <ErrorBanner message="Trésorerie indisponible." />;
  return (
    <div className="space-y-8">
      <section className="grid gap-4 sm:grid-cols-3">
        <Card className="p-5">
          <p className="text-[12.5px] text-text-soft">Trésorerie actuelle</p>
          <p className="mt-1 flex items-center gap-2 figure text-[24px]">
            {fmtMoney(t.cash_now)} <BasisBadge basis={t.cash_basis as ValueBasis} />
          </p>
        </Card>
        <Card className="p-5">
          <p className="text-[12.5px] text-text-soft">Dette restante</p>
          <p className="mt-1 figure text-[24px]">{fmtMoney(t.debt_outstanding)}</p>
        </Card>
        <Card className={`p-5 ${t.below_min_cash ? "border-danger" : ""}`}>
          <p className="text-[12.5px] text-text-soft">Seuil minimum déclaré</p>
          <p className="mt-1 figure text-[24px]">{t.min_cash !== null ? fmtMoney(t.min_cash) : "—"}</p>
          {t.below_min_cash && <p className="text-[12px] text-danger">La projection basse passe sous le seuil.</p>}
        </Card>
      </section>
      <section>
        <SectionLabel>Projection</SectionLabel>
        <Projection points={t.projection} now={t.cash_now} minCash={t.min_cash} />
        <p className="mt-2 text-[12px] text-text-faint">{t.method} Calcul déterministe, sans modèle de langage.</p>
        {canWrite && (
          <div className="mt-3">
            <CashMonitor />
          </div>
        )}
      </section>
      <section>
        <SectionLabel>Entrées et sorties à venir</SectionLabel>
        <Flows flows={t.upcoming} />
      </section>
    </div>
  );
}

async function Accounts({ canWrite, selected }: { canWrite: boolean; selected?: string }) {
  const t = await getTreasury().catch(() => null);
  if (!t) return <ErrorBanner message="Comptes indisponibles." />;
  const kinds: Record<string, string> = {
    current: "Compte courant",
    savings: "Épargne",
    card: "Carte",
    loan: "Prêt",
  };
  return (
    <div className="space-y-6">
      {t.accounts.map((a) => (
        <Card key={a.id} className={`p-6 ${selected === a.id ? "border-accent" : ""}`}>
          <div className="flex flex-wrap items-center gap-3">
            <p className="text-[15px] font-semibold text-text">{a.name}</p>
            <Badge label={kinds[a.kind] ?? a.kind} tone="neutral" />
            {a.masked_identifier && <span className="font-mono text-[12px] text-text-faint">{a.masked_identifier}</span>}
            <span className="ml-auto flex items-center gap-2 font-mono text-[16px] font-semibold">
              {fmtMoney(a.balance)} <BasisBadge basis={a.balance_basis as ValueBasis} />
            </span>
          </div>
          <p className="mt-1 text-[12px] text-text-faint">
            {a.bank_name ?? ""} · solde au <span className="num">{fmtDate(a.balance_as_of)}</span>
            {a.kind === "loan" && a.interest_rate !== null ? ` · taux ${(a.interest_rate * 100).toFixed(2)} % · échéance ${fmtDate(a.maturity_at)}` : ""}
            {a.kind !== "loan" ? ` · 30 derniers jours : +${fmtMoney(a.inflows_30d)} / −${fmtMoney(a.outflows_30d)}` : ""}
          </p>
          {a.projection.length > 0 && (
            <div className="mt-4">
              <Projection points={a.projection} />
            </div>
          )}
          {a.upcoming.length > 0 && (
            <div className="mt-4">
              <Flows flows={a.upcoming} />
            </div>
          )}
        </Card>
      ))}
      {t.accounts.length === 0 && <EmptyState message="Aucun compte enregistré." />}
      {canWrite && <AccountForm />}
    </div>
  );
}

async function Ownership({ canWrite }: { canWrite: boolean }) {
  const o = await getOwnership().catch(() => null);
  if (!o) return <ErrorBanner message="Capital indisponible." />;
  const v = o.valuation;
  return (
    <div className="space-y-8">
      <section>
        <SectionLabel>Valeur de l&rsquo;entreprise</SectionLabel>
        <div className="grid gap-4 md:grid-cols-2">
          <Card className="p-6">
            <p className="text-[12.5px] text-text-soft">Valeur estimée des titres</p>
            <p className="mt-1 figure text-[24px]">{v.estimated_min !== null ? fmtMoneyRange(v.estimated_min, v.estimated_max) : "Non estimable"}</p>
            <p className="mt-1 flex items-center gap-2 text-[12px] text-text-faint">
              <BasisBadge basis={v.basis as ValueBasis} /> {CONFIDENCE_LABEL[v.confidence as Confidence] ?? v.confidence}
            </p>
            <p className="mt-2 text-[11.5px] text-text-faint">{v.method} Une estimation, jamais une valeur officielle.</p>
          </Card>
          <Card className="p-6">
            <p className="text-[12.5px] text-text-soft">Valorisation déclarée</p>
            <p className="mt-1 figure text-[24px]">{v.declared ? fmtMoney(v.declared.value) : "Aucune"}</p>
            {v.declared && <p className="mt-1 text-[12px] text-text-faint">Déclarée{v.declared.date ? ` le ${v.declared.date}` : ""}</p>}
          </Card>
        </div>
        <ul className="mt-4 space-y-1.5 text-[13px]">
          {v.inputs.map((i) => (
            <li key={i.label} className="flex flex-wrap items-center gap-2">
              <span className="min-w-[240px] text-text-soft">{i.label}</span>
              <span className="num font-medium text-text">
                {typeof i.value === "number" ? (Math.abs(i.value) < 5 ? `${(i.value * 100).toFixed(1)} %` : fmtMoney(i.value)) : (i.value ?? "Inconnu")}
              </span>
              <BasisBadge basis={i.basis as ValueBasis} />
              <span className="text-[11.5px] text-text-faint">{i.source}</span>
            </li>
          ))}
        </ul>
      </section>
      <section>
        <SectionLabel>Répartition du capital</SectionLabel>
        {o.holders.length === 0 ? (
          <EmptyState message="Aucun actionnaire enregistré." />
        ) : (
          <div className="space-y-4">
            {o.holders.length > 1 && (
              <Card className="p-5">
                <Donut
                  centerLabel="actionnaires"
                  slices={o.holders.map((h) => ({
                    label: h.name,
                    value: h.pct,
                    display: `${(h.pct * 100).toFixed(1)} %`,
                  }))}
                />
                <p className="mt-3 text-[11.5px] text-text-faint">Pourcentage du capital, calculé à partir des parts enregistrées.</p>
              </Card>
            )}
            <Card className="overflow-x-auto p-0">
              <table className="w-full min-w-[640px] text-[12.5px]">
                <thead className="text-left text-text-faint">
                  <tr className="border-b border-border">
                    <th className="px-4 py-2.5 font-medium">Actionnaire</th>
                    <th className="px-4 py-2.5 font-medium">Parts</th>
                    <th className="px-4 py-2.5 font-medium">%</th>
                    <th className="px-4 py-2.5 font-medium">Droits économiques</th>
                    <th className="px-4 py-2.5 font-medium">Valeur estimée</th>
                  </tr>
                </thead>
                <tbody>
                  {o.holders.map((h) => (
                    <tr key={h.id} className="border-b border-border last:border-0">
                      <td className="px-4 py-2.5 text-text">
                        {h.employee_id ? (
                          <Link href={`/people/${h.employee_id}`} className="hover:underline">
                            {h.name}
                          </Link>
                        ) : (
                          h.name
                        )}{" "}
                        <BasisBadge basis={h.basis as ValueBasis} />
                      </td>
                      <td className="px-4 py-2.5 font-mono">
                        {h.shares.toLocaleString("fr-FR")} ({h.share_class})
                      </td>
                      <td className="px-4 py-2.5 font-mono">{(h.pct * 100).toFixed(1)} %</td>
                      <td className="num px-4 py-2.5">
                        {(h.economic_rights_pct * 100).toFixed(1)} %{h.economic_rights_declared ? " (déclaré)" : ""}
                      </td>
                      <td className="num px-4 py-2.5">{h.value_estimated_min !== null ? fmtMoneyRange(h.value_estimated_min, h.value_estimated_max) : "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </Card>
          </div>
        )}
      </section>
      {canWrite && <FinanceSettingsForm initial={{}} />}
    </div>
  );
}
