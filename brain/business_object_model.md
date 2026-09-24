# Business Object Model (V2 / V2.1)

## Objects

| Object | Table | Notes |
|---|---|---|
| Company | `companies` | single company in this MVP (`app/core/tenancy.py`) |
| Customer (incl. prospect) | `customers` | `status`: prospect / active / inactive — a prospect is not a separate entity |
| Supplier (incl. outside expert) | `suppliers` | `supplier_kind`: goods / law_firm / accounting_firm / insurance_advisor / expert |
| Contact | `contacts` | a person at a customer/supplier (V1 LinkableMixin), or unresolved |
| Product | `products` | **central object**: preferred supplier (V1 `supplier_id`), list price, reference cost (estimate) |
| ProductSupplier | `product_suppliers` | every supplier able to provide a product, with terms and bases |
| StockPosition | `stock_positions` | physical / supplier / potential — never summed |
| CommercialDocument (+ lines, cost items) | `commercial_documents` … | request, quote, order, delivery, invoice (customer side); purchase request, supplier quote, PO, reception, invoice (supplier side) |
| Transaction | `transactions` | ledger fact; `source_document_id/line_id` when posted by a document |
| Communication | `communications` | email / website / calendar; drafts too (`status`), `contact_id`, `thread_key` |
| Document (file) | `documents` | attachments |
| Task | `tasks` | human task or HITL proposal (`pending_action`, `action_payload`); `assignee_employee_id`, `category`, `due_at` (V2.1) |
| Risk, Opportunity | V1 | intelligence results, linkable to any object |
| UserProfile | `users` | a person using the OS: role + custom access |
| Employee (+ cost items) | `employees` | a person working for the company; `user_id` links to their profile |
| SkillNeed, Candidate | V2.1 | declared needs; applicants (usually from an email) |
| BankAccount, CashMovement, Shareholder | V2.1 | director finance |
| SourcingLead, AIRun, WebsiteChangeProposal | V2.1 | AI work with provenance and visible steps |

## Relations (one read model)

`app/objects/graph.py` answers "what is this related to?" for every type,
whatever the storage:

1. **Foreign keys** — a document's customer/supplier/contact, a line's product,
   a posted transaction's source document, product ↔ suppliers, employee ↔ tasks.
2. **V1 LinkableMixin** — Task/Risk/Opportunity/Contact/Communication/file → one object.
3. **ObjectLink** — typed many-to-many: `derived_from` (document chain),
   `concerns` (email ↔ quote, task ↔ order, email ↔ candidate), `mentions`, `attachment`.

```
Customer ─ Contact ─ Email ─ Quote ─ Order ─ Product ─ Supplier
   │                  │        │       │        │         │
Customer request ── Purchase request ── Supplier quotes ── PO ── Reception ── Supplier invoice
                                                         (cost items: transport…)
Order ──posts──▶ Transaction ◀──posts── Reception       Invoice ──revalues──▶ Transaction
Employee ─ Tasks ─ owned deals (via UserProfile) ─ cost items
Compliance Task ─ documents / emails / expert (Supplier)
```

A **customer request is the root of a deal ("affaire")**: quotes and purchase
requests derive from it, so the whole chain request → … → supplier invoice is
one connected component of `derived_from` links (`document_chain`).

## Integrity

ObjectLink and LinkableMixin are application-level references (no multi-table
FK): creation goes through `app.objects.links.create_link` (both ends must
exist, same company, idempotent). A dangling pointer is skipped when
displayed, never fatal.

## Value basis

Every uncertain value carries its `ValueBasis`: observed / declared /
estimated / benchmark / simulated / unknown (+ a confidence where relevant).
Ranges stay ranges (`min`/`max`), never collapsed to a midpoint.
