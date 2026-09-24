# Permissions (V2 / V2.1)

```
ROLE                    → default permissions      (app/access/policy.py)
+ CUSTOM PROFILE ACCESS → grants / revokes          (UserProfile.access_grants / access_revokes)
= EFFECTIVE PERMISSIONS → enforced by the backend, reflected by the UI
```

## Vocabulary

- `view:*` — what a profile sees (navigation **and** read APIs): sales, procurement, catalog, communications, people, finance, intelligence, actions, compliance, settings, and the sensitive **employee_costs**, **treasury**, **ownership**.
- `write:*` — what it can edit: sales, procurement, operations, finance, catalog, communications, people, treasury, compliance, settings.
- `action:*` — submit_email, approve, ask_ai.

`ACCESS_CATALOG` lists every permission once with a label, a group and a
sensitive flag; Settings → Profils et rôles renders it as checkboxes.

## Defaults

Director: everything. Sales, Procurement, Operations, HR, Employee: see the
matrix in `policy.py`. **Treasury, ownership and employee costs are
director-only by default**; a director can grant them to a profile.

## Enforcement

- Every workspace router carries `Depends(require(view:…))` (`app/main.py`).
- Writes check their `write:*` permission; document kinds map to permissions (`KIND_WRITE_PERMISSION`).
- Object context and search check the object's view permission and hide related groups the profile cannot open.
- HITL approval is domain-scoped (`can_approve_with`): sales approves sales/marketing, procurement approves procurement/operations; **people decisions, compliance, website changes, finance and tasks without domain: director only**.
- Salary data never leaves the API without `view:employee_costs` (the employee page returns `cost: null`; a raise proposal requires cost access).

## Administration rules

- Only a profile with `write:settings` changes roles, activation or access.
- **Nobody edits their own role, activation or access** (backend refuses; UI shows read-only) — no self-granting.
- Unknown permission names are rejected (400) and ignored if ever stored.
- Deactivated profiles are refused (401).

## Identity — honest limit

There is no authentication in this MVP: the selected profile id is sent as
`X-User-Id` (cookie `aibos_user`). This is an authorization model enforced
server-side, **not** a security boundary until a real auth layer produces the
same `CurrentUser` from a verified token. No header = legacy single-operator
mode with director rights (kept for V1 clients and tests).
