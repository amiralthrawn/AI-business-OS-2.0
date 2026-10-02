// V2 -- business objects, relationships, transactions (brain/architecture.md).
// Re-exported by lib/types.ts, so every import keeps going through "@/lib/types".

/** Where a value comes from. Never collapsed in the UI (brain/decisions.md #34). */
export type ValueBasis = "observed" | "declared" | "estimated" | "benchmark" | "simulated" | "unknown";
export type Confidence = "high" | "medium" | "low" | "none";

export type Role = "director" | "sales" | "procurement" | "operations" | "hr" | "employee";

export interface UserProfileRead {
  id: string;
  name: string;
  email: string | null;
  role: Role;
  is_active: boolean;
  // V2.1 custom access decided by a director (role defaults + grants - revokes).
  access_grants: string[];
  access_revokes: string[];
  permissions: string[];
}

export interface MeRead {
  profile: UserProfileRead | null;
  role: Role;
  role_label: string;
  permissions: string[];
}

export interface RoleRead {
  role: Role;
  label: string;
  permissions: string[];
}

export type ObjectType =
  | "commercial_document"
  | "customer"
  | "supplier"
  | "product"
  | "contact"
  | "communication"
  | "document"
  | "transaction"
  | "task"
  | "risk"
  | "opportunity"
  | "employee"
  | "candidate";

export interface ObjectSummary {
  type: ObjectType;
  id: string;
  title: string;
  subtitle: string | null;
  status: string | null;
  status_label: string | null;
  kind: string | null;
  kind_label: string;
  href: string | null;
  domain: string | null;
  date: string | null;
}

export interface RelatedGroup {
  type: ObjectType;
  label: string;
  count: number;
  items: (ObjectSummary & { relation: string })[];
}

export interface ObjectAction {
  key: string;
  label: string;
  kind: "status" | "derive" | "email" | "create" | "navigate";
  allowed: boolean;
  reason: string | null;
  params: Record<string, string | boolean>;
}

export interface TimelineEntry {
  occurred_at: string;
  label: string;
  event_type: string;
  detail: string | null;
}

export interface ObjectSignal extends ObjectSummary {
  via: string | null;
  description: string | null;
  severity: string | null;
}

export interface ObjectContext {
  object: ObjectSummary;
  breadcrumb: ObjectSummary[];
  related: RelatedGroup[];
  timeline: TimelineEntry[];
  intelligence: ObjectSignal[];
  actions: ObjectAction[];
}

export type DocumentKind =
  | "customer_request"
  | "customer_quote"
  | "customer_order"
  | "customer_delivery"
  | "customer_invoice"
  | "purchase_request"
  | "supplier_quote"
  | "purchase_order"
  | "reception"
  | "supplier_invoice"
  | "customer_credit_note"
  | "supplier_credit_note";

export interface DocumentParty {
  type: "customer" | "supplier";
  id: string;
  name: string;
  status?: string;
  href: string;
}

export interface DocumentSummary {
  id: string;
  kind: DocumentKind;
  kind_label: string;
  domain: "sales" | "procurement";
  number: string;
  status: string;
  status_label: string;
  is_terminal: boolean;
  title: string | null;
  party: DocumentParty | null;
  external_reference: string | null;
  issued_at: string | null;
  due_at: string | null;
  follow_up_at: string | null;
  completed_at: string | null;
  total: number | null;
  total_is_complete: boolean;
  currency: string;
  line_count: number;
}

export interface DocumentLine {
  id: string;
  position: number;
  product_id: string | null;
  product_name: string | null;
  product_sku: string | null;
  description: string | null;
  quantity: number;
  unit: string | null;
  unit_price: number | null;
  price_basis: ValueBasis;
  total: number | null;
  lead_time_min_days: number | null;
  lead_time_max_days: number | null;
  lead_time_basis: ValueBasis;
  moq: number | null;
  spq: number | null;
  planned_unit_cost: number | null;
  planned_cost_basis: ValueBasis | null;
  planned_cost_source: string | null;
  quantity_nonconforming?: number | null;
  nonconformity_note?: string | null;
}

export interface CostItemRead {
  id: string;
  kind: string;
  label: string | null;
  amount_min: number;
  amount_max: number;
  basis: ValueBasis;
  confidence: string;
  reference: string | null;
  line_id: string | null;
}

export interface CostSource {
  stage: string;
  unit_cost: number | null;
  basis: ValueBasis;
  confidence: string;
  source_label: string;
  document_id: string | null;
  document_number: string | null;
}

export interface MarginView {
  revenue: number;
  cost_min: number;
  cost_max: number;
  margin_min: number;
  margin_max: number;
  margin_pct_min: number | null;
  margin_pct_max: number | null;
  cost_basis: "actual" | "partial" | "estimated" | "incomplete";
}

export interface CostRange {
  min: number;
  max: number;
  basis: ValueBasis;
}

export interface DocumentMargin {
  document_id: string;
  number: string;
  kind: DocumentKind;
  currency: string;
  revenue_basis: ValueBasis;
  lines: {
    line_id: string;
    product_id: string | null;
    product_name: string | null;
    quantity: number;
    unit_price: number | null;
    revenue: number | null;
    current: CostSource;
    planned: CostSource;
    current_cost: number | null;
    planned_cost: number | null;
    margin: number | null;
  }[];
  cost_items: { kind: string; current: CostRange | null; planned: CostRange | null; labels: string[] }[];
  current: MarginView;
  planned: MarginView;
  variances: { component: string; planned: number | null; current: number | null; delta: number; explanation: string }[];
  missing: string[];
  allocation_note: string | null;
}

export interface Measure {
  value: number | null;
  min: number | null;
  max: number | null;
  mid: number | null;
  unit: string | null;
  text: string | null;
  basis: ValueBasis;
  confidence: Confidence;
  source: string | null;
}

export interface SupplierCandidate {
  supplier_id: string;
  supplier_name: string;
  country: string | null;
  quote_id: string | null;
  quote_number: string | null;
  quote_status: string | null;
  unit_price: Measure;
  order_quantity: Measure;
  total_cost: Measure;
  lead_time_days: Measure;
  performance: Measure;
  availability: Measure;
  moq: Measure;
  spq: Measure;
  payment_terms: Measure;
  origin_country: Measure;
  certifications: string[];
  open_risks: number;
  score: number | null;
  score_details: Record<string, number>;
  unknown_criteria: string[];
  recommended: boolean;
}

export interface Benchmark {
  product_id: string;
  product_name: string;
  quantity: number;
  purchase_request_id: string | null;
  weights: Record<string, number>;
  candidates: SupplierCandidate[];
  recommended_supplier_id: string | null;
  recommendation_confidence: Confidence;
  explanation: string[];
}

export interface DocumentDetail extends DocumentSummary {
  internal_reference: string | null;
  payment_terms: string | null;
  notes: string | null;
  source: string;
  editable: boolean;
  contact: { id: string; name: string; email: string | null } | null;
  lines: DocumentLine[];
  cost_items: CostItemRead[];
  chain: DocumentSummary[];
  margin?: DocumentMargin;
  benchmarks?: Benchmark[];
  carrier?: string | null;
  tracking_number?: string | null;
  // V2.2 billing views (backend app/billing, brain/billing.md)
  settlement?: Settlement;
  fulfilment?: Fulfilment | null;
  payment?: OrderPayment;
  credit?: CreditView;
}

export interface KindMeta {
  kind: DocumentKind;
  label: string;
  prefix: string;
  domain: "sales" | "procurement";
  party: "customer" | "supplier";
  initial_status: string;
  statuses: Record<string, string>;
  terminal: string[];
  derivations: DocumentKind[];
}

export interface DocumentsMeta {
  kinds: KindMeta[];
  value_basis: ValueBasis[];
  cost_kinds: string[];
}

export interface NewLineInput {
  product_id?: string;
  new_product?: { name: string; sku?: string; sale_price?: number; unit_cost?: number };
  description?: string;
  quantity: number;
  unit_price?: number;
}

export interface DocumentCreateInput {
  kind: DocumentKind;
  customer_id?: string;
  new_customer?: { name: string; country?: string; status?: string };
  supplier_id?: string;
  contact_id?: string;
  title?: string;
  external_reference?: string;
  due_at?: string;
  lines: NewLineInput[];
  derived_from_id?: string;
}

export interface SupplierTerms {
  id: string;
  supplier_id: string;
  supplier_name: string | null;
  supplier_country: string | null;
  supplier_reference: string | null;
  unit_price: number | null;
  currency: string;
  price_basis: ValueBasis;
  moq: number | null;
  spq: number | null;
  lead_time_min_days: number | null;
  lead_time_max_days: number | null;
  lead_time_basis: ValueBasis;
  payment_terms: string | null;
  country_of_origin: string | null;
  certifications: string[];
  is_preferred: boolean;
  last_confirmed_at: string | null;
  source: string;
}

export interface StockEntry {
  id: string;
  quantity: number;
  basis: ValueBasis;
  as_of: string;
  location: string | null;
  source: string;
  supplier_id: string | null;
  supplier_name: string | null;
  external_ref: string | null;
}

export interface CatalogProduct {
  id: string;
  name: string;
  sku: string | null;
  brand: string | null;
  manufacturer: string | null;
  category: string | null;
  description: string | null;
  unit: string | null;
  sale_price: number | null;
  sale_price_basis: ValueBasis;
  unit_cost: number | null;
  unit_cost_basis: ValueBasis;
  preferred_supplier_id: string | null;
  suppliers: SupplierTerms[];
  stock: { physical: StockEntry[]; supplier: StockEntry[]; potential: StockEntry[] };
}

export interface StockRow {
  id: string;
  product_id: string;
  product_name: string | null;
  product_sku: string | null;
  kind: "physical" | "supplier" | "potential";
  quantity: number;
  basis: ValueBasis;
  as_of: string;
  location: string | null;
  supplier_id: string | null;
  supplier_name: string | null;
  source: string;
}

export interface StockImportResult {
  source: string;
  rows: number;
  created_or_updated: number;
  errors: string[];
}

export interface CommunicationRow {
  id: string;
  channel: string;
  channel_detail: string | null;
  direction: "inbound" | "outbound";
  status: "received" | "sent" | "draft" | "pending_validation" | "rejected";
  purpose: string | null;
  subject: string | null;
  snippet: string;
  occurred_at: string;
  from_address: string | null;
  to_address: string | null;
  contact: { id: string; name: string; email: string | null } | null;
  party: ObjectSummary | null;
  source: string | null;
}

export interface CommunicationDetail extends CommunicationRow {
  body: string | null;
  thread: CommunicationRow[];
}

export interface EmailAnalysis {
  intents: { key: string; label: string }[];
  references: (ObjectSummary & { matched: string })[];
  party: ObjectSummary | null;
  suggested_links: (ObjectSummary & { matched: string })[];
  suggested_actions: { purpose: string; label: string }[];
  summary: string;
  generated_by: "rules" | "rules+llm";
}

export interface FollowUpItem {
  object: ObjectSummary;
  reason: string;
  due_at: string;
  overdue_days: number;
  purpose: string;
  party: string | null;
}

export interface FollowUps {
  computed_at_read_time: boolean;
  note: string;
  items: FollowUpItem[];
}

export interface OrderMarginRow {
  document: DocumentSummary;
  current: MarginView;
  planned: MarginView;
}


// Functional mailboxes / follow-up / campaign performance (read-only views,
// backend app/communications/mailboxes.py).
export interface Mailbox {
  key: string;
  address: string; // "sales@" -- a role, not a configured address
  group: string;
  label: string;
  rule: string;
  status: "connected" | "demo" | "not_configured";
  status_reason: string;
  message_count: number;
  inbound_count: number;
  awaiting_reply: number;
  last_at: string | null;
}

export interface MailboxOverview {
  mailboxes: Mailbox[];
  excluded_count: number;
  providers: { connector: string; provider: string; demo: boolean }[];
  method: string;
}

export interface MailboxRow extends CommunicationRow {
  mailbox: string;
  mailbox_reason: string;
  needs_reply: boolean;
}

export interface FollowUpPerformance {
  prepared: number;
  draft: number;
  pending_validation: number;
  rejected: number;
  validated: number;
  sent: number;
  replies_received: number;
  reply_rate: number | null;
  avg_reply_delay_hours: number | null;
  avg_our_response_hours: number | null;
  awaiting_their_reply: number;
  awaiting_our_reply: number;
  orders_linked: { communication_id: string; document_id: string; number: string | null; kind: string }[];
  by_purpose: { purpose: string; prepared: number; sent: number; replied: number }[];
  sufficient: boolean;
  min_sample: number;
  method: string;
}

export interface CampaignView {
  name: string;
  reports: CommunicationRow[];
  feedback: CommunicationRow[];
  declared: { text: string; value_pct: number; source: string; basis: "declared" }[];
  observed: {
    period: string;
    previous_period: string;
    inbound_requests: number;
    previous_inbound_requests: number;
    change_pct: number | null;
    basis: "observed";
    note: string;
  } | null;
  tasks: { id: string; title: string; status: string }[];
  metrics: Record<"budget" | "prospects_attributed" | "opportunities_attributed" | "sales_attributed" | "roi" | "cost_per_prospect", number | null>;
  limits: string[];
}

export interface CampaignPerformance {
  campaigns: CampaignView[];
  agency_proposals: CommunicationRow[];
  channels_connected: string[];
  method: string;
}


// ---------------------------------------------------------------------------
// V2.2 -- payments, instalments, accounts, credit notes, deliveries
// (backend app/billing/service.py). Every amount is derived from recorded
// invoices, payments and imputed credit notes.
// ---------------------------------------------------------------------------

export type InstallmentState = "paid" | "partial" | "due" | "overdue";

export interface Installment {
  id: string | null;
  sequence: number;
  label: string | null;
  due_at: string | null;
  amount: number;
  stored: boolean;
  settled: number;
  remaining: number;
  state: InstallmentState;
  days_late: number;
}

export interface Settlement {
  invoice_id: string;
  number: string;
  status: string;
  status_label: string;
  available: boolean;
  reason?: string;
  total?: number;
  paid?: number;
  credited?: number;
  remaining?: number;
  state?: "paid" | "partially_paid" | "unpaid";
  state_label?: string;
  is_late?: boolean;
  overdue_amount?: number;
  installments?: Installment[];
  installments_paid?: number;
  installments_count?: number;
  schedule_is_default?: boolean;
  next_due?: Installment | null;
  payments?: { id: string; amount: number; occurred_at: string; label: string | null; source: string; simulated: boolean }[];
  credits?: { credit_note_id: string; number: string | null; amount: number; applied_at: string }[];
}

export interface OrderPayment {
  order_total: number | null;
  invoiced: number;
  paid?: number;
  credited?: number;
  remaining?: number;
  installments_paid?: number;
  installments_count?: number;
  next_due?: Installment | null;
  is_late?: boolean;
  overdue_amount?: number;
  state: "paid" | "partially_paid" | "unpaid" | "not_invoiced";
  state_label: string;
  invoices: { id: string; number: string; status_label: string; remaining?: number }[];
}

export interface FulfilmentLine {
  key: string;
  product_id: string | null;
  label: string;
  unit: string | null;
  ordered: number;
  shipped: number;
  done: number;
  nonconforming: number;
  remaining: number;
  in_transit: number;
}

export interface Fulfilment {
  order_id: string;
  kind: "delivery" | "reception";
  state: "not_started" | "planned" | "in_transit" | "partial" | "complete";
  state_label: string;
  is_late: boolean;
  promised_at: string | null;
  progress: number;
  lines: FulfilmentLine[];
  documents: { id: string; number: string; status: string; status_label: string; planned_at: string | null; done_at: string | null; late_days: number; carrier: string | null; tracking_number: string | null; nonconforming_lines: number }[];
  nonconforming_total: number;
}

export interface CreditView {
  credit_note_id: string;
  amount: number | null;
  status: string;
  status_label: string;
  effect: string;
  counts_in_balance: boolean;
  invoice: { id: string; number: string; status_label: string } | null;
  application: { applied_amount: number; refund_amount: number; applied_at: string; invoice_id: string | null } | null;
  refund: { id: string; amount: number; occurred_at: string } | null;
  refund_due: number;
  validation_task_id: string | null;
  can_request_validation: boolean;
  can_apply: boolean;
  can_refund: boolean;
}

export interface AccountStatementEntry {
  date: string;
  kind: "invoice" | "payment" | "unallocated_payment" | "credit_note" | "refund";
  label: string;
  amount: number;
  balance: number;
  document_id: string | null;
  document_number: string | null;
  account_ref: string | null;
  simulated: boolean;
  note: string | null;
}

export interface PartyAccount {
  party_type: "customer" | "supplier";
  party_id: string;
  invoiced: number;
  paid: number;
  credited: number;
  outstanding: number;
  overdue: number;
  unallocated: number;
  credit_on_account: number;
  refund_due: number;
  balance: number;
  is_up_to_date: boolean;
  next_due: (Installment & { invoice_number: string; invoice_id: string }) | null;
  open_invoices: { id: string; number: string; total: number; remaining: number; state_label: string; is_late: boolean; installments_paid: number; installments_count: number; next_due: Installment | null }[];
  unallocated_payments: { id: string; amount: number; occurred_at: string; label: string | null; simulated: boolean }[];
  pending_credit_notes: { id: string; number: string; amount: number; status: string; status_label: string }[];
  statement: AccountStatementEntry[];
  has_simulated: boolean;
  method: string;
}

export interface AccountingRefs {
  configured: Record<string, string>;
  examples: Record<string, { account: string; label: string }>;
  status: "configured" | "to_confirm";
  note: string;
}

export interface BillingOverview {
  receivables: {
    outstanding: number;
    overdue: number;
    overdue_invoices: { id: string; number: string; party: string | null; overdue: number; remaining: number }[];
    upcoming: { invoice_id: string; invoice_number: string; party: string | null; due_at: string; amount: number; label: string | null; state: InstallmentState; days_late: number }[];
  };
  payables: { outstanding: number; overdue: number; open_invoices: { id: string; number: string; party: string | null; remaining: number; is_late: boolean; status_label: string }[] };
  unallocated_payments: { id: string; amount: number; occurred_at: string; label: string | null; direction: "in" | "out"; counterparty: string | null; customer_id: string | null; supplier_id: string | null; simulated: boolean }[];
  credit_notes: { id: string; number: string; kind: DocumentKind; party: string | null; amount: number | null; status: string; status_label: string; needs_action: boolean; refund_due: number; validation_task_id: string | null }[];
  refunds_due: number;
  orders_awaiting_confirmation: { id: string; number: string; party: string | null; status: string; status_label: string; total: number | null; since: string }[];
  deliveries_to_watch: { order_id: string; number: string; party: string | null; kind: "delivery" | "reception"; state: string; state_label: string; is_late: boolean; progress: number; nonconforming: number }[];
  accounting_refs: AccountingRefs;
  method: string;
}
