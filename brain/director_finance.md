# Director finance — treasury, accounts, ownership, valuation (V2.1)

**Scope: a director view, not a bank, not accounting.** Director-only by
default (`view:treasury`, `view:ownership`). Every number is deterministic
and explainable; no LLM computes figures.

## Treasury

- `BankAccount`: current / savings / card / loan; balance at a date with its
  basis (declared, simulated…); **only a masked identifier** is stored
  (`FR76 •••• 0189`, `•••• 4242`) — full IBAN/card numbers are never stored.
- `CashMovement`: in/out, **actual / planned / estimated**, category (customer
  payment, supplier payment, salary, tax, loan, rent, other).
- Receivables/payables are **read from the commercial documents** (issued
  customer invoices, received/approved supplier invoices = declared; confirmed
  uninvoiced orders = estimated) — not copied.
- Projection at 30/60/90 days as a **range**: low = balance + planned +
  declared flows − estimated outflows; high = low + estimated inflows.

Cash below the declared minimum (`finance_settings.min_cash`) →
`CashForecastDeteriorated` + a company-level V1 Risk → V1 review Task
(idempotent).

## Ownership & valuation

Cap table from shares (percentages always computed), optional declared
economic rights (carry), link to an employee.

Valuation = **estimate range**: enterprise value = revenue 12 months ×
revenue multiple (declared by the director, else a generic SME benchmark
0.5–1.5×), adjusted for margin and growth; equity = EV + cash − debt − taxes
due. Inputs are listed with their basis; a declared valuation is shown
separately. "Une estimation, jamais une valeur officielle."

## Limits

No bank connection or import, no reconciliation, no accounting ledger, no
tax computation (taxes are planned movements), valuation is indicative only.
