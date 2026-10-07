// Backend enum values -> French display labels, in one place so every page
// that shows a Transaction/Task/Risk/Opportunity status translates it the
// same way. Mirrors the exact string values of the backend's Python enums
// (backend/app/core/entities/{transaction,task,risk,opportunity}.py).

export const TRANSACTION_TYPE_LABEL: Record<string, string> = {
  purchase_order: "Bon de commande",
  invoice: "Facture",
  sales_order: "Commande client",
};

export const TRANSACTION_STATUS_LABEL: Record<string, string> = {
  draft: "Brouillon",
  confirmed: "Confirmée",
  paid: "Payée",
  cancelled: "Annulée",
};

export function formatEUR(n: number): string {
  const sign = n < 0 ? "-" : "";
  const abs = Math.abs(Math.round(n));
  const str = String(abs).replace(/\B(?=(\d{3})+(?!\d))/g, " ");
  return `${sign}${str} €`;
}

export function formatPercent(n: number, digits = 1): string {
  return `${n.toFixed(digits).replace(".", ",")} %`;
}

export function formatDateFR(iso: string): string {
  return new Date(iso).toLocaleDateString("fr-FR");
}

export function formatTimeFR(iso: string): string {
  return new Date(iso).toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" });
}

// "2026-09" -> "sept. 2026", for the monthly charts (Step 29 point 11).
export function formatMonthFR(month: string, short = true): string {
  const [year, m] = month.split("-").map(Number);
  const date = new Date(Date.UTC(year, m - 1, 1));
  return date.toLocaleDateString("fr-FR", { month: short ? "short" : "long", year: "numeric" });
}

// backend/app/core/entities/communication.py's `channel_detail` is a free
// string -- this is the frontend's own taxonomy for the seeded narrative
// content (Step 27), never asserted by the backend itself.
export const CHANNEL_DETAIL_LABEL_FR: Record<string, string> = {
  campaign_report: "Marketing",
  agency_proposal: "Marketing — proposition",
  contract_signed: "Ventes",
  employee_idea: "Idée d'employé",
  process_feedback: "Remontée interne",
  price_revision: "Achats",
};

// Narrative items that call for a decision/examination ("Ce que l'entreprise
// propose") vs. items that simply report something that already happened
// ("Ce qui s'est passé"). Purely a frontend grouping of real Communication
// rows -- the backend does not model this distinction.
export const NARRATIVE_PROPOSAL_CHANNEL_DETAILS = ["employee_idea", "process_feedback", "agency_proposal"];

// Which sector a narrative item's `channel_detail` belongs to (Step 28's
// per-sector activity view) -- Marketing/RH have no Intelligence Engine of
// their own (see brain/decisions.md), so their only real activity is these
// seeded Communication rows, never a fabricated Observation-style signal.
export const CHANNEL_DETAIL_TO_SECTOR: Record<string, string> = {
  campaign_report: "marketing",
  agency_proposal: "marketing",
  contract_signed: "sales",
  employee_idea: "hr",
  process_feedback: "hr",
  price_revision: "procurement",
};

export const SECTOR_LABEL_FR: Record<string, string> = {
  finance: "Finance",
  procurement: "Achats",
  sales: "Ventes",
  marketing: "Marketing",
  hr: "RH",
  direction: "Direction",
  operations: "Opérations",
};

// AI Orchestrator capability names -> a short French phrase describing what
// was consulted (Step 27: no raw capability identifiers or JSON context
// shown to the user, see brain/decisions.md).
export const CAPABILITY_LABEL_FR: Record<string, string> = {
  get_business_state_snapshot: "le résumé global de l'entreprise",
  read_supplier: "les données du fournisseur",
  read_customer: "les données du client",
  read_product: "les données du produit",
  read_transactions: "l'historique des transactions",
  analyze_margin: "l'analyse de marge",
  analyze_supplier_performance: "la performance du fournisseur",
  analyze_customer_value: "la tendance du client",
  list_priorities: "les priorités actuelles",
  create_task: "la création d'une tâche",
};


// ---------------------------------------------------------------------------
// Business values coming from the API (enums), in French -- ONE dictionary
// for every component (brain/decisions.md #56). Never render a raw value:
// `valueLabel(group, value)`; an unknown value falls back to itself so a new
// backend value is visible (and caught by the FR audit) rather than hidden.
// ---------------------------------------------------------------------------

export const VALUE_LABELS = {
  severity: { low: "faible", medium: "moyenne", high: "élevée", critical: "critique" },
  confidence: { low: "faible", medium: "moyenne", high: "élevée", none: "aucune" },
  signal: {
    risk: "Risque",
    opportunity: "Opportunité",
    insight: "Signal à surveiller",
    observation: "Observation",
    decision: "Décision",
    interpretation: "Interprétation",
  },
  domain: {
    finance: "Finance",
    procurement: "Achats",
    sales: "Ventes",
    operations: "Opérations",
    people: "Équipe",
    compliance: "Conformité",
    website: "Site web",
    marketing: "Marketing",
    hr: "RH",
    company: "Entreprise",
    deals: "Affaires",
  },
  signalStatus: { open: "ouvert", acknowledged: "pris en compte", resolved: "résolu", pursued: "poursuivie", dismissed: "écartée" },
  taskStatus: {
    pending_validation: "en attente de validation",
    open: "à faire",
    in_progress: "en cours",
    done: "terminée",
    cancelled: "annulée",
    rejected: "rejetée",
    executed: "exécutée",
  },
  entity: {
    supplier: "fournisseur",
    customer: "client",
    product: "produit",
    transaction: "transaction",
    company: "entreprise",
    contact: "contact",
    communication: "message",
    commercial_document: "document",
    employee: "employé",
    candidate: "candidat",
  },
  trend: {
    growing: "en croissance",
    declining: "en baisse",
    stable: "stable",
    improving: "en amélioration",
    deteriorating: "en dégradation",
    insufficient_data: "données insuffisantes",
  },
} as const;

export type ValueGroup = keyof typeof VALUE_LABELS;

export function valueLabel(group: ValueGroup, value: string | null | undefined): string {
  if (value === null || value === undefined || value === "") return "—";
  return (VALUE_LABELS[group] as Record<string, string>)[value] ?? value;
}
