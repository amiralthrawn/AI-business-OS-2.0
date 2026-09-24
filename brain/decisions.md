# Step 12 — Architectural decisions

## 1. Scope: Finance + Procurement + Sales/CRM only, not all 7 domains

The step-12 brief lists Finance, Procurement, Sales/CRM, Products, Supply
Chain, HR, Marketing and External Intelligence as areas the OS should
eventually understand. Building real analytical depth for all seven in one
step would have meant either superficial coverage everywhere or an
unreviewable amount of change. I chose depth over breadth: Finance,
Procurement and Sales/CRM get real entities, real trend computation and real
detection rules; HR, Marketing and Supply Chain remain the structural
placeholders they already were (no `Employee` entity exists, and none was
added). This means "should we hire?" and "should we diversify our supply
chain?" are not yet answerable with real data — that is an explicit,
documented gap, not an oversight. The architecture (Data Core → Business →
Intelligence → AI) does not need to change to add HR/Marketing depth later;
it only needs more entities, more seed data, and more capabilities in the same
shape as the ones added here.

## 2. The Orchestrator no longer gates all capability access behind one Agent

Through step 11, `AIOrchestrator.ask()` picked exactly one Agent and only ever
called that Agent's capabilities. Step 12 required genuine cross-domain
reasoning ("why is margin declining?" needs Finance, Procurement and Sales at
once), which that design could not produce without breaking the "Agent
declares which capabilities may run" invariant.

The fix keeps that invariant but removes the "exactly one Agent" restriction:
`_match_agents_for_topics` returns a *set* of Agents (topic keywords map to one
or more Agent names; the "margin" topic explicitly maps to all three), and the
Orchestrator calls the union of their capabilities against whatever
Supplier/Product/Customer it resolved from the question. A capability is still
only ever invoked because *some* Agent declares it — there is no path for the
Orchestrator to call an undeclared capability. Single-topic questions
("What is our supplier for X?") still only touch one Agent, unchanged from
before; this only added a path for genuinely multi-domain questions.

The `agent` field in `AskAIResponse` became a comma-joined list when more than
one Agent contributed (`"finance, procurement, sales"`), instead of always a
single name. This is a legitimate, documented API contract change — the
affected existing tests were updated to check membership rather than exact
equality, the same way earlier steps updated tests for legitimate contract
changes.

## 3. `ActionsService.create_task_from_risk_created`'s title bug

Building the new monitoring rules exposed a real bug in existing code: this
method (from step 7) hardcoded the Task title as `"Review supplier cost
increase"`, which was accurate when `RiskCreated` could only mean one thing.
Once margin, supplier-performance and customer-decline Risks started
publishing the same `RiskCreated` event, every Task this handler produced was
mislabeled except the original cost-increase case. Fixed to derive the title
from the actual Risk (`f"Review: {risk.title}"`). One existing test asserted
the old literal string and was updated to match the corrected, general
behavior — this is a bug fix surfaced by richer data, not a step-12 feature
change.

## 4. Shared `app/core/analytics.py` instead of duplicating trend logic

Both Intelligence's monitoring rules and the AI layer's on-demand analysis
capabilities need identical numbers for "is this supplier's delivery
performance degrading?" and equivalents for customer value and margin. Rather
than let a proactive rule and an AI capability quietly compute this
differently over time, the arithmetic lives once in `app/core/analytics.py`
as plain functions with no side effects, imported by both call sites.

## 5. Monitoring is a manual sweep, not a scheduler

`POST /intelligence/monitor` runs every rule against every relevant entity
once, on demand — called at seed time and available as an endpoint. No
Celery/Redis/cron was introduced, per the explicit constraint against new
infrastructure. This is the clearest carried-forward production gap: a real
deployment needs a scheduler to run this periodically, which is listed as a
next bottleneck rather than solved here.

## 6. Home's "AI Priorities" reuses `HomeService`, not a new AI-side query

`list_priorities` (the AI capability behind "what deserves my attention?")
calls `HomeService.get_priorities()` directly rather than re-querying Risks
and Opportunities itself. "What deserves attention" must mean the same thing
whether a human opens Home or asks the AI; keeping one ranking implementation
was preferred over two that could drift apart.

## 7. `Task.pending_action` / `Task.correlation_id` distinguish the two Task-producing flows

Both the Risk→Task reactive flow (step 7) and the AI action-proposal flow
(steps 10–11) can produce a Task in `PENDING_VALIDATION`. Only the latter is
eligible for `/approve` and `/reject`: `get_pending_proposal` requires
`pending_action` to be set, which the Risk→Task flow never sets. The frontend
detail views apply the same filter before showing Approve/Reject controls, so
a reactive review-only Task never presents a button that would just fail.

## 8. Baseline observed_value is the historical half, not the recent half — caught by a test

The first draft of `app.core.baseline`'s three metric-specific builders
(`margin_baseline`, `supplier_delivery_baseline`, `customer_value_baseline`)
set `observed_value` to the *recent* trend value instead of the *historical*
one, which would have made a Baseline compare "now" against "now" instead of
against "before". `test_supplier_delivery_baseline_reflects_real_history`
caught it immediately (asserted the wrong number, forcing a re-check of what
each field should mean) before it reached Significance or the Snapshot. Fixed
by having the three builders return `(Baseline, current_value)` as an
explicit pair, rather than trying to fold "what's normal" and "what's
happening now" into one object.

## 9. Significance thresholds duplicate, rather than import, the existing Risk severity thresholds

`app/snapshot/service.py` hardcodes its own impact thresholds
(`_MARGIN_IMPACT_THRESHOLDS` etc.) instead of importing the ones already used
in `app.intelligence.risks.service`'s four detection rules. The two aren't
computing the same thing (Significance classifies a deviation from a
Baseline's reference value; the existing rules classify an absolute recent
value or a point_change), so unifying them isn't a one-line import — it would
mean refactoring the four detection rules to compute and expose a Baseline
too. Deferred on purpose: this step's job was to introduce Baseline/
Significance/Snapshot without touching the twelve passing tests around
stable detection code from steps 6–12. Documented in `brain/business_state.md`
as a named, intentional next refactor rather than an inconsistency to fix
silently later.

## 10. The Business State Snapshot enriches existing Risks/Opportunities; it does not re-scan every entity

`build_snapshot` builds one `SnapshotArea` per currently OPEN Risk/Opportunity
(annotating each with Baseline + Significance), rather than proactively
computing Baseline/Significance for every Supplier/Product/Customer in the
Data Core regardless of whether Intelligence flagged anything. This keeps the
Snapshot cheap and honestly scoped as "a derived view of what's already been
found", per the explicit instruction that it must not become a second
monitoring engine or a second Data Core. The tradeoff: a "why is nothing
wrong with X" question, or a fully proactive scan independent of existing
Risks, isn't answerable from the Snapshot as built — noted as a limitation,
not solved here.

## 11. The Observation Engine stops at "ObservationDetected"; it does not create Risks/Opportunities itself

The Business Observation Engine (`app/observation`) publishes a
`BusinessEvent` the moment an Observable's deviation is material, and stops
there. It does not call into `app.intelligence.risks.service` or
`app.intelligence.opportunities` to promote that event into an actual
Risk/Opportunity, even though today's three registered Observables (margin,
delivery delay, customer revenue variation) overlap exactly with what those
older, per-metric rules already detect. This was a deliberate scope cut: the
target architecture diagram itself places Business Event → Risk/Opportunity/
Insight as a separate, later interpretation step, and collapsing "detection"
and "interpretation" into one change would have meant either duplicating the
existing detection rules' logic inside the generic engine (defeating the
point of making it generic) or replacing them outright (a much larger,
riskier change than this step asked for). The practical effect, visible in
the real seeded dataset: every current anomaly still reaches Home/the
Snapshot via the pre-existing Risk/Opportunity path, and the new
`ObservationDetected` events for the same entities are treated as already
covered (`kind="risk"`, not `"observation"`, per decision-relevant test
`test_snapshot_does_not_duplicate_an_observation_already_covered_by_a_risk`).
The `kind="observation"` Snapshot path exists and is tested precisely so a
*future* Observable — one with no hand-written detection rule yet — can reach
the Snapshot immediately upon registration, without waiting for someone to
also write a dedicated Risk rule for it. Documented in
`brain/observation_engine.md`.

## 12. Cross-domain correlation follows exactly one real edge (Product ↔ its own Supplier), not a general graph search

`_correlate` in `app/observation/engine.py` merges an anomalous Product
Observation with an anomalous Observation on that Product's own Supplier
(via `product.supplier_id`) into a single Business Event, and nothing more
general. A real graph-based correlation (any entity linked to any other
entity with a concurrent anomaly) was judged out of scope for this MVP's "one
real link, not a framework" instruction — the one edge implemented is the
exact cross-domain example given in the brief (supplier cost/delivery trouble
showing up as a product's margin problem), proven by a passing test
(`test_sweep_correlates_a_products_margin_issue_with_its_own_supplier`), but
the seeded demo dataset doesn't happen to trigger it (its two engineered
anomaly chains use different supplier/product pairs by original step-12
design) — so this mechanism is verified by the unit test, not by the demo
run. Widening correlation to a general graph traversal is future work, noted
rather than attempted, to avoid building unused generality now.

## 13. Interpretation classification (risk/opportunity/insight/observation) is a deterministic rule, not an LLM decision

The brief for the Interpretation layer asks the LLM to handle "l'interprétation
et le raisonnement business." I read that as the free-text explanation, not
the type classification itself, and made `app.interpretation.engine.classify`
a small, generic, auditable function of Significance fields already computed
by the Observation Engine (Baseline confidence + a per-metric direction
lookup), never a call to the LLM. Two reasons drove this: first, consistency
— every other classification in this codebase (`Significance.is_material`,
`_classify_impact`, `_classify_urgency`) is already a readable rule rather
than a black box, so extending that same philosophy to the risk/opportunity/
insight call is the more consistent reading of "Business Event reste factuel
et déterministe," not a departure from it. Second, and more practically:
`DeterministicLLMClient` (the no-API-key fallback used throughout this
project's test suite) is a plain prompt echo — it cannot reliably produce a
parseable classification, and making classification depend on real LLM
output would have made the three required MVP demonstrations (Risk /
Opportunity / Insight from the seeded data) non-reproducible without a live
OpenAI key. The LLM's role stayed confined to `explanation`: it never
touches the Data Core, a Baseline, an Observation, or the type/confidence
fields. Documented in `brain/interpretation_engine.md`.

## 14. Interpretation is additive; only the Action Proposal step is deduplicated against existing Risks/Opportunities

An `EventInterpreted` Business Event is produced for every anomalous
Observation regardless of whether an open Risk/Opportunity already exists
for that entity from the older per-metric rules — the Interpretation's
narrative and classification are informational value on their own, even when
a Risk already exists. Only the side-effecting step (proposing a Task via
`ActionsService.propose_task`) is guarded by
`_already_covered_by_existing_flow`, skipping it when an open Risk/
Opportunity already covers the entity. This is why the seeded demo's own
`actions_proposed` count is 0 for its four pre-existing anomalies (each
already has a Risk/Opportunity, most already have a Task too) and only the
one genuinely new entity added for this step (Coastal Metal Supply,
classified as `insight`, which never proposes an action by design) exists to
demonstrate the third MVP case. The Action Proposal → Human Validation
mechanics themselves are proven by dedicated unit tests against an isolated
scenario with no pre-existing Risk, not by the seeded demo run — the same
"proven by unit test, not by the demo run" honesty already established for
the Observation Engine's own cross-domain correlation (decision #12).

## 15. A new seed entity (Coastal Metal Supply) was added specifically to demonstrate the Insight case

The brief permitted adding seed data "si un troisième cas manque réellement."
With the existing seed dataset, every anomaly the Observation Engine finds
overlaps with an entity the older per-metric rules already classify with
enough confidence to become a Risk or Opportunity — there was no case where
the data was genuinely too thin or unclear to justify a confident
classification, i.e. no natural Insight demonstration. A brand-new supplier
(Chain 4: 3 purchase orders, all badly late, no declared delivery-performance
target) was added specifically because 3 data points is below the `_split_in_half`
threshold (4) that makes a historical baseline computable at all, so its
Baseline falls back to a generic benchmark at `confidence="low"` — a
deliberately realistic "too new to judge yet" scenario, not an artificial
one. `declared_baselines` also gained a `customer_revenue_variation_pct`
entry (±5% considered normal) so that the pre-existing customer growth/
decline observations reach `confidence="high"` and correctly demonstrate the
Risk and Opportunity cases rather than falling to `insight` themselves (a
customer's revenue variation has no observed-history baseline by design,
see `app/core/baseline.py`'s `customer_value_baseline`, so without a declared
target its confidence would always be "low"). Both additions are consistent
with the existing seed's own principle of replaying real pipelines over real
data rather than inserting demo state directly.

## 16. Action Proposal moved from Interpretation to Decision Intelligence

Step 16 (`app.interpretation.engine`) originally proposed a Task itself for
any confident risk/opportunity Interpretation, via `_maybe_propose_action`.
Step 17's own target diagram places Action Proposal *after* Decision
Intelligence, not directly after Interpretation
(`Interpretation → Decision Intelligence → Recommendation → Action Proposal
→ Human Validation`), and its brief states explicitly that "une Decision
peut exister sans Action" and "une Recommendation peut exister sans qu'une
Action soit proposée" — meaning the Action Proposal should be conditioned on
a Decision's own recommendation, not on the raw Interpretation type. Rather
than leave two independent places that could each propose a Task for the
same entity (a real duplication risk for any future risk/opportunity not
already covered by the older per-metric flow), I moved
`_maybe_propose_action` and its `_already_covered_by_existing_flow` dedup
guard from `app.interpretation.engine` to `app.decision.engine`, and
`run_interpretation_sweep` now only publishes `EventInterpreted` (its return
dict lost the `actions_proposed` key). This is a deliberate, surgical
relocation, not a rewrite of Interpretation's own classification or
explanation logic (`classify`, `_explain`, `interpret_event` are all
unchanged) — three of last step's tests
(`test_run_interpretation_sweep_interprets_and_proposes_a_pending_task_only`,
`test_no_duplicate_action_when_entity_already_has_an_open_risk`,
`test_proposed_task_can_be_approved_through_the_existing_action_executor`)
were adapted or moved to `tests/test_decision_engine.py` accordingly.
Documented in `brain/decision_intelligence.md`.

## 17. Decision options are a small, generic, per-domain lookup, and the recommendation is deterministic

`app.decision.engine._RISK_OPTIONS`/`_OPPORTUNITY_OPTIONS` hold exactly three
options per (decision type, domain) for the three domains this project has
had since step 12 (finance/procurement/sales), each domain's own list always
shaped as two proactive options followed by one passive one. The
recommendation always combines the two proactive options
(`f"{options[0].label} + {options[1].label}"`) — a deterministic rule, for
the exact same reason `app.interpretation.engine.classify()` is
deterministic rather than LLM-decided (decision #13): `DeterministicLLMClient`
cannot reliably choose among options, and the three required MVP
demonstrations need to be reproducible without a live OpenAI key. This
mirrors the brief's own worked example precisely ("Investigate renegotiation
+ alternative supplier", skipping "absorb the cost temporarily") and keeps
the LLM's role confined to `reasoning` — explaining *why* that combination
makes sense, never choosing a different one. A domain outside these three
falls back to the `finance` catalog entry (the most generic) rather than
raising, so the engine degrades gracefully rather than failing for a future
domain that doesn't yet have its own option catalog. Documented in
`brain/decision_intelligence.md`.

## 18. Cross-domain questions with no named entity get their own scratch context per area, instead of changing `_call`'s shared cache

`AIOrchestrator._call`'s cache is keyed by capability name alone (`if name
in capabilities_used: return context[name]`), which was always correct
because every path before step 18 resolves at most one entity per request.
The new `_handle_cross_domain_request` (for a question like "Why is our
margin declining?" that names no specific Supplier/Product/Customer) can
legitimately need the same capability for several different entities across
multiple significant Snapshot areas in one request — reusing the shared
cache as-is would have silently returned the first entity's cached result
for every subsequent area needing the same capability, a real correctness
bug for genuine multi-entity aggregation. Rather than changing `_call`'s
cache key (touching a function every other, already-tested path in this
file depends on), each area gets its own scratch `area_context`/
`area_capabilities` dict passed into the existing, unmodified
`_dispatch_targeted_capabilities`, then merged into the outer context under
a namespaced key (`"{domain}: {title}"`) afterward. This keeps `_call` and
`_dispatch_targeted_capabilities` completely untouched, confines the new
complexity entirely to the one new method, and is verified by
`test_cross_domain_question_aggregates_two_distinct_domains_and_entities`
(two real, unrelated Risks in two different domains, both entities' data
intact in the same response, under separate keys). Documented in
`brain/ai_orchestrator_cross_domain.md`.

## 19. Home's new "AI Priorities" coexists with, rather than replaces, the older `get_priorities`; `GET /home` stays the one Command Center endpoint

Step 19 needed Home's "AI Priorities" section to show risk/opportunity/
decision/insight areas with real Significance dimensions -- data that only
`build_snapshot(...).material_areas` has, not the older
`HomeService.get_priorities()` (severity-only, Risk/Opportunity rows only,
still used unmodified by the `list_priorities` AI capability since step 9).
Rather than rewrite `get_priorities()` to match the richer shape (risking
`list_priorities`'s own prompt/tests, which have depended on its exact,
simpler shape for several steps) or delete it in favor of one "true"
priorities method, I added a separate `get_ai_priorities(company_id)` that
wraps `build_snapshot` directly, and left `get_priorities()` untouched. The
two intentionally return different shapes for different consumers rather
than one trying to serve both. Related, smaller choices made the same way:
`GET /home` was kept as the one Command Center endpoint (its service method
was renamed from `get_command_center_view` to `get_command_center` and
enriched in place) rather than adding a second `/home/command-center` route
the brief's own conceptual example suggested; and linking an "AI Priority"
back to its Risk/Opportunity detail page was done by cross-referencing the
already-open Risk/Opportunity rows by `(entity_type, entity_id)` rather than
adding a new field to `SnapshotArea` (which would have touched three prior
steps' worth of Snapshot tests for a Home-only concern). Documented in
`brain/home_command_center.md`.

## 20. `EventLogEntry` keeps its per-event-type payload convention; no structured entity-link column was added

Step 20's Data Core audit found a real inconsistency: `EventLogEntry` has no
structured `related_entity_type`/`related_entity_id` column (unlike every
other Business/Intelligence entity, which all use `LinkableMixin`), so every
event type names its subject with whatever payload field makes sense for it
(`entity_id` for Observation/Interpretation/Decision events, `supplier_id`/
`product_id` for the reactive Procurement event, `related_entity_id` for
Task/Action events). Closing this properly would have meant adding the two
columns (a migration), extending `BusinessEvent` with matching optional
fields, and updating every existing publisher across Observation,
Interpretation, Decision, Intelligence and Actions to set them — real
surgery across five modules this step's brief explicitly said not to modify
unnecessarily, for a problem no current consumer is actually blocked by:
every place that needs "events about entity X" already has a working query
(`_recurrence_count`, `_already_interpreted`, `_already_decided`). Instead,
`app.core.entity_context.get_entity_context`'s own event lookup reuses the
exact same "scan payload values for a matching id string" pattern
`app.snapshot.service._recurrence_count` already established, and the
inconsistency is documented rather than silently left undiscovered. If a
future step needs reliable, indexed entity-scoped event queries at a scale
where the payload scan stops being "acceptable" (per every prior step's own
admission of this same limitation), that is the point to revisit this
decision — not before. Documented in `brain/data_core.md`.

## 21. Ingested external data lands on `Communication`/`Document`/`Contact`, not a new entity; identity resolution never creates a Supplier, Customer or Opportunity

Step 21's External Connectivity Layer needed somewhere in the Data Core to
put an imported email, calendar event or website inquiry. Rather than
introduce new tables (`ExternalMessage`, `CalendarEvent`, `Inquiry`, ...),
every one of them maps onto the existing `Communication` entity
(distinguished by `channel`: "email"/"calendar"/"website"), with email
attachments as `Document` rows — both already had `LinkableMixin` and were
already, if minimally, exercised by `data/seed.py`. This avoids a second
"communication-like" concept living alongside the real one. `Contact`
(defined since step 1, never used until now, per step 20's own audit) is
the identity these imports resolve to or create — never a `Supplier`,
`Customer` or `Opportunity`, even when a sender's company is confidently
identifiable, because creating a business entity from an unverified external
message is a materially different, higher-consequence action than recording
"someone said this." A `Contact` can remain `unresolved` (both
`LinkableMixin` fields `None`) indefinitely, which is treated as a normal,
expected state, not a data quality problem to fix. This required three
small, additive schema changes (`Contact.company_id`; `source`/
`external_id` on `Communication` and `Document`, unique together for
idempotence) — the only Data Core changes this step made; nothing about
Observation, Interpretation, Decision, the AI Orchestrator or Home changed,
since none of them read `Communication` or `Contact` yet (verified by
`tests/test_connectors_pipeline_compatibility.py`). Entity resolution
itself is a conservative, generic substring match between an email's domain
(or a stated company name) and existing Supplier/Customer names — real
matching logic, not a hardcoded lookup table, but deliberately not fuzzy or
ML-based, so an incorrect match is always explainable in one sentence.
Documented in `brain/connectors.md`.

## 22. Only 2 of the brief's 6 suggested external Observables were built; the other four don't fit the existing per-entity Observable shape

Step 22's brief suggested up to six external Observables
(`external_inquiry_count`, `unanswered_external_message_age`,
`supplier_communication_activity`, `customer_communication_activity`,
`calendar_conflict_count`, `upcoming_business_meeting`). I built exactly
two: `supplier_unanswered_message_age_days` and
`customer_unanswered_message_age_days`. The Observation Engine's existing,
unmodified shape (one Observable, one `entity_type` from {SUPPLIER, PRODUCT,
CUSTOMER}, iterated per real row of that type) doesn't naturally fit the
other four: `external_inquiry_count`/`calendar_conflict_count` are
inherently company-wide or pairwise-between-events facts, not a property of
one Supplier/Customer row, and forcing them into the per-entity shape would
have meant either extending `_ENTITY_MODELS` with a COMPANY row (a
non-trivial special case in the shared sweep loop) or picking an arbitrary
single entity to attach a company-wide count to. `supplier_communication_activity`/
`customer_communication_activity` (a change in message volume) have no
defensible universal direction — a spike could mean escalating problems or
growing engagement — so registering a direction for them would have forced
exactly the kind of premature "is this good or bad" judgment the brief
explicitly said the deterministic layer must never make; leaving them
unregistered would make every instance classify as `observation`, which is
correct but adds no new demonstrable behavior beyond what the two built
Observables already show. Two Observables, chosen because they cleanly
fit the existing shape AND have a defensible, universal direction (a longer-
unanswered message is always worse, independent of content), were enough to
demonstrate all three of the brief's mandatory cases plus real cross-domain
correlation with an existing Observable (Steel Frame Assembly's margin
issue + Northline Steel's own unanswered email). Documented in
`brain/external_data_intelligence.md`.

## 23. `Observable` gained an optional `extra_context` callback so Interpretation's LLM can see the actual message, not just a number

The brief's own worked example (a supplier's renegotiation email) expects
the Interpretation's narrative to reference what the message actually says.
The three original Observables (margin_pct, delivery_delay_days,
customer_revenue_variation_pct) are purely numeric — there was never a
specific record worth attaching to them. Rather than special-case the two
new Observables inside `app.interpretation.context.assemble_context`
(checking the observable's name and querying Communication directly there,
which would have made a generic module aware of specific metric names — the
exact anti-pattern this codebase has consistently avoided), `Observable`
gained one new, optional field: `extra_context: Callable[[Session, uuid.UUID],
dict] | None = None`, called after `compute()` to attach whatever concrete
record an Observable's own author judges relevant. `Observation` and its
Event Log payload gained a matching `extra_context: dict` field (default
`{}`). `assemble_context` surfaces it generically under
`business_event.related_message` (and, for a message-bearing Observable
that ended up as the *correlated* one rather than primary during step 15's
own cross-domain correlation, under `related_messages_from_correlated_observations`)
— a purely additive change: every pre-existing Observable's behavior,
payload shape and Interpretation output are byte-for-byte unchanged (`{}` in,
`related_message: null` out), verified by every pre-existing Observation/
Interpretation test passing unmodified. A second, smaller fix was needed
alongside this: `compute_unanswered_message_age` originally treated ANY
later-dated outbound Communication as "already answered," including a
merely *scheduled* future calendar event — fixed to only count outbound
Communications that have actually occurred (`occurred_at <= now`), which is
also what makes the Northline Steel cross-domain correlation demo work
correctly (a future-scheduled pricing call must not silently suppress the
real, still-unanswered renegotiation email signal). Documented in
`brain/external_data_intelligence.md`.

## 24. Business Domains (Step 23B) are read-only views, composed entirely from existing functions — no new intelligence, no per-domain database

The step-23 audit had already established that Finance/Procurement/Sales had
no functioning frontend despite the backend already holding everything
needed to answer real questions about them: `app.core.entity_context` for
relational structure, `app.core.analytics`'s trend functions, and
`HomeService.get_ai_priorities` for AI-generated signals. Step 23B's brief
asked for these domains to become "visibly real" pages, and a mid-task
steering note made the constraint explicit: never build something new that
an existing abstraction already does. Every non-trivial number shown on
`/data/{suppliers,customers,products,transactions}` and
`/business/{finance,procurement,sales}` is therefore composed, never
recomputed — `app/data/service.py`'s `list_suppliers`/`get_supplier_detail`/etc.
call `get_entity_context`, `compute_supplier_delivery_performance`,
`compute_customer_value_trend`, `compute_margin_trend` and
`compute_unanswered_message_age` directly, and the three domain overview
endpoints (`GET /finance/overview`, `/procurement/overview`,
`/sales/overview`) call those same `app/data/service.py` functions rather
than re-querying the ORM. The one genuinely new computation is
`compute_company_financials` in `app.core.analytics` (company-wide total
revenue/costs/margin) — a different granularity than `compute_margin_trend`'s
per-product baseline-vs-recent split, not a duplicate of it, and shared
between Finance (revenue, costs, margin) and Procurement (its "total spend"
is exactly that function's `total_costs`) so the two domains can never
silently disagree on what the company spent. Procurement's new
`GET /overview` endpoint was added to the *existing*
`app/domains/procurement/router.py` (which already existed for
`POST /supplier-cost-changes`) rather than a parallel router; Finance's and
Sales's router/service/schemas fill in the `app/domains/{finance,sales}/`
modules that had existed as empty placeholders since Step 12's scope
decision (#1 above) — no new module boundary was introduced, only content
inside boundaries the architecture already reserved. CRM, Marketing, HR and
Supply Chain remain exactly as unimplemented as Step 12 left them; the
Sidebar was restructured to a grouped HOME/BUSINESS/DATA/INTELLIGENCE/
ACTIONS/AI layout but still only links to functional pages. Documented in
`brain/business_domains.md`.

## 25. The frontend became the real product surface (Steps 24-29), not just a thin client over already-decided backend logic

Through Step 23B the frontend was largely a functional-but-minimal read
layer; starting at Step 24 the brief shifted to treating the frontend as the
actual product — onboarding, a single design system, the Command Center as
the flagship screen, a real communication center, 12-month trend charts,
and Tasks as a genuine action center. The standing constraint across all of
these steps was the same: reuse the existing backend (Data Core, Business
Context, Baseline/Significance/Snapshot, Observation/Interpretation/
Decision, Orchestrator, Home, Actions/HITL) and add only the minimal,
justified backend surface a real frontend feature needed — never a new
architecture, never a second source of truth. Every backend addition listed
in #26-29 below is additive (new columns with defaults, new endpoints
composing existing services) and none of them required touching
Observation/Interpretation/Decision, which is why no regression appeared in
the pipeline's own test suite across five separate frontend-focused passes.

## 26. Onboarding and Settings write to the real Company/BusinessContext endpoints — no separate "setup" data model

Step 24 asked for a premium-feeling onboarding wizard and a persistent
company identity in the chrome. Rather than modeling "the answers given
during onboarding" as its own entity, the wizard's 4 steps (company,
organization, current systems, summary) write directly to
`PATCH /company` and `PATCH /business-context` — the same two endpoints
`/settings` uses afterward to edit the same fields. A field the UI collects
that has nowhere to live yet (e.g. currently-used ERP/CRM systems) is kept
client-side only and explicitly not persisted, rather than inventing a
schema column for a value nothing downstream reads yet.

## 27. Technical noise was fixed at its source (the deterministic LLM fallback and the classification templates), never patched with `.replace()` in the frontend

Without an `OPENAI_API_KEY` configured (the default in this environment),
`DeterministicLLMClient` originally echoed its raw prompt back
(`"[deterministic answer -- no LLM configured] {prompt}"`), and
`Interpretation`/`Decision`'s deterministic templates were English and
referenced raw observable identifiers. Both leaked directly into the UI as
JSON-like text and English fragments inside an otherwise French product. A
mid-Step-27 correction made the rule explicit: never hide the problem by
stripping strings in a component — fix the source that produces the string.
Three call sites were changed to branch on `isinstance(llm,
DeterministicLLMClient)` and compose a clean French sentence from data that
was already fully available (`app/interpretation/engine.py`'s
`_deterministic_explanation`, `app/decision/engine.py`'s
`_build_recommendation`, `app/ai/orchestrator/service.py`'s
`_deterministic_answer`), backed by one new shared label module,
`app/core/observable_labels.py`. A real regression this surfaced: the fix's
first pass silently dropped Step 22's feature of quoting the actual message
subject that triggered an unanswered-message signal — restored by having
`_deterministic_explanation` append it explicitly when present, rather than
accepting the loss of real information as the cost of removing noise.
`Risk.title`/`Opportunity.title` from the older per-metric Intelligence
pipeline were deliberately left in English: `app/snapshot/service.py`
string-matches those exact English titles for cross-domain correlation, so
translating them would have silently broken that correlation — a documented,
reasoned exception rather than an unexplained inconsistency.

## 28. `GET /contacts` and the FR/EN switcher are both scoped to real, honest coverage rather than faked completeness

Step 28 asked for Contacts to become a real communication center and for a
working language switcher. `GET /contacts` (new, `app/data/service.py`) does
nothing `app/core/entity_context.py` couldn't already do per-entity — it
just lists every `Contact` company-wide and resolves, for each, its linked
Supplier/Customer name and its most recent `Communication` by the same
`related_entity_type`/`related_entity_id` pair both already carry, with no
new join table. The frontend then shows Gmail/Site web as genuinely
"Connecté (démonstration)" (real connectors, real ingested counts from
`GET /connectors`) and LinkedIn/Facebook/Email marketing as explicitly "Non
configuré" — never a fabricated "connected" state for an integration that
doesn't exist. The FR/EN switcher (`frontend/lib/i18n.tsx`, a small
localStorage-persisted context with one centralized dictionary) deliberately
covers only the app's own chrome and static labels (Sidebar, Topbar, page
titles); it does not attempt to translate backend-generated content (Risk
titles, narrative text, Decision reasoning), since that content is produced
server-side in French and translating it live would require a backend i18n
layer this pass explicitly did not build. The campaign/social widget on the
same page follows the identical honesty rule: its CONTENU→DIFFUSION→
ENGAGEMENT→CONVERSION→RÉTENTION funnel only fills in "Contenu" (a real
seeded Communication) and marks every other stage "Indisponible" rather than
inventing engagement numbers no connector has ever measured.

## 29. `compute_monthly_series` is one shared, zero-filling function reused by three overviews; `Task.domain`/`requires_decision` and two new endpoints turn Tasks into an action center without a second Task-like entity

Step 29 asked for real 12-month Achats/Ventes charts, a Finance cross-
reference of the two, and a full redesign of Tasks into a business action
center with a large library of real actions. `compute_monthly_series`
(`app/core/analytics.py`) computes one thing — real, zero-filled monthly
totals for a set of Transaction types — and is called three times (Procurement's
`monthly_purchases`, Sales's `monthly_sales`, Finance's own copies of both)
rather than being reimplemented per domain; a month with no matching
Transaction reports `0`, never an omission or an interpolation, so the
frontend chart can show an honest gap. For Tasks, the brief's large action
library (Finance/RH/Ventes/Achats/Marketing/Direction/Opérations, ~70
concrete action names, some requiring a decision before execution — e.g. a
financing request) was implemented as a frontend-only static catalog
(`frontend/lib/action-library.ts`) that creates ordinary Tasks through the
existing `POST /actions/tasks`, plus exactly two additive Task columns
(`domain`, `requires_decision`, both nullable/defaulted, no backfill needed)
and two small service methods: `update_status` (a whitelisted state machine
over the existing `TaskStatus` enum — `open ↔ in_progress ↔ done/cancelled`
— refusing to touch a Task that is an AI proposal still awaiting
approve/reject) and `submit_for_validation`, which deliberately reuses the
*existing* `"create_task"` `ActionExecutor` branch rather than adding a new
one: that branch's effect (flip the Task to `EXECUTED`) is exactly the right
semantics for "this human-authored action has now been approved," so no new
execution branch was needed. No loan/HR/financial modeling logic was built
behind the "Analyser une demande de prêt"-style templates — the human still
does that analysis; the product only gives the task a place to live, a
decision-required flag, and a real validation step, never a fabricated
scenario calculator.

# V2 — Business objects, relationships, transactions

## 30. One `CommercialDocument` table for all ten document kinds

Requests, quotes, orders, deliveries and invoices on both sides share
numbering, statuses, lines, parties, traceability and the contextual API.
Ten tables would have duplicated all of that; `kind` + a lifecycle table
(`app/transactions/lifecycle.py`) keeps one code path. A customer request is
the root of a deal. See `brain/transactional_model.md`.

## 31. Documents post ledger facts; a supplier invoice revalues instead of posting

V1 intelligence reads `Transaction`. Rather than rewrite it, documents post
facts when the business event happens (order confirmed, goods received), each
pointing back to its document. The V2 audit found V1 sums PURCHASE_ORDER +
INVOICE as costs, so an approved supplier invoice revalues the reception
facts instead of adding an INVOICE fact — never double-counting a purchase.

## 32. One product, one customer, one representation

Creating a product or customer from a quote reuses an existing one with the
same reference/name. A supplier quoting a product creates the
product↔supplier relation once.

## 33. Follow-ups are computed at read time — no scheduler

Due quotes, awaited supplier quotes and unanswered messages are computed when
a page opens. Nothing is sent by a background job; this is stated in the UI.

## 34. Every uncertain value carries its basis; ranges stay ranges

observed / declared / estimated / benchmark / (V2.1) simulated / unknown,
with a confidence where relevant. Prices, lead times, costs, margins, stock,
salaries, cash, valuations. Never a midpoint presented as a fact.

## 35. One relationship read model over three storages

FKs, V1 LinkableMixin and the new many-to-many `ObjectLink` are read through
`app/objects/graph.py`; pages, margin and the Orchestrator never care where
a relation is stored. Integrity of ObjectLink is enforced at creation.

## 36. Planned cost is frozen on the sales line

Approving a supplier invoice updates catalog prices; recomputing "planned"
from live data would erase the original estimate. The cost expected when a
line is priced is stored on the line (with its basis) and carried quote → order.

## 37. Workspaces + contextual links instead of one tab per object

See `brain/navigation_v2.md`. Intelligence and Actions merged into one entry
each; the V1 Data hub removed; documents, customers, suppliers, products are
reached contextually.

## 38. Roles + declared profiles, enforced server-side

`X-User-Id` names a profile; the backend enforces permissions; no header =
legacy director mode for V1 clients. Declared identity, not authentication
(`brain/permissions.md`).

## 39. A `deals` agent instead of editing V1 agents

V1 tests pin each agent's capability set. The three V2 read capabilities
(object context, document margin, supplier benchmark) belong to a new agent,
used when a question names a document or is asked from an object page.

# V2.1 — Strategic additions

## 40. Reuse before creating

HR decisions and compliance requests are `Task`s (new columns: assignee,
due date, category, action payload) going through the existing HITL; outside
experts are `Supplier`s with a kind and a fee range; new events use the
existing bus and Event Log; new intelligence becomes V1 Risks/Opportunities.
New tables only where nothing existed (employees, needs, candidates,
accounts, movements, shareholders, sourcing leads, AI runs, website proposals).

## 41. Custom access = role defaults ± director decisions

`access_grants` / `access_revokes` per profile; sensitive areas
(treasury, ownership, employee costs) director-only by default; nobody edits
their own access; every workspace router enforces its view permission.

## 42. People: estimated contribution, never a score

Cost is a labelled range (benchmark charges when missing); contribution uses
only measurable inputs, says "partielle" and "insuffisante" when so; no
ranking; promotions/raises only after director approval.

## 43. Director finance is deterministic

Projection as low/high range from balances, planned movements, document
receivables/payables and estimated flows; valuation as a range from revenue ×
multiple (declared or benchmark); masked account identifiers only.

## 44. Sourcing and website intelligence never invent and never act alone

No invented supplier/price; web search only when configured; the real
website is never modified (no CMS connector); every AI run records its real
steps and mode (real / simulated / partial).

## 45. Demo data is SIMULATED and says so

V2.1 demo data (salaries, balances, candidates, messages) is stored with
basis/source "simulated" and shown with a red "Simulé" badge.

## 46. Numbers are always mono and tabular (UX pass)

IBM Plex Mono + tabular figures through `.num` / `.figure` in globals.css,
not per-page styling; titles keep the display font.

## 47. Charts never invent history

Sparklines use real monthly series only, trimmed before the first activity,
with the open month marked partial and a 3-month minimum; below that the UI
says "historique insuffisant". Trend badges are computed or absent.

## 48. Functional mailboxes are a classification, not an integration

sales@ / orders@ / rfq@ / careers@ / support@ / contact@ group existing
messages by displayed rules; statuses are Connectée / Démonstration / Non
configurée and "Connectée" requires a real provider. No account is connected.

## 49. Follow-up and campaign metrics keep stages and bases apart

Draft ≠ validated ≠ sent ≠ reply ≠ order; rates need 3 sends. Campaign
figures are declared / observed / not available; no attribution without a
real link; no marketing data is created or modified.
