import ComplianceItem, { NewComplianceRequest } from "@/components/compliance/ComplianceItem";
import SectionTabs from "@/components/objects/SectionTabs";
import EmptyState from "@/components/ui/EmptyState";
import ErrorBanner from "@/components/ui/ErrorBanner";
import PageHeader from "@/components/ui/PageHeader";
import { getComplianceCategories, getComplianceRequests, getMe } from "@/lib/api";
import { can } from "@/lib/objects";

export const dynamic = "force-dynamic";

// Compliance (V2.1): not a legal module -- compliance matters are Tasks
// (category + due date) linked to their documents and emails, with a
// recommendation of which outside expert to ask (brain/compliance.md).
export default async function CompliancePage() {
  const me = await getMe().catch(() => null);
  const [requests, categories] = await Promise.all([getComplianceRequests().catch(() => null), getComplianceCategories().catch(() => ({}))]);
  const canWrite = can(me?.permissions, "write:compliance");
  return (
    <main className="mx-auto max-w-4xl space-y-6 p-8 md:p-12">
      <PageHeader title="Conformité & juridique" description="Contrats, NDA, obligations, assurances et échéances — avec le cabinet externe à solliciter si nécessaire." />
      <SectionTabs section="actions" active="compliance" />
      {requests === null ? (
        <ErrorBanner message="Votre profil n'a pas accès à la conformité." />
      ) : (
        <>
          {requests.length === 0 && <EmptyState message="Aucune demande de conformité." />}
          <div className="space-y-3">
            {requests.map((r) => <ComplianceItem key={r.id} item={r} canWrite={canWrite} />)}
          </div>
          {canWrite && <NewComplianceRequest categories={categories} />}
        </>
      )}
    </main>
  );
}
