import RiskListItem from "@/components/intelligence/RiskListItem";
import EmptyState from "@/components/ui/EmptyState";
import ErrorBanner from "@/components/ui/ErrorBanner";
import SectionTabs from "@/components/objects/SectionTabs";
import PageHeader from "@/components/ui/PageHeader";
import { getRisks } from "@/lib/api";
import type { RiskRead } from "@/lib/types";

export const dynamic = "force-dynamic";

export default async function RisksPage() {
  let risks: RiskRead[] = [];
  let error: string | null = null;
  try {
    risks = await getRisks();
  } catch (err) {
    error = err instanceof Error ? err.message : "Impossible de charger les risques.";
  }

  return (
    <main className="space-y-8 p-8 md:p-12">
      <PageHeader title="Risques" description="Détectés par l'Intelligence à partir de tendances réelles du Data Core — des règles déterministes, sans LLM." />
      <SectionTabs section="intelligence" active="risks" />
      {error && <ErrorBanner message={error} />}
      {!error && (
        <ul className="space-y-3">
          {risks.length === 0 ? (
            <EmptyState message="Aucun risque détecté pour l'instant." />
          ) : (
            risks.map((risk) => (
              <li key={risk.id}>
                <RiskListItem risk={risk} />
              </li>
            ))
          )}
        </ul>
      )}
    </main>
  );
}
