import Link from "next/link";
import Card from "@/components/ui/Card";
import EmptyState from "@/components/ui/EmptyState";
import ErrorBanner from "@/components/ui/ErrorBanner";
import SectionTabs from "@/components/objects/SectionTabs";
import PageHeader from "@/components/ui/PageHeader";
import { getCompanyNarrative, getOSActivity } from "@/lib/api";
import { CHANNEL_DETAIL_LABEL_FR, CHANNEL_DETAIL_TO_SECTOR, SECTOR_LABEL_FR, formatTimeFR } from "@/lib/labels";

export const dynamic = "force-dynamic";

const SECTORS = ["finance", "sales", "procurement", "marketing", "hr", "direction"];

interface Row {
  occurred_at: string;
  sectorLabel: string | null;
  source: "os" | "vie";
  label: string;
  detail: string;
}

export default async function OSActivityPage({ searchParams }: { searchParams: Promise<{ domain?: string }> }) {
  const { domain } = await searchParams;

  let rows: Row[] = [];
  let error: string | null = null;
  try {
    const [activity, narrative] = await Promise.all([getOSActivity(undefined, 100), getCompanyNarrative(100)]);

    const osRows: Row[] = activity.map((a) => ({
      occurred_at: a.occurred_at,
      sectorLabel: a.domain ? SECTOR_LABEL_FR[a.domain] ?? a.domain : null,
      source: "os",
      label: a.label,
      detail: a.detail,
    }));
    const narrativeRows: Row[] = narrative
      .filter((n) => n.channel_detail && CHANNEL_DETAIL_TO_SECTOR[n.channel_detail])
      .map((n) => ({
        occurred_at: n.occurred_at,
        sectorLabel: SECTOR_LABEL_FR[CHANNEL_DETAIL_TO_SECTOR[n.channel_detail!]] ?? null,
        source: "vie",
        label: CHANNEL_DETAIL_LABEL_FR[n.channel_detail!] ?? "Vie de l'entreprise",
        detail: n.subject ?? "",
      }));

    rows = [...osRows, ...narrativeRows].sort((a, b) => new Date(b.occurred_at).getTime() - new Date(a.occurred_at).getTime());

    if (domain) {
      const wanted = SECTOR_LABEL_FR[domain];
      rows = rows.filter((r) => r.sectorLabel === wanted);
    }
  } catch (err) {
    error = err instanceof Error ? err.message : "Impossible de charger l'activité.";
  }

  return (
    <main className="mx-auto max-w-3xl space-y-8 p-8 md:p-12">
      <PageHeader
        title="Activité de l'entreprise"
        description="Ce que l'OS a analysé ou recommandé, et ce que l'entreprise a vécu, par secteur — jamais une action qui n'a pas réellement eu lieu."
      />
      <SectionTabs section="actions" active="activity" />

      <div className="flex flex-wrap gap-2">
        <Link
          href="/actions/activity"
          className={`rounded-full border-[1.5px] px-3.5 py-1.5 text-[13px] font-medium transition-colors ${
            !domain ? "border-accent bg-accent-soft text-accent-strong font-semibold" : "border-border-strong text-text-soft hover:border-text-faint"
          }`}
        >
          Tous
        </Link>
        {SECTORS.map((s) => (
          <Link
            key={s}
            href={`/actions/activity?domain=${s}`}
            className={`rounded-full border-[1.5px] px-3.5 py-1.5 text-[13px] font-medium transition-colors ${
              domain === s ? "border-accent bg-accent-soft text-accent-strong font-semibold" : "border-border-strong text-text-soft hover:border-text-faint"
            }`}
          >
            {SECTOR_LABEL_FR[s]}
          </Link>
        ))}
      </div>

      {error && <ErrorBanner message={error} />}
      {!error && (
        <Card className="px-6">
          {rows.length === 0 ? (
            <div className="py-6">
              <EmptyState
                message="Aucune donnée disponible pour ce secteur."
                hint="Ce secteur n'a pas encore de source de données connectée (rapports, documents, emails…). L'interface est prête à les recevoir."
              />
            </div>
          ) : (
            rows.map((r, i) => (
              <div key={i} className="flex items-start gap-4 border-b border-border py-3.5 text-[13px] last:border-0">
                <span className="w-12 shrink-0 pt-0.5 font-mono text-[11.5px] text-text-faint">{formatTimeFR(r.occurred_at)}</span>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    {r.sectorLabel && <span className="text-[10.5px] font-bold uppercase tracking-wide text-accent-strong">{r.sectorLabel}</span>}
                    <span className="font-medium text-text">{r.label}</span>
                  </div>
                  <p className="mt-0.5 truncate text-text-soft">{r.detail}</p>
                </div>
              </div>
            ))
          )}
        </Card>
      )}
    </main>
  );
}
