import OpportunityListItem from "@/components/intelligence/OpportunityListItem";
import EmptyState from "@/components/ui/EmptyState";
import ErrorBanner from "@/components/ui/ErrorBanner";
import SectionTabs from "@/components/objects/SectionTabs";
import PageHeader from "@/components/ui/PageHeader";
import { getOpportunities } from "@/lib/api";
import type { OpportunityRead } from "@/lib/types";

export const dynamic = "force-dynamic";

export default async function OpportunitiesPage() {
  let opportunities: OpportunityRead[] = [];
  let error: string | null = null;
  try {
    opportunities = await getOpportunities();
  } catch (err) {
    error = err instanceof Error ? err.message : "Impossible de charger les opportunités.";
  }

  return (
    <main className="space-y-8 p-8 md:p-12">
      <PageHeader title="Opportunités" description="Détectées par l'Intelligence à partir de tendances réelles du Data Core — des règles déterministes, sans LLM." />
      <SectionTabs section="intelligence" active="opportunities" />
      {error && <ErrorBanner message={error} />}
      {!error && (
        <ul className="space-y-3">
          {opportunities.length === 0 ? (
            <EmptyState message="Aucune opportunité détectée pour l'instant." />
          ) : (
            opportunities.map((opportunity) => (
              <li key={opportunity.id}>
                <OpportunityListItem opportunity={opportunity} />
              </li>
            ))
          )}
        </ul>
      )}
    </main>
  );
}
