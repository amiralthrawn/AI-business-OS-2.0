"""Role -> permissions matrix, plus per-profile custom access (V2, brain/permissions.md).

    ROLE                      -> default permissions (this file)
  + CUSTOM PROFILE ACCESS     -> grants / revokes decided by a director (UserProfile)
  = EFFECTIVE PERMISSIONS     -> what the backend enforces and the UI shows

One flat set of named permissions. No IAM engine, no per-row ACLs: call
sites only ever ask `has_permission(...)`, so the model can grow without
touching them. `view:*` = what a user sees (navigation + read APIs),
`write:*` = what they can edit, `action:*` = what they can trigger.
"""

from dataclasses import dataclass

from app.core.entities.user import Role

# --- Visibility (navigation + read APIs of a workspace) ---
VIEW_SALES = "view:sales"
VIEW_PROCUREMENT = "view:procurement"
VIEW_CATALOG = "view:catalog"
VIEW_FINANCE = "view:finance"
VIEW_COMMUNICATIONS = "view:communications"
VIEW_INTELLIGENCE = "view:intelligence"
VIEW_ACTIONS = "view:actions"
VIEW_SETTINGS = "view:settings"
# V2.1 -- people, director finance, compliance. The three sensitive ones
# (salaries, treasury, ownership) are director-only by default.
VIEW_PEOPLE = "view:people"
VIEW_EMPLOYEE_COSTS = "view:employee_costs"
VIEW_TREASURY = "view:treasury"
VIEW_OWNERSHIP = "view:ownership"
VIEW_COMPLIANCE = "view:compliance"

# --- Edition ---
WRITE_SALES = "write:sales"  # customer requests, quotes, customer orders
WRITE_PROCUREMENT = "write:procurement"  # purchase requests, supplier quotes, POs, sourcing
WRITE_OPERATIONS = "write:operations"  # receptions, deliveries (physical flow)
WRITE_FINANCE = "write:finance"  # invoices (both sides)
WRITE_CATALOG = "write:catalog"  # products, supplier terms, stock
WRITE_COMMUNICATIONS = "write:communications"  # drafts, links between emails and objects, website proposals
WRITE_SETTINGS = "write:settings"  # company, business context, users and their access
WRITE_PEOPLE = "write:people"  # employees, candidates, skill needs
WRITE_TREASURY = "write:treasury"  # accounts, cash movements, ownership
WRITE_COMPLIANCE = "write:compliance"  # compliance requests, external experts

# --- Actions ---
ACTION_SUBMIT_EMAIL = "action:submit_email"  # submit a draft for validation
ACTION_APPROVE = "action:approve"  # approve/reject HITL proposals (domain-scoped, see can_approve)
ACTION_ASK_AI = "action:ask_ai"

ALL_PERMISSIONS = frozenset(
    {
        VIEW_SALES, VIEW_PROCUREMENT, VIEW_CATALOG, VIEW_FINANCE, VIEW_COMMUNICATIONS,
        VIEW_INTELLIGENCE, VIEW_ACTIONS, VIEW_SETTINGS,
        VIEW_PEOPLE, VIEW_EMPLOYEE_COSTS, VIEW_TREASURY, VIEW_OWNERSHIP, VIEW_COMPLIANCE,
        WRITE_SALES, WRITE_PROCUREMENT, WRITE_OPERATIONS, WRITE_FINANCE, WRITE_CATALOG,
        WRITE_COMMUNICATIONS, WRITE_SETTINGS, WRITE_PEOPLE, WRITE_TREASURY, WRITE_COMPLIANCE,
        ACTION_SUBMIT_EMAIL, ACTION_APPROVE, ACTION_ASK_AI,
    }
)  # fmt: skip

ROLE_PERMISSIONS: dict[Role, frozenset[str]] = {
    Role.DIRECTOR: ALL_PERMISSIONS,
    Role.SALES: frozenset(
        {
            VIEW_SALES, VIEW_CATALOG, VIEW_FINANCE, VIEW_COMMUNICATIONS, VIEW_INTELLIGENCE, VIEW_ACTIONS,
            WRITE_SALES, WRITE_CATALOG, WRITE_COMMUNICATIONS,
            ACTION_SUBMIT_EMAIL, ACTION_APPROVE, ACTION_ASK_AI,
        }
    ),  # fmt: skip
    Role.PROCUREMENT: frozenset(
        {
            VIEW_PROCUREMENT, VIEW_CATALOG, VIEW_FINANCE, VIEW_COMMUNICATIONS, VIEW_INTELLIGENCE, VIEW_ACTIONS,
            WRITE_PROCUREMENT, WRITE_OPERATIONS, WRITE_CATALOG, WRITE_COMMUNICATIONS,
            ACTION_SUBMIT_EMAIL, ACTION_APPROVE, ACTION_ASK_AI,
        }
    ),  # fmt: skip
    Role.OPERATIONS: frozenset(
        {
            VIEW_SALES, VIEW_PROCUREMENT, VIEW_CATALOG, VIEW_COMMUNICATIONS, VIEW_ACTIONS,
            WRITE_OPERATIONS, WRITE_CATALOG, WRITE_COMMUNICATIONS,
            ACTION_SUBMIT_EMAIL, ACTION_ASK_AI,
        }
    ),  # fmt: skip
    # HR manages people and recruitment and follows compliance; salaries
    # (employee costs) stay director-only unless a director grants them.
    Role.HR: frozenset(
        {
            VIEW_COMMUNICATIONS, VIEW_ACTIONS, VIEW_PEOPLE, VIEW_COMPLIANCE,
            WRITE_COMMUNICATIONS, WRITE_PEOPLE, ACTION_SUBMIT_EMAIL, ACTION_ASK_AI,
        }
    ),  # fmt: skip
    Role.EMPLOYEE: frozenset({VIEW_CATALOG, VIEW_COMMUNICATIONS, VIEW_ACTIONS, ACTION_ASK_AI}),
}

# Which HITL proposals a role may approve, by Task.domain. The director
# approves everything; a Task with no domain -- and the sensitive domains
# (people decisions, compliance, website changes, finance) -- can only be
# approved by the director (never guessed into someone's scope).
_APPROVAL_DOMAINS: dict[Role, frozenset[str]] = {
    Role.SALES: frozenset({"sales", "marketing"}),
    Role.PROCUREMENT: frozenset({"procurement", "operations"}),
}

ROLE_LABELS_FR: dict[Role, str] = {
    Role.DIRECTOR: "Direction",
    Role.SALES: "Commercial",
    Role.PROCUREMENT: "Achats",
    Role.OPERATIONS: "Opérations",
    Role.HR: "RH",
    Role.EMPLOYEE: "Employé",
}


@dataclass(frozen=True)
class AccessItem:
    permission: str
    label: str
    group: str  # "Espaces" | "Données sensibles" | "Modification" | "Actions"
    sensitive: bool = False


# What a director can tick / untick per profile, in the navigation's own
# vocabulary (brain/permissions.md). Every permission appears exactly once.
ACCESS_CATALOG: tuple[AccessItem, ...] = (
    AccessItem(VIEW_SALES, "Ventes (affaires, devis, commandes, clients)", "Espaces"),
    AccessItem(VIEW_PROCUREMENT, "Achats (demandes, fournisseurs, sourcing)", "Espaces"),
    AccessItem(VIEW_CATALOG, "Catalogue & stock", "Espaces"),
    AccessItem(VIEW_COMMUNICATIONS, "Communications (emails, site web, campagnes)", "Espaces"),
    AccessItem(VIEW_PEOPLE, "Équipe (employés, recrutement)", "Espaces"),
    AccessItem(VIEW_FINANCE, "Finance (marges, écritures)", "Espaces"),
    AccessItem(VIEW_INTELLIGENCE, "Intelligence (risques, opportunités, décisions)", "Espaces"),
    AccessItem(VIEW_ACTIONS, "Actions & validations", "Espaces"),
    AccessItem(VIEW_COMPLIANCE, "Conformité & juridique", "Espaces"),
    AccessItem(VIEW_SETTINGS, "Configuration", "Espaces"),
    AccessItem(VIEW_EMPLOYEE_COSTS, "Rémunérations & coût des employés", "Données sensibles", True),
    AccessItem(VIEW_TREASURY, "Trésorerie & comptes bancaires", "Données sensibles", True),
    AccessItem(VIEW_OWNERSHIP, "Capital & valorisation", "Données sensibles", True),
    AccessItem(WRITE_SALES, "Modifier les ventes", "Modification"),
    AccessItem(WRITE_PROCUREMENT, "Modifier les achats", "Modification"),
    AccessItem(WRITE_OPERATIONS, "Réceptions & livraisons", "Modification"),
    AccessItem(WRITE_FINANCE, "Factures", "Modification"),
    AccessItem(WRITE_CATALOG, "Produits & stock", "Modification"),
    AccessItem(WRITE_COMMUNICATIONS, "Préparer emails & propositions site", "Modification"),
    AccessItem(WRITE_PEOPLE, "Employés & candidats", "Modification"),
    AccessItem(WRITE_TREASURY, "Comptes, flux & capital", "Modification", True),
    AccessItem(WRITE_COMPLIANCE, "Demandes de conformité", "Modification"),
    AccessItem(WRITE_SETTINGS, "Configuration & gestion des accès", "Modification", True),
    AccessItem(ACTION_SUBMIT_EMAIL, "Soumettre un email à validation", "Actions"),
    AccessItem(ACTION_APPROVE, "Valider des actions (de son domaine)", "Actions"),
    AccessItem(ACTION_ASK_AI, "Demander à l'IA", "Actions"),
)


def role_defaults(role: Role) -> frozenset[str]:
    return ROLE_PERMISSIONS.get(role, frozenset())


def effective_permissions(role: Role, grants: list[str] | None = None, revokes: list[str] | None = None) -> frozenset[str]:
    """Role defaults, plus what a director granted, minus what they revoked.
    Unknown names are ignored, never trusted."""

    granted = {p for p in (grants or []) if p in ALL_PERMISSIONS}
    revoked = {p for p in (revokes or []) if p in ALL_PERMISSIONS}
    return frozenset((role_defaults(role) | granted) - revoked)


# Kept for callers that only know a role (tests, V2 code paths).
def permissions_for(role: Role) -> frozenset[str]:
    return role_defaults(role)


def has_permission(role: Role, permission: str) -> bool:
    return permission in role_defaults(role)


def can_approve_with(role: Role, permissions: frozenset[str], task_domain: str | None) -> bool:
    if ACTION_APPROVE not in permissions:
        return False
    if role == Role.DIRECTOR:
        return True
    return task_domain is not None and task_domain in _APPROVAL_DOMAINS.get(role, frozenset())


def can_approve(role: Role, task_domain: str | None) -> bool:
    return can_approve_with(role, role_defaults(role), task_domain)


# Which view permission an object belongs to (contextual API, search).
# A commercial document belongs to its flow's workspace.
OBJECT_VIEW_PERMISSION: dict[str, str] = {
    "customer": VIEW_SALES,
    "supplier": VIEW_PROCUREMENT,
    "product": VIEW_CATALOG,
    "contact": VIEW_COMMUNICATIONS,
    "communication": VIEW_COMMUNICATIONS,
    "document": VIEW_COMMUNICATIONS,
    "transaction": VIEW_FINANCE,
    "risk": VIEW_INTELLIGENCE,
    "opportunity": VIEW_INTELLIGENCE,
    "task": VIEW_ACTIONS,
    "employee": VIEW_PEOPLE,
    "candidate": VIEW_PEOPLE,
    "bank_account": VIEW_TREASURY,
}
DOMAIN_VIEW_PERMISSION: dict[str, str] = {"sales": VIEW_SALES, "procurement": VIEW_PROCUREMENT}
