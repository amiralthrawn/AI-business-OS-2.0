# Transactional model (V2)

## Documents

One table, `commercial_documents`, discriminated by `kind` (decision #30).
Lifecycle, prefixes and derivations live in `app/transactions/lifecycle.py`
(also served by `GET /documents/meta`).

| Kind | Prefix | Statuses |
|---|---|---|
| customer_request | DEM | new → qualifying → quoting → negotiating → won / lost |
| customer_quote | DEV | draft → sent → accepted / rejected / expired |
| customer_order | CMD | draft → (sent → acknowledged →) confirmed → delivered → invoiced → closed (or cancelled) |
| customer_delivery | LIV | planned → shipped → delivered |
| customer_invoice | FAC | draft → issued → partially_paid → paid (settlement statuses set by payments, V2.2) |
| purchase_request | DA | draft → consulting → comparing → decided → ordered |
| supplier_quote | DFO | requested → received → selected / declined |
| purchase_order | BC | draft → sent → confirmed → received → closed |
| reception | REC | expected → received |
| supplier_invoice | FFO | received → approved → partially_paid → paid (disputed); paid set by payments |
| customer_credit_note | AV | draft → submitted → accepted / rejected → validated (HITL) → applied → refunded |
| supplier_credit_note | AVF | requested → confirmed / rejected → applied |

Numbers: `PREFIX-YYYY-NNNN`, per company/kind/year. `external_reference` keeps
the other party's number; `issued_at`, `due_at` (promise), `completed_at`
(what really happened), `follow_up_at`.

**Derivation** (`derive_document`) copies parties and lines and records a
`derived_from` link; prices are copied only within the same party's flow
(quote → order, supplier quote → PO). Obvious status consequences are applied
only when they are valid transitions (quote accepted → request won; PO created →
purchase request walks consulting → comparing → decided → ordered).

V2.2 (`brain/billing.md`): payments, instalments, balances, credit notes and
delivery follow-up are derived from invoices, `CashMovement`s and
`credit_applications`; statuses that follow a recorded fact are in
`SYSTEM_STATUSES` and cannot be set through the status API.

## Ledger posting (V2 → V1 intelligence)

| Event | Ledger effect |
|---|---|
| customer order confirmed | one SALES_ORDER fact per product line |
| reception received | one PURCHASE_ORDER fact per line, `occurred_at` = real date, `expected_at` = PO promise (feeds V1 delivery performance) |
| supplier invoice approved | the reception facts are revalued at the invoiced (OBSERVED) price; supplier terms updated; increase vs reference cost → V1 Risk path |
| customer invoice paid | the order's facts become PAID |
| order cancelled | its facts become CANCELLED |

A supplier invoice is **not** posted as a separate INVOICE fact: V1 sums
PURCHASE_ORDER + INVOICE as costs, which would count a purchase twice (#31).

## Margin

`app/transactions/margin.py` walks the deal and prices each line's cost from
the best source: actual (approved invoice, OBSERVED) > committed (PO) >
quoted (supplier quote) > catalog (ProductSupplier) > reference (estimated) >
unknown. Two views: **planned** (the cost frozen on the sales line when it was
priced, #36) and **current**. Cost items (transport…) are ranges; observed ones
replace estimates of the same kind. The margin is "actual" only when every cost
is observed; "incomplete" when a cost is unknown. Variances explain the gap.

## Stock

Three kinds (physical, supplier, potential), never summed, each with basis,
date and source; CSV import upserts on (product, kind, supplier, location).

## Limits

Float money (move to Numeric with the Postgres migration), number sequence
from max() (fine under SQLite's single writer), no partial deliveries/
receptions per line quantity, no multi-currency conversion, cost allocation
between several orders of one deal by revenue share only.
