export type RelatedEntityType = "company" | "supplier" | "customer" | "product" | "transaction" | "contact" | "communication" | "commercial_document" | "employee" | "candidate";

export * from "@/lib/types-v2";
export * from "@/lib/types-v21";

export interface RiskRead {
  id: string;
  company_id: string;
  title: string;
  description: string | null;
  severity: "low" | "medium" | "high" | "critical";
  status: "open" | "acknowledged" | "resolved";
  related_entity_type: RelatedEntityType | null;
  related_entity_id: string | null;
  source_event_id: string | null;
  created_at: string;
}

export interface OpportunityRead {
  id: string;
  company_id: string;
  title: string;
  description: string | null;
  status: "open" | "acknowledged" | "pursued" | "dismissed";
  related_entity_type: RelatedEntityType | null;
  related_entity_id: string | null;
  source_event_id: string | null;
  created_at: string;
}

export type TaskStatus =
  | "pending_validation"
  | "open"
  | "in_progress"
  | "done"
  | "cancelled"
  | "rejected"
  | "executed";

export interface TaskRead {
  id: string;
  company_id: string;
  title: string;
  description: string | null;
  status: TaskStatus;
  domain: string | null;
  requires_decision: boolean;
  related_entity_type: RelatedEntityType | null;
  related_entity_id: string | null;
  source_event_id: string | null;
  pending_action: string | null;
  correlation_id: string | null;
  created_at: string;
}

export interface TaskCreate {
  title: string;
  description?: string;
  domain?: string;
  requires_decision?: boolean;
  related_entity_type?: RelatedEntityType;
  related_entity_id?: string;
}

export interface EventLogEntryRead {
  event_id: string;
  event_type: string;
  source: string;
  correlation_id: string;
  occurred_at: string;
}

// One Business State Snapshot `material_area`, re-exposed as-is by Home
// (see backend app/home/service.py:get_ai_priorities) -- `kind` is the
// Snapshot's own vocabulary, traceable back to its source.
export interface AIPriorityItem {
  kind: "risk" | "opportunity" | "observation" | "interpretation" | "decision";
  interpretation_type: "risk" | "opportunity" | "insight" | "observation" | null;
  domain: string;
  title: string;
  related_entity_type: RelatedEntityType | null;
  related_entity_id: string | null;
  impact: "low" | "medium" | "high";
  urgency: "low" | "medium" | "high";
  confidence: string;
  explanation: string | null;
  recommendation: string | null;
  decision_options: { label: string; expected_benefit: string; trade_offs: string }[] | null;
  detail_kind: "risk" | "opportunity" | null;
  detail_id: string | null;
}

export interface DecisionSummary {
  type: "risk" | "opportunity" | "insight" | "observation";
  problem: string;
  domain: string;
  entity_type: RelatedEntityType | null;
  entity_id: string | null;
  options: { label: string; expected_benefit: string; trade_offs: string }[];
  recommendation: { chosen_option: string | null; reasoning: string };
  confidence: string;
  occurred_at: string;
}

export interface HomeResponse {
  overview: {
    supplier_count: number;
    product_count: number;
    customer_count: number;
    transaction_count: number;
  };
  priorities: AIPriorityItem[];
  risks: {
    total_risks: number;
    high_risks: number;
    recent_risks: RiskRead[];
  };
  opportunities: {
    total_opportunities: number;
    recent_opportunities: OpportunityRead[];
  };
  decisions: DecisionSummary[];
  tasks: {
    total_tasks: number;
    pending_validation_tasks: number;
    recent_tasks: TaskRead[];
  };
  recent_events: EventLogEntryRead[];
  os_activity: OSActivityItem[];
  company_narrative: CompanyNarrativeItem[];
}

// --- "Vie de l'entreprise" (Step 27) -----------------------------------------
// Mirrors backend/app/home/schemas.py's OSActivityRead/CompanyNarrativeItemRead.

export interface OSActivityItem {
  event_type: string;
  domain: string | null;
  label: string;
  detail: string;
  occurred_at: string;
}

export interface CompanyNarrativeItem {
  id: string;
  channel: string;
  channel_detail: string | null;
  direction: "inbound" | "outbound";
  subject: string | null;
  body: string | null;
  occurred_at: string;
  related_entity_type: RelatedEntityType | null;
  related_entity_name: string | null;
}

export interface AskAIResponse {
  answer: string;
  agent: string;
  capabilities_used: string[];
  context: Record<string, unknown>;
  requires_human_validation: boolean;
  action_result: { task_id: string; title: string; status: string; requires_human_validation: boolean } | null;
}

// --- Business Domain read APIs (Step 23B) -----------------------------------
// Mirrors backend/app/data/schemas.py exactly -- every field here is
// composed from an already-existing backend function (get_entity_context,
// app.core.analytics, HomeService.get_ai_priorities), never recomputed here.

export interface IntelligenceSignal {
  kind: string;
  interpretation_type: "risk" | "opportunity" | "insight" | "observation" | null;
  domain: string;
  title: string;
  impact: "low" | "medium" | "high";
  urgency: "low" | "medium" | "high";
  confidence: string;
  explanation: string | null;
  recommendation: string | null;
  decision_options: { label: string; expected_benefit: string; trade_offs: string }[] | null;
  detail_kind: "risk" | "opportunity" | null;
  detail_id: string | null;
}

export interface LinkedProduct {
  id: string;
  name: string;
  sku: string | null;
}

export interface LinkedSupplier {
  id: string;
  name: string;
}

export interface LinkedTransaction {
  id: string;
  type: string;
  status: string;
  amount: number;
  currency: string;
  occurred_at: string;
}

export interface LinkedRisk {
  id: string;
  title: string;
  severity: string;
}

export interface LinkedOpportunity {
  id: string;
  title: string;
}

export interface LinkedTask {
  id: string;
  title: string;
  status: string;
}

export interface LinkedDocument {
  id: string;
  title: string;
  document_type: string | null;
}

export interface LinkedCommunication {
  id: string;
  channel: string;
  direction: string;
  subject: string | null;
}

export interface LinkedContact {
  id: string;
  name: string;
  role: string | null;
  email: string | null;
  phone: string | null;
}

export interface ContactCommunication {
  id: string;
  channel: string;
  channel_detail: string | null;
  direction: string;
  subject: string | null;
  occurred_at: string;
}

export interface ContactListItem {
  id: string;
  name: string;
  role: string | null;
  email: string | null;
  phone: string | null;
  related_entity_type: RelatedEntityType | null;
  related_entity_id: string | null;
  related_entity_name: string | null;
  last_communication: ContactCommunication | null;
}

// Mirrors backend/app/connectors/router.py's GET /connectors -- honest
// connection status, never a fabricated "connected" state (Step 28).
export interface ConnectorStatus {
  connector: string;
  ingested_count: number;
  last_ingested_at: string | null;
}

export interface SupplierListItem {
  id: string;
  name: string;
  country: string | null;
  product_count: number;
  transaction_count: number;
  signal_count: number;
  top_signal: IntelligenceSignal | null;
}

export interface SupplierDetail {
  id: string;
  name: string;
  country: string | null;
  products: LinkedProduct[];
  transactions: LinkedTransaction[];
  communications: LinkedCommunication[];
  contacts: LinkedContact[];
  documents: LinkedDocument[];
  tasks: LinkedTask[];
  open_risks: LinkedRisk[];
  open_opportunities: LinkedOpportunity[];
  intelligence: IntelligenceSignal[];
  delivery_trend: string;
  baseline_avg_delay_days: number | null;
  recent_avg_delay_days: number | null;
  unanswered_message_age_days: number | null;
}

export interface CustomerListItem {
  id: string;
  name: string;
  country: string | null;
  transaction_count: number;
  recent_revenue: number | null;
  signal_count: number;
  top_signal: IntelligenceSignal | null;
}

export interface CustomerDetail {
  id: string;
  name: string;
  country: string | null;
  transactions: LinkedTransaction[];
  communications: LinkedCommunication[];
  contacts: LinkedContact[];
  documents: LinkedDocument[];
  tasks: LinkedTask[];
  open_risks: LinkedRisk[];
  open_opportunities: LinkedOpportunity[];
  intelligence: IntelligenceSignal[];
  revenue_trend: string;
  baseline_revenue: number | null;
  recent_revenue: number | null;
  variation_pct: number | null;
  unanswered_message_age_days: number | null;
}

export interface ProductListItem {
  id: string;
  name: string;
  sku: string | null;
  unit_cost: number | null;
  supplier: LinkedSupplier | null;
  transaction_count: number;
  signal_count: number;
}

export interface ProductDetail {
  id: string;
  name: string;
  sku: string | null;
  unit_cost: number | null;
  supplier: LinkedSupplier | null;
  transactions: LinkedTransaction[];
  open_risks: LinkedRisk[];
  open_opportunities: LinkedOpportunity[];
  intelligence: IntelligenceSignal[];
  margin_trend: string;
  baseline_margin_pct: number | null;
  recent_margin_pct: number | null;
}

export interface TransactionRead {
  id: string;
  type: string;
  status: string;
  amount: number;
  currency: string;
  occurred_at: string;
  expected_at: string | null;
  supplier_id: string | null;
  supplier_name: string | null;
  customer_id: string | null;
  customer_name: string | null;
  product_id: string | null;
  product_name: string | null;
}

// --- Business Domain overviews (Step 23B) -----------------------------------
// Mirrors backend/app/domains/{finance,procurement,sales}/schemas.py exactly.

export interface ProductMargin {
  id: string;
  name: string;
  margin_trend: string;
  recent_margin_pct: number | null;
}

// Mirrors backend/app/core/analytics.MonthlyPoint -- a real, zero-filled
// month total, never an estimate or interpolation (Step 29 point 11).
export interface MonthlyPoint {
  month: string; // "YYYY-MM"
  total_amount: number;
  transaction_count: number;
}

export interface FinanceOverview {
  total_revenue: number;
  total_costs: number;
  overall_margin_pct: number | null;
  transaction_count: number;
  products: ProductMargin[];
  intelligence: IntelligenceSignal[];
  recent_transactions: TransactionRead[];
  monthly_purchases: MonthlyPoint[];
  monthly_sales: MonthlyPoint[];
}

export interface ProcurementOverview {
  supplier_count: number;
  total_spend: number;
  suppliers: SupplierListItem[];
  intelligence: IntelligenceSignal[];
  recent_transactions: TransactionRead[];
  monthly_purchases: MonthlyPoint[];
}

export interface SalesOverview {
  customer_count: number;
  total_revenue: number;
  customers: CustomerListItem[];
  intelligence: IntelligenceSignal[];
  recent_transactions: TransactionRead[];
  monthly_sales: MonthlyPoint[];
}

// --- Company & Business Context (Step 26) -----------------------------------
// Mirrors backend/app/company/schemas.py and backend/app/business_context/schemas.py exactly.

export interface CompanyRead {
  id: string;
  name: string;
  industry: string | null;
}

export interface CompanyUpdate {
  name?: string;
  industry?: string;
}

export interface BusinessContextRead {
  id: string;
  company_id: string;
  company_size: string | null;
  country: string | null;
  business_model: string | null;
  monitored_domains: string[];
  home_focus: string[];
  notification_level: string;
  stated_objectives: string | null;
  declared_baselines: Record<string, number>;
  learned_notes: string[];
  created_at: string;
  updated_at: string;
}

export interface BusinessContextUpdate {
  company_size?: string;
  country?: string;
  business_model?: string;
  monitored_domains?: string[];
  home_focus?: string[];
  notification_level?: string;
  stated_objectives?: string;
  declared_baselines?: Record<string, number>;
}

export interface ConfigurationSuggestionRead {
  field: string;
  current_value: unknown;
  suggested_value: unknown;
  reason: string;
  evidence_count: number;
}
