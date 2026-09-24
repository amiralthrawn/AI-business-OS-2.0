# Design rules (V2 / V2.1)

The V1 visual language is kept as is (Fraunces / Plus Jakarta Sans / IBM
Plex Mono, light theme, tokens in `app/globals.css`, `components/ui/*`). V2
adds no new visual style — only reusable object components.

## Object page pattern (`components/objects/*`)

1. `ObjectBreadcrumb` — section, then the deal chain.
2. Header — kind, number/name, status badge, linked party.
3. `ObjectActions` — actions from the contextual API; forbidden ones stay
   visible, disabled, with their reason.
4. Content sections — lines, margin, benchmark, sourcing, cost, contribution…
5. `ObjectSignals` — open risks/opportunities on the object or what it involves.
6. `RelatedObjects` — every related object as a link.
7. `ObjectAskAI` — questions sent with the object as context.
8. `ObjectTimeline` — the object's history.

## Honesty in the UI

- `BasisBadge` next to every uncertain value: Réel / Déclaré / Estimé /
  Référence marché / **Simulé** (red) / Inconnu, with a tooltip.
- Ranges rendered as ranges (`fmtMoneyRange`, `fmtDaysRange`), never midpoints.
- Margins say "réelle" only when all costs are observed.
- AI work shows real steps and a mode badge (`AIRunSteps`).
- Everything external or sensitive says "brouillon", "à valider", "envoi
  simulé", "à appliquer manuellement" rather than implying it happened.

## Typography of numbers (UX pass)

Titles stay in Fraunces, interface text in Plus Jakarta Sans. **Every number
is set in IBM Plex Mono with tabular figures**, through three central
classes in `app/globals.css` (`@layer components`, so Tailwind colour and
weight utilities still win):

- `.font-mono` / `.num` — an inline value (amount, %, date shown as data,
  quantity, counter, table cell);
- `.figure` — a headline indicator (StatCard, director cards, margin).

`body` also enables `tabular-nums`. Headline figures no longer use the
italic display font.

## Charts (UX pass)

Reusable client components in `components/ui/`:

- `Sparkline` — mini-curve under an indicator; hover shows the period, the
  value and what is summed; draws in on mount.
- `RangeBars` — low→high ranges on one scale with a reference line (treasury
  projection vs declared minimum cash). Ranges are never collapsed.
- `Donut` — a real distribution only (cap table); hover highlights a slice.
- `MonthlyLineChart` (existing) — axis labels now in mono.

Rules: **never simulate a series.** `lib/series.ts` drops the months before
the first recorded transaction (absence of data is not a zero), marks the
current month as partial, and returns nothing below 3 real months; the card
then says "Historique mensuel insuffisant". Month-over-month badges only
compare two complete months that both have transactions (the old hard-coded
"En hausse" / "Actif" badges were removed). The margin card has no curve
because no monthly margin series exists. All animations are disabled by
`prefers-reduced-motion` (globals.css).
