# Compliance & outside experts (V2.1)

**Not a legal module.** Built from existing objects:

- a compliance matter is a **Task** (`domain = compliance`, `category`, `due_at`)
  linked to the documents/emails it concerns (object graph);
- an outside expert (law firm, accounting firm, insurance advisor, expert) is a
  **Supplier** (`supplier_kind`, declared hourly fee range) with a Contact.

```
Compliance request → analysis → recommendation → action (draft request email, HITL)
```

Categories: contract_review, nda, legal_request, regulatory,
accounting_request, insurance, renewal, other. The recommendation says which
expertise is needed ("Cette demande semble nécessiter…"), lists matching
experts and estimates fees = benchmark hours for the category × the expert's
declared rate (or a market benchmark when none) — a range with basis and
confidence, "estimation, pas un devis". "Préparer la demande d'intervention"
creates a draft email linked to the task; **nothing is ordered or paid**.

View: Actions → Conformité & juridique (`view:compliance`). Approvals in the
compliance domain are director-only.

## Limits

No document analysis of contracts, no legal knowledge base, no e-signature,
no engagement letters or invoicing of experts.
