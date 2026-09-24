# People — employees, cost, contribution, recruitment (V2.1)

**Scope: a small layer, not HR software, not payroll, not an ATS.**

```
EMPLOYEE → COST → TASKS → CONTRIBUTION → BUSINESS IMPACT
Company needs + team skills + workload → skills gap → hiring recommendation
Application email → candidate → match with needs → interview proposal (HITL)
```

## Employee

Identity, job, department, status, hire date, weekly hours, leave left,
skills, responsibilities, manager, `user_id` (link to the person's profile),
`data_basis` (declared / simulated). Tasks are ordinary `Task` rows with
`assignee_employee_id` (reuse, no HR task entity).

## Cost

`EmployeeCostItem` lines (salary, employer charges, software, equipment,
benefits, other) as ranges with a basis. When employer charges are missing,
a **benchmark** line is computed from the country (FR 40–47 % of gross…),
labelled as such. Total = range; basis = weakest component; missing
components are listed. Visible only with `view:employee_costs`.

## Contribution — estimated, partial, never a verdict

Measured inputs only: tasks done/open/overdue (observed), margin of the
customer orders the person owns (via the margin engine, observed or
estimated). Statement says "estimée (partielle)", its confidence, and
"données insuffisantes" when so. **No single score, no ranking of people.**
The cost-coverage ratio is shown only to profiles with cost access.

## Decisions — HITL only

Promotion, raise, evolution, other decision = a `PENDING_VALIDATION` Task in
domain `people` with its parameters in `action_payload`; **only a director
approves**; approval applies the change (title / declared salary) and
publishes `EmployeeDecisionApplied` + `EmployeeCostChanged`. A job title
cannot be edited directly (400). Evolution *suggestions* are deterministic
(skills covering an uncovered declared need + tenure + work done) and
labelled "à examiner — aucune décision automatique".

## Skills gap & recruitment

`SkillNeed` (declared: skill, keywords, level, reason, impact, priority).
Gap = need with no active holder (or a single, overloaded holder).
Recommendation = profile, skills, justification, impact, priority,
confidence. "Signaler à l'Intelligence" creates an Opportunity
"Recruter ou former : X" (idempotent).

Candidates are extracted from application emails by explainable rules
(skills vocabulary, years of experience, position); fields are DECLARED by
the applicant (unverified) or SIMULATED for demo data. Matching = overlap
with each need's keywords (élevée / moyenne / faible), a reading aid only.
"Proposer un entretien" = a draft email (HITL); no meeting is booked.

## Limits

No payroll, contracts, time tracking, leave workflow, performance reviews;
contribution ignores non-commercial work; skill extraction is keyword-based.
