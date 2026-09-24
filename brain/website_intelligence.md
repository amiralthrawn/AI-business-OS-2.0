# Website intelligence & AI optimisation (V2.1)

```
Current site → limited crawl → SEO analysis → issues (what / why / what to change)
→ proposed changes (before/after diff) → human approval (V1 HITL) → "ready to apply"
```

## Crawl

At most 20 same-domain pages, `robots.txt` respected (disallow → run fails),
stdlib HTML parsing, no JavaScript rendering. When no site is configured or it
cannot be reached, the audit runs on a **bundled demo site** and the run is
recorded and shown as **simulated**.

## Analysis

Per page: HTTP errors, title missing/short/long/duplicated, meta description
missing/short, H1 missing/multiple, images without alt, missing `lang`, thin
content, slow response. Each issue: severity, what, why it matters, what to
change. No single "SEO score".

## Proposals

Deterministic, from the page's own content (H1/title + company name; meta
description template; single H1), optionally rephrased by an LLM without new
facts. Shown as a diff. "Soumettre à validation" creates a HITL Task (domain
`website`, director approval). **Approval never modifies the real site** — there
is no CMS connector; the proposal becomes "approved — to apply manually".

## AI activity

Each run stores its real steps (`AIRun.steps`) with status and detail; the UI
renders them ("✓ 5 pages analysées", "– Aucun site configuré") and the mode
badge (real / simulated / partial). No fake progress.

## Limits

No Core Web Vitals, no keyword ranking data, no backlinks, no content
generation beyond metadata, no CMS integration.
