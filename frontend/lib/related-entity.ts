import { getCustomer, getProduct, getSupplier } from "@/lib/api";
import type { AIPriorityItem, HomeResponse, LinkedContact, RelatedEntityType } from "@/lib/types";

// Shared by the Risk and Opportunity detail pages: a Risk/Opportunity row
// only ever carries related_entity_type/id, never the entity's name -- this
// resolves it via the same read APIs the Data pages already use, rather
// than inventing a name or leaving the link unnamed.
export function entityHref(type: RelatedEntityType, id: string): string | null {
  if (type === "supplier") return `/data/suppliers/${id}`;
  if (type === "customer") return `/data/customers/${id}`;
  if (type === "product") return `/data/products/${id}`;
  // V2 objects a Task can point at (e.g. an email awaiting validation).
  if (type === "communication") return `/communications?tab=drafts&message=${id}`;
  if (type === "commercial_document") return `/documents/${id}`;
  if (type === "contact") return `/communications?tab=contacts&contact=${id}`;
  if (type === "employee") return `/people/${id}`;
  if (type === "candidate") return `/people?tab=recruitment&candidate=${id}`;
  return null;
}

export async function resolveEntityName(type: RelatedEntityType | null, id: string | null): Promise<string | null> {
  if (!type || !id) return null;
  try {
    if (type === "supplier") return (await getSupplier(id)).name;
    if (type === "customer") return (await getCustomer(id)).name;
    if (type === "product") return (await getProduct(id)).name;
  } catch {
    return null;
  }
  return null;
}

// The related entity's name AND its first real Contact (Step 27) in one
// fetch, for the Risk/Opportunity detail pages' "Contacter" action -- a
// Product has no contacts. Kept separate from `resolveEntityName` above
// (which many existing call sites only need the name from) to avoid a
// second, duplicate fetch when a caller needs both.
export async function resolveEntityWithContact(
  type: RelatedEntityType | null,
  id: string | null
): Promise<{ name: string | null; contact: LinkedContact | null }> {
  if (!type || !id) return { name: null, contact: null };
  try {
    if (type === "supplier") {
      const supplier = await getSupplier(id);
      return { name: supplier.name, contact: supplier.contacts[0] ?? null };
    }
    if (type === "customer") {
      const customer = await getCustomer(id);
      return { name: customer.name, contact: customer.contacts[0] ?? null };
    }
    if (type === "product") return { name: (await getProduct(id)).name, contact: null };
  } catch {
    return { name: null, contact: null };
  }
  return { name: null, contact: null };
}

// Risk/Opportunity rows have no confidence/explanation of their own -- both
// live on the Business State Snapshot's material area that produced them,
// already returned by GET /home. Matching on (detail_kind, detail_id) finds
// the same one Home itself would link back to this same Risk/Opportunity.
export function findPriorityFor(home: HomeResponse, kind: "risk" | "opportunity", id: string): AIPriorityItem | null {
  return home.priorities.find((p) => p.detail_kind === kind && p.detail_id === id) ?? null;
}
