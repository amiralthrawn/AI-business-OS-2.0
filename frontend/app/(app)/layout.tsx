import AppShell from "@/components/layout/AppShell";
import { getCompany, getMe, getTasks, getUsers } from "@/lib/api";

export default async function AppLayout({ children }: { children: React.ReactNode }) {
  const [company, tasks, me, users] = await Promise.all([
    getCompany().catch(() => null),
    getTasks().catch(() => []),
    getMe().catch(() => null),
    getUsers().catch(() => []),
  ]);
  const pendingCount = tasks.filter((t) => t.status === "pending_validation").length;

  return (
    <AppShell companyName={company?.name ?? null} pendingCount={pendingCount} me={me} users={users}>
      {children}
    </AppShell>
  );
}
