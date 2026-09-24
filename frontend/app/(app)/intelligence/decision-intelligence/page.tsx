import DecisionCard from "@/components/intelligence/DecisionCard";
import EmptyState from "@/components/ui/EmptyState";
import ErrorBanner from "@/components/ui/ErrorBanner";
import SectionTabs from "@/components/objects/SectionTabs";
import PageHeader from "@/components/ui/PageHeader";
import { getHomeView } from "@/lib/api";
import type { DecisionSummary } from "@/lib/types";

export const dynamic = "force-dynamic";

// No dedicated Decision Intelligence endpoint exists (see
// brain/frontend_api_contract.md) -- Decisions are re-hydrated from the
// Event Log's own DecisionProposed entries entirely inside GET /home, which
// already returns the same list Home itself shows.
export default async function DecisionIntelligencePage() {
  let decisions: DecisionSummary[] = [];
  let error: string | null = null;
  try {
    decisions = (await getHomeView()).decisions;
  } catch (err) {
    error = err instanceof Error ? err.message : "Impossible de charger les décisions.";
  }

  return (
    <main className="mx-auto max-w-3xl space-y-8 p-8 md:p-12">
      <PageHeader
        title="Intelligence décisionnelle"
        description="Options, recommandation et confiance produites par le moteur de Décision Intelligence à partir de vrais risques, opportunités et insights — jamais de chaîne de raisonnement affichée."
      />
      <SectionTabs section="intelligence" active="decisions" />
      {error && <ErrorBanner message={error} />}
      {!error && (
        <div className="space-y-3">
          {decisions.length === 0 ? (
            <EmptyState message="Aucune décision produite pour l'instant." />
          ) : (
            decisions.map((decision, i) => <DecisionCard key={i} decision={decision} />)
          )}
        </div>
      )}
    </main>
  );
}
