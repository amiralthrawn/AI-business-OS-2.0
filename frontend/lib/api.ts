import type {
  AskAIResponse,
  BusinessContextRead,
  BusinessContextUpdate,
  CompanyNarrativeItem,
  CompanyRead,
  CompanyUpdate,
  ConfigurationSuggestionRead,
  ConnectorStatus,
  ContactListItem,
  CustomerDetail,
  CustomerListItem,
  FinanceOverview,
  HomeResponse,
  OpportunityRead,
  OSActivityItem,
  ProcurementOverview,
  ProductDetail,
  ProductListItem,
  RiskRead,
  SalesOverview,
  SupplierDetail,
  SupplierListItem,
  TaskCreate,
  TaskRead,
  TaskStatus,
  TransactionRead,
  // V2.1
  AccessCatalog,
  AIRunView,
  CandidateRow,
  ComplianceRecommendation,
  ComplianceRequest,
  EmployeeCost,
  EmployeeDetail,
  EmployeeRow,
  OwnershipView,
  SkillsGapView,
  SourcingLeadView,
  SourcingState,
  TreasuryOverview,
  WebsiteProposal,
  WebsiteState,
  // V2
  Benchmark,
  CatalogProduct,
  CommunicationDetail,
  CommunicationRow,
  DocumentCreateInput,
  DocumentDetail,
  DocumentKind,
  DocumentsMeta,
  DocumentSummary,
  EmailAnalysis,
  FollowUps,
  BillingOverview,
  CreditView,
  PartyAccount,
  Settlement,
  CampaignPerformance,
  FollowUpPerformance,
  MailboxOverview,
  MailboxRow,
  MeRead,
  NewLineInput,
  ObjectContext,
  ObjectSummary,
  ObjectType,
  OrderMarginRow,
  Role,
  RoleRead,
  StockImportResult,
  StockRow,
  SupplierTerms,
  UserProfileRead,
  ValueBasis,
} from "@/lib/types";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

// V2 roles (brain/permissions.md): every call carries the selected user
// profile as `X-User-Id`. The profile id lives in the `aibos_user` cookie;
// in the browser it is read from document.cookie, and on the server a
// resolver registered by `lib/server-user.ts` (imported by the root layout)
// reads it from the incoming request -- so Server and Client Components share
// this one API client. No cookie = the backend's legacy single-operator mode.
export const USER_COOKIE = "aibos_user";

type UserIdResolver = () => Promise<string | null> | string | null;

function readBrowserCookie(): string | null {
  if (typeof document === "undefined") return null;
  const match = document.cookie.split("; ").find((c) => c.startsWith(`${USER_COOKIE}=`));
  return match ? decodeURIComponent(match.split("=")[1]) : null;
}

let resolveUserId: UserIdResolver = readBrowserCookie;

/** Selects (or clears, with null) the profile every following call acts as. */
export function setSelectedProfile(id: string | null) {
  document.cookie = id
    ? `${USER_COOKIE}=${encodeURIComponent(id)}; path=/; max-age=31536000; samesite=lax`
    : `${USER_COOKIE}=; path=/; max-age=0`;
}

export function setServerUserIdResolver(resolver: UserIdResolver) {
  if (typeof window === "undefined") resolveUserId = resolver;
}

async function apiFetch(url: string, init: RequestInit = {}): Promise<Response> {
  const userId = await resolveUserId();
  const headers = new Headers(init.headers);
  if (userId) headers.set("X-User-Id", userId);
  return fetch(url, { ...init, headers });
}

async function getJSON<T>(path: string, notFoundMessage: string): Promise<T> {
  const res = await apiFetch(`${API_URL}${path}`, { cache: "no-store" });
  if (!res.ok) {
    throw new Error(res.status === 404 ? notFoundMessage : `La requête a échoué (${res.status})`);
  }
  return res.json();
}

async function patchJSON<T>(path: string, body: object, failureMessage: string): Promise<T> {
  const res = await apiFetch(`${API_URL}${path}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    cache: "no-store",
  });
  if (!res.ok) {
    const detail = await res.json().catch(() => null);
    throw new Error(detail?.detail ?? `${failureMessage} (${res.status})`);
  }
  return res.json();
}

export async function getHomeView(): Promise<HomeResponse> {
  const res = await apiFetch(`${API_URL}/home`, { cache: "no-store" });
  if (!res.ok) {
    throw new Error(`Failed to load Home view (${res.status})`);
  }
  return res.json();
}

export const getRisks = () => getJSON<RiskRead[]>("/intelligence/risks", "Risques introuvables");
export const getRisk = (id: string) => getJSON<RiskRead>(`/intelligence/risks/${id}`, "Risque introuvable");
export const getOpportunities = () => getJSON<OpportunityRead[]>("/intelligence/opportunities", "Opportunités introuvables");
export const getOpportunity = (id: string) =>
  getJSON<OpportunityRead>(`/intelligence/opportunities/${id}`, "Opportunité introuvable");
export const getTasks = () => getJSON<TaskRead[]>("/actions/tasks", "Tâches introuvables");

export async function askAI(question: string, context?: { objectType: string; objectId: string }): Promise<AskAIResponse> {
  const res = await apiFetch(`${API_URL}/ai/ask`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    // V2: the object on screen, so "cette commande" needs no number.
    body: JSON.stringify(context ? { question, object_type: context.objectType, object_id: context.objectId } : { question }),
    cache: "no-store",
  });
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new Error(body?.detail ?? `Ask AI request failed (${res.status})`);
  }
  return res.json();
}

async function decideOnTask(taskId: string, decision: "approve" | "reject"): Promise<TaskRead> {
  const res = await apiFetch(`${API_URL}/actions/tasks/${taskId}/${decision}`, {
    method: "POST",
    cache: "no-store",
  });
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new Error(body?.detail ?? `Failed to ${decision} the task (${res.status})`);
  }
  return res.json();
}

export const approveTask = (taskId: string) => decideOnTask(taskId, "approve");
export const rejectTask = (taskId: string) => decideOnTask(taskId, "reject");

export async function updateTaskStatus(taskId: string, status: TaskStatus): Promise<TaskRead> {
  const res = await apiFetch(`${API_URL}/actions/tasks/${taskId}/status`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ status }),
    cache: "no-store",
  });
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new Error(body?.detail ?? `Failed to update the task (${res.status})`);
  }
  return res.json();
}

export async function submitTaskForValidation(taskId: string): Promise<TaskRead> {
  const res = await apiFetch(`${API_URL}/actions/tasks/${taskId}/submit`, { method: "POST", cache: "no-store" });
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new Error(body?.detail ?? `Failed to submit the task (${res.status})`);
  }
  return res.json();
}

export async function createTask(payload: TaskCreate): Promise<TaskRead> {
  const res = await apiFetch(`${API_URL}/actions/tasks`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
    cache: "no-store",
  });
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new Error(body?.detail ?? `Failed to create the task (${res.status})`);
  }
  return res.json();
}

// --- "Vie de l'entreprise" (Step 27) -----------------------------------------

export const getOSActivity = (domain?: string, limit = 30) =>
  getJSON<OSActivityItem[]>(`/home/activity?limit=${limit}${domain ? `&domain=${domain}` : ""}`, "Activité introuvable");
export const getCompanyNarrative = (limit = 30) =>
  getJSON<CompanyNarrativeItem[]>(`/home/narrative?limit=${limit}`, "Fil d'activité indisponible");

// --- Business Domain read APIs (Step 23B) -----------------------------------

export const getSuppliers = () => getJSON<SupplierListItem[]>("/suppliers", "Fournisseurs introuvables");
export const getSupplier = (id: string) => getJSON<SupplierDetail>(`/suppliers/${id}`, "Fournisseur introuvable");
export const getCustomers = () => getJSON<CustomerListItem[]>("/customers", "Clients introuvables");
export const getCustomer = (id: string) => getJSON<CustomerDetail>(`/customers/${id}`, "Client introuvable");
export const getProducts = () => getJSON<ProductListItem[]>("/products", "Produits introuvables");
export const getProduct = (id: string) => getJSON<ProductDetail>(`/products/${id}`, "Produit introuvable");
export const getTransactions = () => getJSON<TransactionRead[]>("/transactions", "Transactions introuvables");
export const getTransaction = (id: string) => getJSON<TransactionRead>(`/transactions/${id}`, "Transaction introuvable");
export const getContacts = () => getJSON<ContactListItem[]>("/contacts", "Contacts introuvables");

// --- Connectors (real connection status, Step 28's Contacts page) -----------

export const getConnectors = () => getJSON<{ connectors: ConnectorStatus[] }>("/connectors", "Connecteurs introuvables");

// --- Business Domain overviews (Step 23B) -----------------------------------

export const getFinanceOverview = () => getJSON<FinanceOverview>("/finance/overview", "Vue Finance indisponible");
export const getProcurementOverview = () =>
  getJSON<ProcurementOverview>("/procurement/overview", "Vue Achats indisponible");
export const getSalesOverview = () => getJSON<SalesOverview>("/sales/overview", "Vue Ventes indisponible");

// --- Company & Business Context (Step 26) -----------------------------------

export const getCompany = () => getJSON<CompanyRead>("/company", "Aucune entreprise n'est encore configurée");
export const updateCompany = (payload: CompanyUpdate) =>
  patchJSON<CompanyRead>("/company", payload, "Mise à jour de l'entreprise impossible");

export const getBusinessContext = () =>
  getJSON<BusinessContextRead>("/business-context", "Contexte métier introuvable");
export const updateBusinessContext = (payload: BusinessContextUpdate) =>
  patchJSON<BusinessContextRead>("/business-context", payload, "Mise à jour du contexte métier impossible");
export const getConfigurationSuggestions = () =>
  getJSON<ConfigurationSuggestionRead[]>("/business-context/suggestions", "Aucune suggestion");

// ---------------------------------------------------------------------------
// V2 -- business objects, relationships, transactions (brain/architecture.md)
// ---------------------------------------------------------------------------

async function sendJSON<T>(method: string, path: string, body: unknown | undefined, failureMessage: string, contentType = "application/json"): Promise<T> {
  const res = await apiFetch(`${API_URL}${path}`, {
    method,
    headers: body !== undefined ? { "Content-Type": contentType } : undefined,
    body: body === undefined ? undefined : contentType === "application/json" ? JSON.stringify(body) : (body as string),
    cache: "no-store",
  });
  if (!res.ok) {
    const detail = await res.json().catch(() => null);
    throw new Error(typeof detail?.detail === "string" ? detail.detail : `${failureMessage} (${res.status})`);
  }
  return res.json();
}

function query(params: Record<string, string | number | boolean | string[] | undefined | null>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === "") continue;
    if (Array.isArray(value)) value.forEach((v) => search.append(key, v));
    else search.set(key, String(value));
  }
  const s = search.toString();
  return s ? `?${s}` : "";
}

// Users & roles
export const getMe = () => getJSON<MeRead>("/users/me", "Profil introuvable");
export const getUsers = () => getJSON<UserProfileRead[]>("/users", "Profils introuvables");
export const getRoles = () => getJSON<RoleRead[]>("/users/roles", "Rôles introuvables");
export const createUser = (payload: { name: string; email?: string; role: Role }) =>
  sendJSON<UserProfileRead>("POST", "/users", payload, "Impossible de créer le profil");
export const updateUser = (id: string, payload: Partial<Pick<UserProfileRead, "name" | "email" | "role" | "is_active">>) =>
  sendJSON<UserProfileRead>("PATCH", `/users/${id}`, payload, "Impossible de modifier le profil");

// Objects & relations
export const getObjectContext = (type: ObjectType, id: string) =>
  getJSON<ObjectContext>(`/objects/${type}/${id}/context`, "Objet introuvable");
export const searchObjects = (q: string, types?: ObjectType[]) =>
  getJSON<ObjectSummary[]>(`/objects/search${query({ q, types })}`, "Recherche impossible");
export const linkObjects = (payload: { source_type: ObjectType; source_id: string; target_type: ObjectType; target_id: string; relation?: string; origin?: string }) =>
  sendJSON<{ id: string }>("POST", "/objects/links", payload, "Impossible de lier ces objets");

// Commercial documents
export const getDocumentsMeta = () => getJSON<DocumentsMeta>("/documents/meta", "Référentiel des documents indisponible");
export const listDocuments = (params: { kind?: DocumentKind[]; domain?: "sales" | "procurement"; status?: string; open_only?: boolean; customer_id?: string; supplier_id?: string; q?: string } = {}) =>
  getJSON<DocumentSummary[]>(`/documents${query(params)}`, "Documents introuvables");
export const getDocument = (id: string) => getJSON<DocumentDetail>(`/documents/${id}`, "Document introuvable");
export const getOrderMargins = () => getJSON<OrderMarginRow[]>("/documents/margins", "Marges introuvables");
export const createDocument = (payload: DocumentCreateInput) =>
  sendJSON<DocumentDetail>("POST", "/documents", payload, "Impossible de créer le document");
export const updateDocument = (id: string, payload: Record<string, unknown>) =>
  sendJSON<DocumentDetail>("PATCH", `/documents/${id}`, payload, "Impossible de modifier le document");
export const changeDocumentStatus = (id: string, status: string) =>
  sendJSON<DocumentDetail>("POST", `/documents/${id}/status`, { status }, "Changement de statut impossible");
export const deriveDocument = (id: string, kind: DocumentKind, supplierId?: string) =>
  sendJSON<DocumentDetail>("POST", `/documents/${id}/derive`, { kind, supplier_id: supplierId }, "Création impossible");
export const addDocumentLine = (id: string, line: NewLineInput) =>
  sendJSON<DocumentDetail>("POST", `/documents/${id}/lines`, line, "Ajout de ligne impossible");
export const updateDocumentLine = (id: string, lineId: string, changes: Record<string, unknown>) =>
  sendJSON<DocumentDetail>("PATCH", `/documents/${id}/lines/${lineId}`, changes, "Modification de ligne impossible");
export const removeDocumentLine = (id: string, lineId: string) =>
  sendJSON<DocumentDetail>("DELETE", `/documents/${id}/lines/${lineId}`, undefined, "Suppression impossible");
export const addCostItem = (id: string, payload: { kind: string; amount_min: number; amount_max?: number; basis: ValueBasis; label?: string; reference?: string }) =>
  sendJSON<DocumentDetail>("POST", `/documents/${id}/costs`, payload, "Ajout du coût impossible");

// Catalog, suppliers, stock
export const getCatalogProducts = () => getJSON<CatalogProduct[]>("/catalog/products", "Catalogue introuvable");
export const getCatalogProduct = (id: string) => getJSON<CatalogProduct>(`/catalog/products/${id}`, "Produit introuvable");
export const createCatalogProduct = (payload: { name: string; sku?: string; sale_price?: number; unit_cost?: number; brand?: string }) =>
  sendJSON<CatalogProduct>("POST", "/catalog/products", payload, "Impossible de créer le produit");
export const setSupplierTerms = (productId: string, supplierId: string, terms: Partial<SupplierTerms>) =>
  sendJSON<CatalogProduct>("PUT", `/catalog/products/${productId}/suppliers/${supplierId}`, terms, "Impossible d'enregistrer les conditions");
export const getBenchmark = (productId: string, quantity: number, purchaseRequestId?: string) =>
  getJSON<Benchmark>(`/catalog/products/${productId}/benchmark${query({ quantity, purchase_request_id: purchaseRequestId })}`, "Comparaison impossible");
export const getStock = (kind?: "physical" | "supplier" | "potential") =>
  getJSON<StockRow[]>(`/catalog/stock${query({ kind })}`, "Stock introuvable");
export const importStockCsv = (content: string, filename: string) =>
  sendJSON<StockImportResult>("POST", `/catalog/stock/import${query({ filename })}`, content, "Import impossible", "text/csv");

// Communications
export const listCommunications = (box: "inbox" | "sent" | "drafts" | "all" = "inbox", channel?: string) =>
  getJSON<CommunicationRow[]>(`/communications${query({ box, channel })}`, "Messages introuvables");
export const getCommunication = (id: string) => getJSON<CommunicationDetail>(`/communications/${id}`, "Message introuvable");
export const analyzeCommunication = (id: string) =>
  sendJSON<EmailAnalysis>("POST", `/communications/${id}/analyze`, undefined, "Analyse impossible");
export const createDraft = (payload: { purpose: string; object_type?: ObjectType; object_id?: string; reply_to_id?: string; contact_id?: string }) =>
  sendJSON<CommunicationDetail>("POST", "/communications/drafts", payload, "Préparation du brouillon impossible");
export const updateDraft = (id: string, payload: { subject?: string; body?: string; to_address?: string }) =>
  sendJSON<CommunicationDetail>("PATCH", `/communications/${id}`, payload, "Modification impossible");
export const submitDraft = (id: string) =>
  sendJSON<{ task_id: string; communication: CommunicationDetail }>("POST", `/communications/${id}/submit`, undefined, "Soumission impossible");
export const getFollowUps = () => getJSON<FollowUps>("/follow-ups", "Relances introuvables");
export const getMailboxes = () => getJSON<MailboxOverview>("/communications/mailboxes", "Boîtes introuvables");
export const listMailbox = (key: string) => getJSON<MailboxRow[]>(`/communications/mailboxes/${key}`, "Boîte introuvable");
export const getFollowUpPerformance = () => getJSON<FollowUpPerformance>("/communications/performance", "Performance indisponible");
export const getCampaignPerformance = () => getJSON<CampaignPerformance>("/communications/campaigns", "Campagnes indisponibles");

// ---------------------------------------------------------------------------
// V2.1 -- access, people, director finance, compliance, sourcing, website
// ---------------------------------------------------------------------------

export const getAccessCatalog = () => getJSON<AccessCatalog>("/users/access-catalog", "Catalogue d'accès introuvable");

// People
export const getEmployees = () => getJSON<EmployeeRow[]>("/people/employees", "Employés introuvables");
export const getEmployee = (id: string) => getJSON<EmployeeDetail>(`/people/employees/${id}`, "Employé introuvable");
export const createEmployee = (payload: { full_name: string; job_title?: string; department?: string; skills?: string[] }) =>
  sendJSON<EmployeeRow>("POST", "/people/employees", payload, "Création impossible");
export const addEmployeeCost = (id: string, payload: { kind: string; annual_min: number; annual_max?: number; basis: string; label?: string }) =>
  sendJSON<EmployeeCost>("POST", `/people/employees/${id}/costs`, payload, "Ajout du coût impossible");
export const assignEmployeeTask = (id: string, payload: { title: string; description?: string; due_at?: string }) =>
  sendJSON<{ id: string }>("POST", `/people/employees/${id}/tasks`, payload, "Création de la tâche impossible");
export const proposeEmployeeDecision = (id: string, payload: { kind: string; rationale: string; new_job_title?: string; new_salary?: number }) =>
  sendJSON<{ task_id: string; note: string }>("POST", `/people/employees/${id}/decisions`, payload, "Proposition impossible");
export const getSkillsGap = () => getJSON<SkillsGapView>("/people/skills-gap", "Analyse indisponible");
export const publishSkillGaps = () => sendJSON<{ opportunities_created: number }>("POST", "/people/skills-gap/publish", undefined, "Publication impossible");
export const addSkillNeed = (payload: { skill: string; keywords: string[]; priority: string; reason?: string; expected_impact?: string }) =>
  sendJSON<{ id: string }>("POST", "/people/skill-needs", payload, "Ajout impossible");
export const getCandidates = () => getJSON<CandidateRow[]>("/people/candidates", "Candidats introuvables");
export const getApplications = () => getJSON<{ id: string; subject: string | null; from_address: string | null; occurred_at: string }[]>("/people/applications", "Candidatures introuvables");
export const candidateFromEmail = (communicationId: string) =>
  sendJSON<CandidateRow>("POST", `/people/candidates/from-communication/${communicationId}`, undefined, "Extraction impossible");
export const updateCandidate = (id: string, status: string) => sendJSON<CandidateRow>("PATCH", `/people/candidates/${id}`, { status }, "Mise à jour impossible");

// Director finance
export const getTreasury = () => getJSON<TreasuryOverview>("/treasury/overview", "Trésorerie indisponible");
export const addBankAccount = (payload: { name: string; bank_name?: string; kind: string; identifier?: string; balance: number }) =>
  sendJSON<{ id: string; masked_identifier: string | null }>("POST", "/treasury/accounts", payload, "Ajout du compte impossible");
export const addCashMovement = (payload: { account_id?: string; direction: string; amount: number; status: string; occurred_at: string; category: string; label?: string }) =>
  sendJSON<{ id: string }>("POST", "/treasury/movements", payload, "Ajout du flux impossible");
export const monitorCash = () => sendJSON<{ risk_created: boolean; reason?: string }>("POST", "/treasury/monitor", undefined, "Contrôle impossible");
export const getOwnership = () => getJSON<OwnershipView>("/ownership", "Capital indisponible");
export const updateFinanceSettings = (payload: Record<string, number | string | null>) =>
  sendJSON<Record<string, unknown>>("PATCH", "/ownership/settings", payload, "Enregistrement impossible");

// Compliance
export const getComplianceRequests = () => getJSON<ComplianceRequest[]>("/compliance/requests", "Demandes introuvables");
export const getComplianceCategories = () => getJSON<Record<string, string>>("/compliance/categories", "Catégories introuvables");
export const createComplianceRequest = (payload: { title: string; category: string; description?: string; due_at?: string }) =>
  sendJSON<{ id: string }>("POST", "/compliance/requests", payload, "Création impossible");
export const getComplianceRecommendation = (id: string) =>
  getJSON<ComplianceRecommendation>(`/compliance/requests/${id}/recommendation`, "Recommandation indisponible");
export const askExpert = (taskId: string, supplierId: string) =>
  sendJSON<{ draft_id: string }>("POST", `/compliance/requests/${taskId}/ask-expert/${supplierId}`, undefined, "Préparation impossible");

// Sourcing
export const getSourcing = (prId: string) => getJSON<SourcingState>(`/sourcing/purchase-requests/${prId}`, "Sourcing indisponible");
export const runSourcing = (prId: string) => sendJSON<AIRunView>("POST", `/sourcing/purchase-requests/${prId}/run`, undefined, "Sourcing impossible");
export const convertLead = (leadId: string) =>
  sendJSON<{ supplier_quote_id: string; supplier_id: string }>("POST", `/sourcing/leads/${leadId}/convert`, undefined, "Conversion impossible");
export const discardLead = (leadId: string) => sendJSON<SourcingLeadView>("POST", `/sourcing/leads/${leadId}/discard`, undefined, "Impossible");

// Website intelligence
export const getWebsite = () => getJSON<WebsiteState>("/website", "Analyse du site indisponible");
export const setWebsiteUrl = (url: string | null) => sendJSON<{ website_url: string | null }>("PATCH", "/website/site", { website_url: url }, "Enregistrement impossible");
export const runWebsiteAudit = () => sendJSON<AIRunView & { proposals: WebsiteProposal[] }>("POST", "/website/audit", undefined, "Analyse impossible");
export const submitWebsiteProposal = (id: string) =>
  sendJSON<WebsiteProposal>("POST", `/website/proposals/${id}/submit`, undefined, "Soumission impossible");


// V2.2 -- billing (payments, instalments, accounts, credit notes, deliveries)
export const getBillingOverview = () => getJSON<BillingOverview>("/billing/overview", "Suivi financier indisponible");
export const getCustomerAccount = (id: string) => getJSON<PartyAccount>(`/billing/accounts/customer/${id}`, "Compte client indisponible");
export const getSupplierAccount = (id: string) => getJSON<PartyAccount>(`/billing/accounts/supplier/${id}`, "Compte fournisseur indisponible");
export const recordPayment = (payload: { amount: number; invoice_id?: string; customer_id?: string; supplier_id?: string; occurred_at?: string; label?: string }) =>
  sendJSON<{ movement_id: string; settlement: Settlement | null }>("POST", "/billing/payments", payload, "Enregistrement du paiement impossible");
export const allocatePayment = (movementId: string, invoiceId: string) =>
  sendJSON<Settlement>("POST", `/billing/payments/${movementId}/allocate`, { invoice_id: invoiceId }, "Rapprochement impossible");
export const setInstallments = (docId: string, installments: { due_at: string; amount: number; label?: string }[]) =>
  sendJSON<Settlement>("PUT", `/billing/documents/${docId}/installments`, { installments }, "Échéancier refusé");
export const requestCreditValidation = (docId: string) =>
  sendJSON<{ task_id: string; credit: CreditView }>("POST", `/billing/credit-notes/${docId}/request-validation`, undefined, "Demande de validation impossible");
export const applyCreditNote = (docId: string) => sendJSON<CreditView>("POST", `/billing/credit-notes/${docId}/apply`, undefined, "Imputation impossible");
export const recordRefund = (docId: string, payload: { occurred_at?: string } = {}) =>
  sendJSON<CreditView>("POST", `/billing/credit-notes/${docId}/refund`, payload, "Enregistrement du remboursement impossible");
export const reportNonconformity = (docId: string, payload: { line_id: string; quantity: number; note: string }) =>
  sendJSON<{ risk_id: string; risk_created: boolean }>("POST", `/billing/documents/${docId}/nonconformity`, payload, "Signalement impossible");
