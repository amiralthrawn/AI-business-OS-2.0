# Architecture — AI Business OS V2 / V2.1

Reference for how the product is built after V2 (business objects, relations,
transactions) and V2.1 (people, director finance, compliance, sourcing,
website intelligence). V1 layers (Data Core, Business Context, Baseline,
Significance, Snapshot, Observation, Interpretation, Decision, Orchestrator,
HITL) are unchanged in their role; `docs/ARCHITECTURE.md` keeps their detail.

## Principle

```
BUSINESS DATA + BUSINESS OBJECTS
        ↓
RELATIONSHIPS  (one graph over FKs, V1 LinkableMixin pointers and ObjectLink)
        ↓
TRANSACTIONS   (commercial documents → ledger facts V1 already reads)
        ↓
CONTEXT        (object context: breadcrumb, related, history, intelligence, actions)
        ↓
INTELLIGENCE   (V1 Baseline/Significance/Observation/Risk/Opportunity, fed by V2 objects)
        ↓
DECISION → ACTION → HUMAN VALIDATION (V1 HITL, unchanged mechanism)
```

and, across the product: **OBJECT → RELATED OBJECTS → CONTEXT → INTELLIGENCE → ACTION**.

Still a modular monolith (FastAPI + SQLAlchemy + SQLite, Next.js). No
microservices, no queue, no vector DB, no new agent per feature.

## Backend modules

| Module | Role | Since |
|---|---|---|
| `app/core/entities` | Data model. V2 adds `CommercialDocument`(+lines, `CostItem`), `ObjectLink`, `ProductSupplier`, `StockPosition`, `UserProfile`; V2.1 adds `Employee`(+`EmployeeCostItem`), `SkillNeed`, `Candidate`, `BankAccount`, `CashMovement`, `Shareholder`, `SourcingLead`, `AIRun`, `WebsiteChangeProposal`. All additive. | V1→V2.1 |
| `app/objects` | Object registry, **relationship graph**, links, contextual API (`GET /objects/{type}/{id}/context`), search. | V2 |
| `app/transactions` | Document lifecycle (numbering, statuses, derivations), creation/derivation, **ledger posting**, **margin engine**. | V2 |
| `app/catalog` | Products, supplier terms, stock (3 kinds), CSV import. | V2 |
| `app/domains/procurement/benchmark.py` | Supplier benchmark with ranges, bases, recommended point. | V2 |
| `app/communications` | Inbox/sent/drafts, analysis, template/LLM drafts, submit → HITL send, follow-ups at read time. | V2 |
| `app/access` | Roles, custom per-profile access, `require()` dependency, users API. | V2 / V2.1 |
| `app/people` | Employees, cost, contribution, HR decisions (HITL), skills gap, candidates. | V2.1 |
| `app/treasury` | Accounts, cash movements, projection, cash risk, ownership, valuation. | V2.1 |
| `app/compliance` | Compliance requests (Tasks), expert recommendation, request drafts. | V2.1 |
| `app/sourcing` | Sourcing runs and leads for purchase requests. | V2.1 |
| `app/website` | Limited site crawl, SEO issues, change proposals (HITL). | V2.1 |
| `app/ai` | V1 orchestrator + `deals` agent with 3 read capabilities over V2 objects. | V2 |

Every workspace router declares its view permission (`app/main.py`); sensitive
ones (treasury, ownership, employee costs) are director-only by default.

## How V2/V2.1 feed V1 intelligence (no parallel system)

| New data | Path into V1 |
|---|---|
| Confirmed customer order, received reception | posted as `Transaction` facts → margin/customer/supplier analytics, Observation Engine |
| Approved supplier invoice above reference cost | V1 `record_supplier_cost_increase` → `SupplierCostIncreased` → Risk → review Task |
| Sent quote awaiting answer | new Observable `customer_quote_pending_age_days` → Significance → Interpretation → Decision |
| Missing skill | Opportunity "Recruter ou former : X" + `SkillGapDetected` event |
| Cash projection under declared minimum | `CashForecastDeteriorated` + company-level Risk → V1 RiskCreated → review Task |
| Cheaper source stated by a web result | Opportunity on the product + `SourcingOpportunityFound` |
| Employee decision / cost change | Business Events with the employee as subject (timeline) |

Every Business Event now carries a structured subject (`events.subject_type/subject_id`), giving every object an indexed history.

## Frontend

Next.js 16 App Router, server components calling one API client (`lib/api.ts`) that adds the selected profile (`X-User-Id`, from the `aibos_user` cookie) on both server and client. Pages follow the object page pattern (`components/objects/*`): breadcrumb, actions, related objects, signals, timeline, Ask AI with the object as context. See `brain/navigation_v2.md` and `brain/design.md`.

## Deliberately not built

Authentication (profiles are declared identities), multi-tenancy beyond `company_id` columns, scheduler/queue (sweeps and follow-ups are on demand), real Gmail/CMS/bank connectors, crawler, RAG, payroll, ATS, legal platform. See the "Limits" sections of each `brain/*.md`.
