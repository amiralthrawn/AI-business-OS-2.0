# AI sourcing (V2.1)

```
Purchase request → sourcing run (visible steps, AIRun) → leads with provenance
→ human converts a lead → Supplier + supplier-quote request derived from the PR
→ the existing benchmark compares it → RFQ email (HITL) → PO
```

## Rules

- **Never invent a supplier or a price.** Leads come from (1) suppliers the
  company already knows but has not consulted for this product, (2) real web
  search results with their URL, (3) manual entries with a source.
- A price is recorded only when the source's own text states it (DECLARED by
  that source); otherwise UNKNOWN.
- Web search runs only if `BRAVE_SEARCH_API_KEY` is configured; without it the
  run is "partial" and says so; a failed search is reported, not hidden.
- No crawler, no scraping of supplier sites, no permanent job.

A stated price ≥ 10 % under the best known price creates an Opportunity on
the product ("Source moins chère possible…"), unverified until a real quote.

## Limits

One product line per run, no deduplication across web domains beyond name,
facts beyond price (MOQ, lead time, certifications) come from the converted
supplier's quote, not from web text parsing.
