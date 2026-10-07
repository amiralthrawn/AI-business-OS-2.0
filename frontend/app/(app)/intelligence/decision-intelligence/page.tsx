import { tasksFor } from "@/components/intelligence/AnalysisLevels";
import DecisionCard from "@/components/intelligence/DecisionCard";
import EmptyState from "@/components/ui/EmptyState";
import ErrorBanner from "@/components/ui/ErrorBanner";
import SectionTabs from "@/components/objects/SectionTabs";
import PageHeader from "@/components/ui/PageHeader";
import { getHomeView, getTasks } from "@/lib/api";
import type { DecisionSummary, TaskRead } from "@/lib/types";

export const dynamic = "force-dynamic";

// No dedicated Decision Intelligence endpoint exists (see
// brain/frontend_api_contract.md) -- Decisions are re-hydrated from the
// Event Log's own DecisionProposed entries entirely inside GET /home, which
// already returns the same list Home itself shows.
export default async function DecisionIntelligencePage() {
  let decisions: DecisionSummary[] = [];
  let error: string | null = null;
  const tasks: TaskRead[] = await getTasks().catch(() => []);
  try {
    decisions = (await getHomeView()).decisions;
  } catch (err) {
    error = err instanceof Error ? err.message : "Impossible de charger les décisions.";
  }

  return (
    <main className="mx-auto max-w-3xl space-y-8 p-8 md:p-12">
      <PageHeader
        title="Intelligence décisionnelle"
        description="Chaque analyse se lit en trois temps : ce qui se passe, pourquoi c'est important et ce que l'OS recommande, puis ce que vous pouvez faire et le résultat réellement obtenu."
      />
      <SectionTabs section="intelligence" active="decisions" />
      {error && <ErrorBanner message={error} />}
      {!error && (
        <div className="space-y-3">
          {decisions.length === 0 ? (
            <EmptyState message="Aucune décision produite pour l'instant." />
          ) : (
            decisions.map((decision, i) => <DecisionCard key={i} decision={decision} tasks={tasksFor(tasks, decision.entity_type, decision.entity_id)} />)
          )}
        </div>
      )}
    </main>
  );
}
