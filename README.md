# AI Business OS 2.0

**A decision-and-action operating system for small and mid-size companies.**

AI Business OS gives a company one place that says, in plain language, *what is happening*, *why it matters* and *what to do next*, and then lets a human validate the action before anything is sent, changed or executed.

Most business software either stores records (ERP, CRM) or charts them (BI dashboards). AI Business OS aims at a third thing: it connects operational data, business objects and transactions, detects what deserves attention, and turns it into concrete, explainable decisions and actions, with a human always in the loop.

> **Project status:** a working MVP built incrementally as a technical portfolio project. This README describes what is **implemented today**, not a target design. Everything simulated or not yet connected is listed in [Limitations and honesty](#limitations-and-honesty). Every non-obvious design choice is recorded in [`brain/decisions.md`](brain/decisions.md).

---

## Table of contents

- [Vision](#vision)
- [From V1 to V2: what fundamentally changed](#from-v1-to-v2-what-fundamentally-changed)
- [Design principles](#design-principles)
- [How it works](#how-it-works)
- [Implemented capabilities](#implemented-capabilities)
- [Product tour](#product-tour)
- [Architecture](#architecture)
- [Quick Start (Windows)](#quick-start-windows)
- [Deploying on Render](#deploying-on-render)
- [Testing and quality checks](#testing-and-quality-checks)
- [Limitations and honesty](#limitations-and-honesty)
- [Documentation](#documentation)

---

## Vision

A company is not a set of tables. It is a web of customers, suppliers, products, quotes, orders, invoices, emails, people and cash, and every one of these relates to the others. A decision is only as good as the context around it.

AI Business OS is designed around a single loop:

```text
OBJECT  →  RELATED OBJECTS  →  CONTEXT  →  INTELLIGENCE  →  DECISION  →  ACTION  →  HUMAN VALIDATION
```

- **Decision-oriented.** The Command Center answers "what needs my attention and what should I decide?", not "here are forty charts".
- **Action-oriented.** Insights end in something you can do: a draft email, a task, a purchase order, an HR decision, a website change. Each one is prepared by the system and approved by a person.
- **Explainable.** Every conclusion shows its reasoning trail and the data it came from. Every value carries its basis (observed, declared, estimated, benchmark, simulated or unknown).
- **Honest.** When data is missing, the product says so ("données insuffisantes", "non configuré") instead of inventing a number, a trend or an integration.

## From V1 to V2: what fundamentally changed

**V1** established the intelligence pipeline: a Data Core, baselines, significance scoring, observation, interpretation into risks and opportunities, decision options, and a Human-in-the-loop (HITL) task executor. It reasoned mostly over flat *transactions*.

**V2** reorganised the product around **business objects and their relationships**, so intelligence and actions work on the real shape of a company's activity. **V2.1** extended that model to people, director-level finance, compliance, sourcing and website intelligence.

| Dimension | V1 | V2 / V2.1 |
|---|---|---|
| **Business objects** | Suppliers, customers, products, flat transactions | Commercial documents (customer request → quote → order → delivery → invoice; purchase request → supplier quote → purchase order → reception → supplier invoice), document lines, cost items, catalog and stock, employees, candidates, bank accounts, shareholders |
| **Relations** | Foreign keys and a single "related entity" pointer | One **relationship graph** over three storages (FKs, V1 pointers, a generic `ObjectLink` table) and a contextual API that returns any object with its breadcrumb, related objects, history, signals and allowed actions |
| **Transactions** | Recorded facts only | Documents with a lifecycle, numbering and derivation chain, **posted** into the V1 ledger. Planned vs. actual **margin engine**, **supplier benchmark** with ranges and confidence |
| **Intelligence** | Risks and opportunities over transactions | The same V1 engine, fed by V2 objects: late quotes, supplier cost increases, cash below the declared minimum, skill gaps, cheaper sources found. No parallel AI system |
| **Actions** | Tasks, including AI-proposed tasks pending validation | Contextual actions on every object (derive, draft email, submit for approval, apply HR decision, apply website change) through the **same** HITL mechanism |
| **Human-in-the-loop** | Approve or reject a proposed task | Also covers outbound email, HR decisions and website changes. Approval rights depend on role and custom per-profile access, and sensitive domains are director-only |
| **Users** | Single implicit operator | Roles (director, sales, procurement, operations, HR, employee) with custom grants/revokes, enforced by the backend |

## Design principles

1. **Modular monolith.** One FastAPI backend and one Next.js frontend. No microservices, message queue, vector database or multi-agent framework.
2. **Deterministic first, LLM second.** Classification, scoring, margins, projections and recommendations are deterministic Python. An LLM, when configured, only rewrites explanations or drafts in natural language, and is instructed not to add facts. Without an API key, the product runs fully offline with deterministic text.
3. **Nothing external happens without a human.** Every outbound or sensitive action becomes a `PENDING_VALIDATION` task that a person with the right permission approves or rejects.
4. **Uncertainty is visible.** Values carry a basis and confidence, and ranges stay ranges instead of being collapsed to a midpoint. Simulated demo data is stored as simulated and shown with a red "Simulé" badge.
5. **No invented history.** Charts use real series only, and too little history produces an explicit empty state, not an extrapolation.

## How it works

```text
BUSINESS DATA + BUSINESS OBJECTS
        ↓
RELATIONSHIPS   one graph over FKs, V1 pointers and ObjectLink
        ↓
TRANSACTIONS    commercial documents → ledger facts the V1 analytics already read
        ↓
CONTEXT         GET /objects/{type}/{id}/context: breadcrumb, related, history, signals, actions
        ↓
INTELLIGENCE    Business Context → Baseline → Significance → Observation
                → Interpretation (risk / opportunity / insight) → Decision options
        ↓
DECISION → ACTION → HUMAN VALIDATION → RESULT (a real status change, never simulated)
```

The AI Orchestrator answers targeted or cross-domain questions ("why is our margin dropping?") by reading a derived Business State Snapshot and calling only the typed capabilities it needs, rather than scanning the database blindly. Layer-by-layer detail lives in [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) (V1 layers) and [`brain/architecture.md`](brain/architecture.md) (V2/V2.1).

## Implemented capabilities

### V1 foundation (kept, now fed by V2 objects)

- **Business Context** (company profile, monitored domains, objectives, declared baselines), with configuration suggestions that are never auto-applied.
- **Baseline and Significance**: what "normal" is for a metric (observed, declared or generic), and whether a deviation matters across several independent dimensions.
- **Observation → Interpretation → Decision**: pluggable observables, deterministic classification into risks and opportunities, and two or three decision options with trade-offs and a recommendation.
- **Tasks and HITL executor**: the single place where tasks are written and approved actions are executed.
- **Ask AI** over the Orchestrator, plus a `deals` agent with read capabilities over V2 objects.

### V2: business objects, relations and transactions

- **Commercial documents** for the full sales and purchasing flows, with statuses, numbering, derivation (quote → order → delivery → invoice) and posting into the ledger.
- **Relationship graph and contextual API**: every object page shows its breadcrumb, related objects, timeline, open signals and the actions allowed for the current user. Forbidden actions stay visible but disabled, with the reason.
- **Margin engine**: planned vs. current margin per order and line, with cost items (transport, customs, insurance…) and their basis.
- **Supplier benchmark**: total cost and lead-time ranges per supplier for a given quantity, with a recommended option and its confidence.
- **Catalog and stock**: products, supplier terms, three kinds of stock, CSV import.
- **Communications hub**: inbox, sent and drafts, message analysis (intents, document references, suggested links), template- or LLM-assisted drafts, submission for approval, and follow-ups computed at read time (no scheduler).
- **Roles and permissions** enforced on every router.

### V2.1: people, director finance, compliance, sourcing, website

- **People**: employees, labelled cost ranges, measurable contribution (never a ranking or a verdict), skills-gap analysis, candidates created from application emails, and HR decisions applied only after director approval.
- **Director finance** (director-only by default):
  - treasury with accounts (masked identifiers only);
  - planned, actual and estimated cash movements, and receivables/payables read from documents;
  - a **30/60/90-day projection as a low–high range**, with a cash-risk signal below the declared minimum;
  - cap table, and an **estimated valuation range** (never an official value).
- **Compliance and outside experts**: compliance matters as tasks linked to the documents they concern, a recommendation of the expertise needed, fee *estimates*, and draft requests to experts.
- **Sourcing**: sourcing runs for purchase requests with visible steps. Leads come from known suppliers or real web results with their URL, and a price is recorded only when the source states it.
- **Website intelligence**: limited same-domain crawl (robots.txt respected) and SEO issues with what/why/how. Change proposals are shown as diffs and approved through HITL, then *applied manually*, since there is no CMS connector.
- **AI activity visibility**: each AI run records its real steps and mode (real, simulated or partial).

### UX finishing pass

- **Typography**: titles in Fraunces, interface in Plus Jakarta Sans, and **every number in IBM Plex Mono with tabular figures**, centralised in `globals.css`.
- **Director charts**:
  - interactive sparklines built **only from real monthly series**, with a 3-month minimum and the current month marked partial;
  - range bars for the treasury projection against the declared minimum;
  - a donut for the capital distribution;
  - hover tooltips and entry animations, all respecting `prefers-reduced-motion`.
- **Functional mailboxes** (sales@, orders@, rfq@, careers@, support@, contact@):
  - a deterministic, displayed classification of existing messages;
  - honest status per box: *Connectée* / *Démonstration* / *Non configurée*;
  - an "awaiting reply" indicator, and the existing AI draft → edit → HITL send flow.
- **Follow-up performance**: prepared, pending, validated, sent, replies and linked orders are counted as separate stages. Rates are shown only from 3 sent messages.
- **Campaign performance**:
  - *declared* figures (from reports) separated from *observed* counts;
  - budget, attribution and ROI marked "not available" until real data and links exist;
  - rule-based recommendations that state the data used and their limits.
- **Onboarding** (5-step wizard) stays at `/onboarding` and is reachable from Configuration. Direct access to the app is unchanged.

## Product tour

| Area | Route | What you can do |
|---|---|---|
| Command Center | `/` | KPIs with real monthly trends, sector pulse, operations in progress, director view, decisions to take, pending validations |
| Sales / Procurement / Finance | `/business/sales`, `/business/procurement`, `/business/finance` | Deals pipeline, supplier consultations and benchmark, 12-month trends, margins |
| Documents | `/documents/[id]`, `/documents/new` | Full document lifecycle, lines, margin, derivations, related objects |
| Catalog & stock | `/data/products` | Products, supplier terms, stock positions, CSV import |
| Communications | `/communications` | Mailboxes, inbox, drafts and validation, follow-ups and performance, contacts, channels and campaigns, website & SEO |
| People | `/people` | Employees, cost, contribution, skills gap, candidates, HR decisions |
| Direction | `/direction` | Treasury, accounts, projection, cap table and valuation (director-only) |
| Intelligence | `/intelligence/*` | Risks, opportunities and decision intelligence, each with its reasoning trail |
| Actions & validations | `/actions/tasks`, `/actions/compliance` | Task board, approvals, compliance matters |
| Ask AI | `/ai/ask-ai` | Questions answered by the Orchestrator |
| Configuration | `/settings` | Business context, users, roles and custom access, link to the onboarding wizard |
| Onboarding | `/onboarding` | Step-by-step setup (company, organisation, systems, role, summary) |

Routes such as `/business/crm`, `/business/hr`, `/business/marketing`, `/business/supply-chain`, `/ai/agents`, `/ai/reports`, `/actions/emails`, `/actions/workflows`, `/actions/automations`, `/data/documents` and `/intelligence/external-intelligence` are **placeholders** ("Pas encore disponible dans ce MVP") and are not linked from the sidebar.

## Architecture

### Tech stack

| Layer | Technologies |
|---|---|
| Backend | Python 3.10+, FastAPI, SQLAlchemy 2, Alembic, Pydantic v2, pydantic-settings, SQLite (local) or PostgreSQL (psycopg 3), pytest, `openai` SDK (optional) |
| Frontend | Next.js 16 (App Router, Turbopack), React 19, TypeScript, Tailwind CSS v4, ESLint 9. Charts are hand-built SVG (no charting library) |
| Tooling | PowerShell launchers for Windows, optional Cloudflare quick tunnel for temporary public demos |

### Backend modules

| Module | Responsibility |
|---|---|
| `app/core` | Data model (entities), analytics, baseline, significance, event bus |
| `app/objects` | Object registry, relationship graph, links, contextual API, search |
| `app/transactions` | Document lifecycle, derivation, ledger posting, margin engine |
| `app/catalog` | Products, supplier terms, stock, CSV import |
| `app/domains` | Finance, procurement (incl. benchmark) and sales overviews. `crm`, `hr`, `marketing` and `supply_chain` are empty placeholders |
| `app/observation`, `app/interpretation`, `app/decision`, `app/snapshot` | V1 intelligence pipeline |
| `app/ai` | Orchestrator, capabilities, agents, Ask AI, LLM abstraction with a deterministic fallback |
| `app/actions` | Task lifecycle and the HITL action executor |
| `app/communications` | Messages, analysis, drafts, submission, follow-ups, mailboxes and performance views |
| `app/connectors` | Mock email, calendar and website providers plus the ingestion pipeline |
| `app/access` | Roles, permission catalog, custom access, `require()` dependency |
| `app/people`, `app/treasury`, `app/compliance`, `app/sourcing`, `app/website` | V2.1 domains |
| `app/home` | Command Center read model (composes, computes nothing new) |

### Repository structure

```text
AI-business-OS/
├── README.md
├── .env.example            # configuration template (copy to .env)
├── start.bat / start.ps1   # local launcher: backend + frontend in two windows
├── demo.bat / demo.ps1     # optional temporary public demo via Cloudflare quick tunnels
├── docs/ARCHITECTURE.md    # V1 architecture reference, one section per layer
├── brain/                  # per-topic design notes and the decision log
├── backend/
│   ├── app/                # FastAPI application (modules above)
│   ├── alembic/            # database migrations
│   ├── data/               # seed.py (+ seed_v2.py, seed_v21.py): idempotent demo data
│   ├── tests/              # pytest suite
│   └── requirements.txt
└── frontend/
    ├── app/                # Next.js routes: onboarding/ and (app)/ (the main shell)
    ├── components/         # ui/ primitives, objects/, communications/, home/, direction/…
    ├── lib/                # API client, types, formatting, series helpers, i18n
    └── package.json
```

## Quick Start (Windows)

Tested on Windows 11 with Python 3.10 and Node.js 24. All commands below are **PowerShell**, run from the repository root unless stated otherwise.

### Prerequisites

- **Python 3.10+** (`python --version`)
- **Node.js 20.9+** and npm (required by Next.js 16; `node --version`)
- Git

### 1. Configuration

```powershell
Copy-Item .env.example .env
```

The backend reads `.env` at the repository root. Every value is optional for a local run:

| Variable | Purpose | Default |
|---|---|---|
| `DATABASE_URL` | SQLite file (relative to `backend/`) or a PostgreSQL URL (`postgres://…` / `postgresql://…` are accepted as-is) | `sqlite:///./data_core.db` |
| `OPENAI_API_KEY` | Enables LLM rewording of explanations and drafts. Leave empty to run fully offline with deterministic text | empty |
| `OPENAI_MODEL` | Model used when a key is set | `gpt-4o-mini` |
| `ALLOWED_ORIGINS` | CORS origins for a deployed frontend. Empty = any `localhost` / `127.0.0.1` port | empty |
| `BRAVE_SEARCH_API_KEY` | Enables real web search in supplier sourcing. Empty = internal data only, and the run says so | empty |

The frontend calls `http://localhost:8000` by default. To point it elsewhere, set `NEXT_PUBLIC_API_URL` in `frontend/.env.local` (template: [`frontend/.env.example`](frontend/.env.example); never committed); Next.js does not read the root `.env`. The value is compiled into the browser bundle when `npm run dev` starts, so **restart `npm run dev` after changing it**. The terminal prints `[AI Business OS] Browser API URL: …` at startup so you can check it.

### 2. Backend: install, migrate, seed

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m data.seed
cd ..
```

Calling the virtual environment's `python.exe` directly avoids PowerShell's script execution policy for `Activate.ps1`. The seed is **idempotent**: it loads the V1 demo company, then the V2 deals and the V2.1 simulated data, and re-running it skips what already exists.

### 3. Frontend: install

```powershell
cd frontend
npm install
cd ..
```

### 4. Run

**Option A: launcher.** Double-click `start.bat`, or from PowerShell:

```powershell
.\start.ps1
```

It starts the backend and the frontend in their own windows and opens the browser once the frontend responds. If a port is already in use, it skips that server and says so. Closing the launcher window does not stop the servers; close their windows (or press Ctrl+C in them).

**Option B: manual, two terminals.**

```powershell
# Terminal 1
cd backend
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

```powershell
# Terminal 2
cd frontend
npm run dev
```

| Service | URL |
|---|---|
| App | http://localhost:3000 |
| API | http://localhost:8000 |
| API docs (Swagger UI) | http://localhost:8000/docs |
| Health check | http://localhost:8000/health |

On first visit, the Command Center redirects to the onboarding wizard (`/onboarding`), which you can complete or skip. The profile menu in the top bar switches between the demo user profiles (director, sales, procurement…) to see role-based navigation and permissions.

### Optional: temporary public demo

`demo.bat` / `demo.ps1` expose the local backend and frontend through two anonymous Cloudflare quick tunnels (`*.trycloudflare.com`). It requires [`cloudflared`](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/) and free ports 8000/3000. The URLs disappear when the windows are closed, and the app still runs on your machine. Only share them for short, supervised demos (see the access-control limitation below).

To do the same by hand, in four terminals, in this order:

```powershell
# 1. Backend (local mode: ALLOWED_ORIGINS empty accepts localhost and https://*.trycloudflare.com)
cd backend
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000

# 2. Backend tunnel: note the https://<random>.trycloudflare.com URL it prints
cloudflared tunnel --url http://localhost:8000

# 3. Frontend, started WITH that backend URL (restart it whenever the backend tunnel changes)
cd frontend
$env:NEXT_PUBLIC_API_URL = "<backend tunnel URL from step 2>"
npm run dev

# 4. Frontend tunnel: share the URL it prints
cloudflared tunnel --url http://localhost:3000
```

Quick Tunnel URLs change on every restart and are never stored in the code or config. If the page shows `Load failed` (Safari) or `Failed to fetch` (Chrome), the frontend is almost always still pointing at an expired backend tunnel: check the `Browser API URL` line printed by `npm run dev` and restart it with the current URL.

## Deploying on Render

The repository runs as two Render web services from the same GitHub repository. Nothing is hard-coded: everything comes from environment variables.

**Backend** (Python web service, root directory `backend`)

| Setting | Value |
|---|---|
| Build command | `pip install -r requirements.txt` |
| Start command | `alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port $PORT` |
| `DATABASE_URL` | The Render PostgreSQL **internal** URL (recommended), or `sqlite:////var/data/data_core.db` with a persistent disk mounted on `/var/data`. Without one of them, data is lost at each deploy. |
| `ALLOWED_ORIGINS` | The frontend URL, e.g. `https://<frontend>.onrender.com` (comma-separated if several). When set, only these origins are accepted: no `localhost`, no tunnels. |
| `OPENAI_API_KEY`, `BRAVE_SEARCH_API_KEY` | Optional. |

Load the demo data once, from the backend service's shell: `python -m data.seed` (idempotent).

**Frontend** (Node web service, root directory `frontend`)

| Setting | Value |
|---|---|
| Build command | `npm ci && npm run build` |
| Start command | `npm run start -- -p $PORT` |
| `NEXT_PUBLIC_API_URL` | The backend URL, e.g. `https://<backend>.onrender.com`. It is compiled into the build: change it, then redeploy. |

The migrations and the full demo seed were validated on PostgreSQL as well as SQLite. The access-control limitation below applies: identity is not verified, so keep a public deployment for supervised demos.

## Testing and quality checks

```powershell
# Backend: 390 tests at the time of writing
cd backend
.\.venv\Scripts\python.exe -m pytest -q
cd ..

# Frontend: lint and production build (includes type-checking)
cd frontend
npm run lint
npm run build
cd ..
```

The test suite runs on isolated test databases and does not modify `backend/data_core.db`. There is no frontend unit test runner yet: ESLint and the `next build` type check are the frontend quality gates.

## Limitations and honesty

This is an MVP. The following are deliberate, documented limits, not hidden gaps.

### Simulated or demonstration data

- **The demo dataset is fictitious.** V1/V2 entities and deals come from the seed scripts. V2.1 figures (salaries, bank balances, cash movements, candidates, some messages) are stored with basis or source `simulated` and shown with a red **Simulé** badge.
- **Email sending is simulated.** An approved email is handed to a mock provider and labelled "envoi simulé". Nothing leaves the machine.
- **Website audits** run on a bundled demo site when no site is configured or reachable. Those runs are marked *simulated*.

### Integrations that are not connected

- **Email, calendar and website "connectors" are mock providers.** The ingestion path into the Data Core is real, but there is no OAuth and no Gmail, Outlook, Google Calendar, LinkedIn, Facebook or advertising account behind it. The UI shows these channels as *Démonstration* or *Non configuré*.
- **Functional mailboxes** (sales@, rfq@…) are a **classification of existing messages by displayed rules**, not real mailboxes. None is connected.
- **No bank connection, accounting ledger, tax computation, e-signature or CMS.** Website changes are approved, then applied manually.
- **Web sourcing** needs a Brave Search API key. Without it, runs are "partial" and use internal data only.

### Functional limits

- **No authentication.** The current user is selected with a profile switcher (an `X-User-Id` header). A request without that header runs in a legacy director mode. Permissions are enforced by the backend, but identity is **not verified**, so do not expose the app publicly beyond short supervised demos.
- **Single company.** The backend assumes one `Company` row (no multi-tenancy).
- **Marketing and campaign metrics** are mostly unavailable. There is no budget object and no link between inbound requests and a campaign, so ROI, cost per prospect and attribution are shown as "not available".
- **Reply and follow-up detection** relies on thread keys and contacts. Mailbox classification relies on keywords and links, so some messages (newsletters, spam) are classified as needing a reply.
- **No scheduler.** Follow-ups and observations are computed on read or on demand, and nothing is sent automatically.
- **Placeholder modules**: CRM, HR domain module, marketing, supply chain, reports, workflows and automations (see [Product tour](#product-tour)).
- **Interface language**: an FR/EN switch covers the interface chrome. Backend-generated content (explanations, drafts, labels) is French.
- **Valuation, fees, costs and projections are estimates** shown as ranges with their basis, never official figures.

## Documentation

- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md): V1 architecture, one section per layer.
- [`brain/architecture.md`](brain/architecture.md): V2 / V2.1 architecture and how new data feeds V1 intelligence.
- [`brain/decisions.md`](brain/decisions.md): the decision log, including rejected alternatives.
- Topic notes:
  - business model and transactions: [`brain/business_object_model.md`](brain/business_object_model.md), [`brain/transactional_model.md`](brain/transactional_model.md);
  - communications and permissions: [`brain/communications.md`](brain/communications.md), [`brain/permissions.md`](brain/permissions.md);
  - people and finance: [`brain/people.md`](brain/people.md), [`brain/director_finance.md`](brain/director_finance.md);
  - compliance, sourcing and website: [`brain/compliance.md`](brain/compliance.md), [`brain/sourcing.md`](brain/sourcing.md), [`brain/website_intelligence.md`](brain/website_intelligence.md);
  - design and navigation: [`brain/design.md`](brain/design.md), [`brain/navigation_v2.md`](brain/navigation_v2.md).
