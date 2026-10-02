# Orders, payments, deliveries and credit notes (V2.2)

Backend `app/billing/` (service + router), migration `d1688efa5611`, demo
`data/seed_v22.py`, tests `tests/test_v22_billing.py`, `tests/test_v22_seed.py`.
No new navigation entry: everything lives on the objects it concerns.

## One source of truth, derived views

| Fact | Stored as | Never |
|---|---|---|
| What is owed | the **invoice** (`CommercialDocument`, lines) | a typed "amount due" |
| Its due dates | `payment_installments` (free terms per invoice; none = one payment at `due_at`) | a rule like "3 instalments" |
| A payment | a real `CashMovement` (`status="actual"`, `document_id` = invoice) | a status ticked by hand |
| A payment not yet matched | a `CashMovement` with `customer_id`/`supplier_id` and no document ("à rapprocher") | silently assigned |
| A credit note's effect | its single `credit_applications` row (unique per credit note) | deducted at creation or at acceptance |
| A refund | a `CashMovement` out, category `customer_refund`, `document_id` = credit note | assumed |

Derived at read time (`settlement`, `party_account`, `order_payment`,
`fulfilment`, `billing_overview`): remaining, overdue, instalments paid,
next due date, invoice state, customer/supplier balance, delivery progress.
The customer page, the order, Finance and the Centre de contrôle all call the
same functions, so they cannot disagree.

**Balance** = invoices issued − payments received − credit notes imputed
+ refunds paid. Checked invariant (tests): balance = outstanding on invoices −
unallocated payments − credit kept on the account − refunds owed.

## Statuses that follow facts

- Customer invoice: `issued → partially_paid → paid`; supplier invoice:
  `approved → partially_paid → paid`. Set **only** by recorded payments or an
  imputed credit note (`SYSTEM_STATUSES`, refused by the status API). A
  supplier invoice is paid only once approved.
- Customer order: `draft → sent` ("Transmise au client") `→ acknowledged`
  ("Réception accusée par le client") `→ confirmed`. Each is recorded by a
  person (buttons say "Enregistrer l'accusé de réception du client"); the
  historical `draft → confirmed` path remains. Sending the "order
  confirmation" email (HITL) marks the order transmitted, never acknowledged.
  Only `confirmed` posts revenue.

## Credit notes

Customer (`AV`): `draft (Préparé) → submitted (Soumis — en attente de
réponse) → accepted | rejected | draft (modification demandée) → validated →
applied (Imputé) → refunded`.

- **Acceptance never moves a balance.** It publishes `CreditNoteAccepted` and
  creates a `PENDING_VALIDATION` Task (`validate_credit_note`, domain
  `finance` → director approval by default). The executor sets `validated`.
- **Imputation** (write:finance) happens once: reduces what is still owed on
  the corrected invoice; any excess (the invoice was already paid) becomes a
  refund owed; with no invoice yet, the whole credit stays on the account.
- **Refund** is recorded when the transfer was really made (no bank link).
- **Refusal** publishes `CreditNoteRejected` and opens a decision Task.
- Drawn from a delivery with recorded non-conformities, a credit note takes
  only the non-conforming quantities (prices from the order).

Supplier (`AVF`, our claim): `requested → confirmed | rejected → applied`
(reduces what we owe on their invoice). The supplier's answer is recorded by
a person; the claim email is a draft sent only after validation.

## Deliveries and non-conformities

`fulfilment(order)`: ordered / shipped / delivered-received / in transit /
remaining per line, from the order's deliveries/receptions **statuses only**;
planned vs actual dates, delay, carrier and tracking number (new document
fields), non-conforming quantities (new line fields). A non-conformity is
reported on a delivered delivery / received reception (write:operations): it
opens one V1 Risk per document, whose RiskCreated reaction creates the review
Task.

## Communications, notifications

New draft purposes: `credit_note_offer`, `supplier_claim`,
`payment_reminder` (templates, HITL send, "envoi simulé" with the mock
provider). Events (`PaymentRecorded`, `CreditNote*`,
`NonConformityReported`, `CustomerOrderAcknowledged`, …) feed the object
timelines; Tasks surface in Actions & validations and the Centre de
contrôle. **No external notification is sent**: none is claimed.

## Permissions

Record/allocate a payment, set a schedule, impute, record a refund:
`write:finance`. Report a non-conformity: `write:operations`. Record the
customer's answer, request validation: `write:sales`. Validate: HITL
approval, finance domain (director). Customer account: `view:sales` or
`view:finance`; supplier account: `view:procurement` or `view:finance`.

## À confirmer avec le comptable

Nothing below is coded as a rule; the product records operations and lets
references be attached.

1. **Plan de comptes**: 411 (clients), 401 (fournisseurs), 512 (banque),
   601 (achats), 706 (ventes) are shown as *examples* until configured
   (`finance_settings.accounting_refs`). Sub-accounts per customer (411XXX)?
2. **TVA**: amounts are HT; no VAT on invoices, credit notes or refunds.
3. **Avoir comptable**: is an accepted commercial credit note always a
   formal "facture d'avoir" (numbering, mentions légales)? Imputation on a
   specific invoice vs on the account balance?
4. **Acomptes**: deposit = instalment of the final invoice (current model) or
   a separate "facture d'acompte"?
5. **Écarts de règlement** (small differences, bank fees, currency) and
   **créances douteuses**: not modelled.
6. **Date d'effet** of a credit note for the books: acceptance, validation
   or imputation date?
7. **Rapprochement bancaire**: payments are declared; no bank import.

## Limits

One payment → one invoice (no split across invoices); no partial reversal of
a payment; supplier refunds (money back from a supplier) not modelled;
timeline dates of replayed demo events are the seeding time; no ledger,
journal or FEC export.
