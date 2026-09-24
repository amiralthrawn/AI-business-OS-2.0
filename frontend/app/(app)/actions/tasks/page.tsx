import TaskBoard from "@/components/actions/TaskBoard";
import ErrorBanner from "@/components/ui/ErrorBanner";
import SectionTabs from "@/components/objects/SectionTabs";
import PageHeader from "@/components/ui/PageHeader";
import { getCustomers, getSuppliers, getTasks } from "@/lib/api";
import type { TaskRead } from "@/lib/types";

export const dynamic = "force-dynamic";

export default async function TasksPage() {
  let tasks: TaskRead[] = [];
  let entityNames: Record<string, string> = {};
  let error: string | null = null;
  try {
    const [taskList, suppliers, customers] = await Promise.all([getTasks(), getSuppliers(), getCustomers()]);
    tasks = taskList;
    entityNames = {
      ...Object.fromEntries(suppliers.map((s) => [s.id, s.name])),
      ...Object.fromEntries(customers.map((c) => [c.id, c.name])),
    };
  } catch (err) {
    error = err instanceof Error ? err.message : "Impossible de charger les tâches.";
  }

  return (
    <main className="mx-auto max-w-4xl space-y-6 p-8 md:p-12">
      <PageHeader
        title="Tâches"
        description="Le centre d'action de l'entreprise. Inclut les actions proposées par l'IA en attente de validation — rien ne s'exécute automatiquement."
      />
      <SectionTabs section="actions" active="tasks" />
      {error && <ErrorBanner message={error} />}
      {!error && <TaskBoard initialTasks={tasks} entityNames={entityNames} />}
    </main>
  );
}
