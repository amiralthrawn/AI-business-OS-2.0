// V2.1 -- people, director finance, compliance, sourcing, website intelligence.
// Re-exported by lib/types.ts.

export interface AccessCatalog {
  items: { permission: string; label: string; group: string; sensitive: boolean }[];
  role_defaults: Record<string, string[]>;
}

export interface CostLine {
  kind: string;
  label: string;
  annual_min: number;
  annual_max: number;
  basis: string;
  confidence: string;
  source: string | null;
  computed: boolean;
}

export interface EmployeeCost {
  lines: CostLine[];
  total_min: number;
  total_max: number;
  basis: string;
  confidence: string;
  explanation: string;
  missing: string[];
}

export interface TaskSummary {
  done_recent: number;
  open: number;
  overdue: number;
  critical_done: number;
  window_days: number;
  total: number;
}

export interface EmployeeRow {
  id: string;
  full_name: string;
  email: string | null;
  job_title: string | null;
  department: string | null;
  status: string;
  hired_at: string | null;
  weekly_hours: number | null;
  leave_days_remaining: number | null;
  skills: string[];
  responsibilities: string[];
  user_id: string | null;
  manager_id: string | null;
  data_basis: string;
  tasks: TaskSummary;
  cost?: { total_min: number; total_max: number; basis: string; confidence: string };
}

export interface Contribution {
  components: { label: string; value: string; basis: string; detail: string | null }[];
  attributable_margin_min: number | null;
  attributable_margin_max: number | null;
  cost_coverage: string | null;
  confidence: string;
  sufficient: boolean;
  statement: string;
}

export interface EmployeeDetail extends Omit<EmployeeRow, "cost"> {
  cost: EmployeeCost | null;
  can_view_costs: boolean;
  contribution: Contribution;
  suggestions: { kind: string; title: string; reasons: string[]; confidence: string; note: string }[];
  task_list: { id: string; title: string; status: string; due_at: string | null; requires_decision: boolean }[];
  decisions: { id: string; title: string; status: string; category: string | null; created_at: string }[];
}

export interface SkillGap {
  need_id: string;
  skill: string;
  level: string;
  priority: string;
  reason: string | null;
  expected_impact: string | null;
  holders: string[];
  basis: string;
  coverage?: string;
  recommendation?: { profile: string; skills: string[]; justification: string; impact: string; priority: string; confidence: string };
}

export interface SkillsGapView {
  team_size: number;
  open_tasks_per_person: number | null;
  gaps: SkillGap[];
  covered: SkillGap[];
}

export interface CandidateRow {
  id: string;
  full_name: string;
  email: string | null;
  applied_for: string | null;
  skills: string[];
  years_experience: number | null;
  status: string;
  basis: string;
  extracted_by: string;
  communication_id: string | null;
  created_at: string;
  matches: { need_id: string; need: string; need_is_gap: boolean; need_priority: string; match: string; matched_skills: string[]; note: string }[];
}

export interface CashFlowItem {
  date: string;
  direction: "in" | "out";
  amount: number;
  status: string;
  category: string;
  label: string;
  account_id: string | null;
  document_id: string | null;
  source: string | null;
}

export interface ProjectionPoint {
  horizon_days: number;
  low: number;
  high: number;
}

export interface AccountView {
  id: string;
  name: string;
  bank_name: string | null;
  kind: string;
  masked_identifier: string | null;
  balance: number;
  balance_basis: string;
  balance_as_of: string;
  source: string;
  inflows_30d: number;
  outflows_30d: number;
  upcoming: CashFlowItem[];
  projection: ProjectionPoint[];
  interest_rate: number | null;
  maturity_at: string | null;
}

export interface TreasuryOverview {
  as_of: string;
  cash_now: number;
  cash_basis: string;
  debt_outstanding: number;
  projection: ProjectionPoint[];
  min_cash: number | null;
  below_min_cash: boolean;
  upcoming: CashFlowItem[];
  accounts: AccountView[];
  method: string;
}

export interface ValuationView {
  declared: { value: number; date: string | null; basis: string } | null;
  estimated_min: number | null;
  estimated_max: number | null;
  basis: string;
  confidence: string;
  inputs: { label: string; value: number | string | null; basis: string; source: string }[];
  method: string;
}

export interface OwnershipView {
  total_shares: number;
  holders: {
    id: string;
    name: string;
    kind: string;
    shares: number;
    share_class: string;
    pct: number;
    economic_rights_pct: number;
    economic_rights_declared: boolean;
    employee_id: string | null;
    basis: string;
    value_estimated_min: number | null;
    value_estimated_max: number | null;
    value_declared: number | null;
  }[];
  valuation: ValuationView;
}

export interface ComplianceRequest {
  id: string;
  title: string;
  description: string | null;
  category: string | null;
  category_label: string;
  status: string;
  due_at: string | null;
  overdue: boolean;
  open: boolean;
  linked: Record<string, number>;
}

export interface ComplianceRecommendation {
  needs_expert: boolean;
  statement: string;
  expert_kind?: string;
  expert_kind_label?: string;
  hours_benchmark?: [number, number];
  options: { supplier_id: string; name: string; kind: string; fee_min: number | null; fee_max: number | null; basis: string; confidence: string; has_contact: boolean }[];
  note?: string;
}

export interface AIRunView {
  id: string;
  kind: string;
  mode: "real" | "simulated" | "partial";
  status: string;
  target: string | null;
  started_at: string;
  finished_at: string | null;
  steps: { label: string; status: string; detail: string | null; at: string }[];
  result: Record<string, unknown>;
}

export interface SourcingLeadView {
  id: string;
  name: string;
  website: string | null;
  country: string | null;
  source_kind: string;
  source_url: string | null;
  snippet: string | null;
  found_price: number | null;
  price_basis: string;
  status: string;
  supplier_id: string | null;
  retrieved_at: string;
}

export interface SourcingState {
  run: AIRunView | null;
  leads: SourcingLeadView[];
  web_search_configured: boolean;
}

export interface WebsiteIssue {
  code: string;
  severity: "high" | "medium" | "low";
  what: string;
  why: string;
  change: string;
  url: string;
}

export interface WebsiteProposal {
  id: string;
  page_url: string;
  field: string;
  current_value: string | null;
  proposed_value: string;
  rationale: string;
  generated_by: string;
  status: string;
  task_id: string | null;
}

export interface WebsiteState {
  website_url: string | null;
  run: AIRunView | null;
  proposals: WebsiteProposal[];
}
