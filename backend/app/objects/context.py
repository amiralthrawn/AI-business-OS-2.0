"""The contextual view of any business object (V2): the one payload behind
every object page and behind the AI's object reasoning.

    OBJECT -> RELATED OBJECTS -> CONTEXT (history) -> INTELLIGENCE -> ACTIONS

Answers the five questions every screen must answer (brain/navigation_v2.md):
where am I (`breadcrumb`), what am I looking at (`object`), what is it
linked to (`related`), what can I do now (`actions`, already filtered by
the caller's role), where can I go next (every summary carries its `href`).
"""

import uuid
from dataclasses import asdict, dataclass, field

from sqlalchemy.orm import Session

from app.access.deps import CurrentUser
from app.access.policy import WRITE_FINANCE, WRITE_OPERATIONS, ACTION_SUBMIT_EMAIL, WRITE_COMMUNICATIONS, WRITE_PROCUREMENT, WRITE_SALES
from app.core.entities import (
    CommercialDocument,
    DocumentKind,
    EventLogEntry,
    Opportunity,
    OpportunityStatus,
    Risk,
    RiskStatus,
)
from app.objects.graph import document_ancestry, related_edges
from app.objects.registry import OBJECT_TYPES, ObjectSummary, get_object, summarize
from app.transactions.lifecycle import DERIVATIONS, KIND_WRITE_PERMISSION, KINDS, manual_transitions, status_label

# Group order and labels of the "related objects" panel.
GROUPS: list[tuple[str, str]] = [
    ("customer", "Clients"),
    ("supplier", "Fournisseurs"),
    ("contact", "Contacts"),
    ("product", "Produits"),
    ("commercial_document", "Documents commerciaux"),
    ("communication", "Communications"),
    ("document", "Fichiers"),
    ("task", "Tâches"),
    ("risk", "Risques"),
    ("opportunity", "Opportunités"),
    ("employee", "Employés"),
    ("candidate", "Candidats"),
    ("transaction", "Écritures"),
]

EVENT_LABELS = {
    "DocumentCreated": "Document créé",
    "DocumentStatusChanged": "Changement de statut",
    "ObjectsLinked": "Objet lié",
    "EmailDrafted": "Brouillon d'email préparé",
    "EmailSubmitted": "Email soumis à validation",
    "EmailSent": "Email envoyé",
    "StockUpdated": "Stock mis à jour",
    "TaskCreated": "Tâche créée",
    "RiskCreated": "Risque détecté",
    "OpportunityCreated": "Opportunité détectée",
    "ObservationDetected": "Signal observé",
    "EventInterpreted": "Signal interprété",
    "DecisionProposed": "Décision proposée",
    "ActionProposed": "Action proposée",
    "ActionApproved": "Action approuvée",
    "ActionExecuted": "Action exécutée",
    "SupplierCostIncreased": "Hausse de coût fournisseur",
    "MarginDeteriorated": "Dégradation de marge",
    "SupplierPerformanceDeteriorated": "Dégradation des délais fournisseur",
    "CustomerGrowthDetected": "Croissance client",
    "CustomerDeclineDetected": "Baisse client",
    # V2.1
    "EmployeeCostChanged": "Coût employé modifié",
    "EmployeeDecisionApplied": "Décision RH appliquée",
    "CandidateCreated": "Fiche candidat créée",
    "SkillGapDetected": "Compétence manquante détectée",
    "CashForecastDeteriorated": "Prévision de trésorerie dégradée",
    "SourcingOpportunityFound": "Source moins chère possible",
    "WebsiteAudited": "Site analysé",
    "WebsiteChangeApproved": "Modification du site approuvée",
}


@dataclass
class ActionItem:
    key: str  # "status:sent" | "derive:customer_order" | "email:follow_up" | "create:customer_quote" | "benchmark"
    label: str
    kind: str  # "status" | "derive" | "email" | "create" | "navigate"
    allowed: bool
    reason: str | None = None
    params: dict = field(default_factory=dict)


@dataclass
class TimelineEntry:
    occurred_at: object
    label: str
    event_type: str
    detail: str | None


@dataclass
class ObjectContext:
    object: ObjectSummary
    breadcrumb: list[ObjectSummary]
    related: list[dict]
    timeline: list[TimelineEntry]
    intelligence: list[dict]
    actions: list[ActionItem]

    def to_dict(self) -> dict:
        return asdict(self)


def _describe(session: Session, edges) -> list[tuple[str, ObjectSummary]]:
    described = []
    for edge in edges:
        try:
            obj = get_object(session, edge.type, edge.id)
        except LookupError:
            continue  # application-level integrity: a dangling pointer is skipped, not fatal
        described.append((edge.relation, summarize(edge.type, obj)))
    return described


def _grouped(described: list[tuple[str, ObjectSummary]]) -> list[dict]:
    groups = []
    for key, label in GROUPS:
        items = [asdict(s) | {"relation": rel} for rel, s in described if s.type == key]
        if items:
            groups.append({"type": key, "label": label, "count": len(items), "items": items})
    return groups


def _timeline(session: Session, obj_type: str, obj_id: uuid.UUID) -> list[TimelineEntry]:
    rows = (
        session.query(EventLogEntry)
        .filter(EventLogEntry.subject_type == obj_type, EventLogEntry.subject_id == obj_id)
        .order_by(EventLogEntry.occurred_at.desc())
        .limit(30)
        .all()
    )
    entries = []
    for row in rows:
        payload = row.payload or {}
        detail = None
        if row.event_type == "DocumentStatusChanged":
            detail = f"{payload.get('from')} → {payload.get('to')}"
        elif row.event_type == "ObjectsLinked":
            detail = f"{payload.get('linked_type')} ({payload.get('relation')})"
        elif payload.get("title"):
            detail = payload.get("title")
        entries.append(TimelineEntry(row.occurred_at, EVENT_LABELS.get(row.event_type, row.event_type), row.event_type, detail))
    return entries


def _intelligence(session: Session, described: list[tuple[str, ObjectSummary]], obj_type: str, obj) -> list[dict]:
    """Open Risks/Opportunities on this object AND on the objects it directly
    involves (a PO shows the open risk on its supplier) -- the point where
    V1's intelligence meets V2's objects."""

    signals: list[dict] = []
    seen: set[uuid.UUID] = set()

    def add(model, open_status, via: str | None, **filters):
        for row in session.query(model).filter_by(**filters).filter(model.status == open_status).all():
            if row.id not in seen:
                seen.add(row.id)
                summary = summarize("risk" if model is Risk else "opportunity", row)
                signals.append(asdict(summary) | {"via": via, "description": row.description, "severity": getattr(row, "severity", None) and row.severity.value})

    linkable = OBJECT_TYPES[obj_type].linkable
    if linkable is not None:
        add(Risk, RiskStatus.OPEN, None, related_entity_type=linkable, related_entity_id=obj.id)
        add(Opportunity, OpportunityStatus.OPEN, None, related_entity_type=linkable, related_entity_id=obj.id)
    if obj_type in {"commercial_document", "transaction", "product", "contact"}:
        for _, s in described:
            if s.type in {"supplier", "customer", "product"}:
                neighbor_linkable = OBJECT_TYPES[s.type].linkable
                add(Risk, RiskStatus.OPEN, f"{s.kind_label} {s.title}", related_entity_type=neighbor_linkable, related_entity_id=s.id)
                add(Opportunity, OpportunityStatus.OPEN, f"{s.kind_label} {s.title}", related_entity_type=neighbor_linkable, related_entity_id=s.id)
    return signals


# --- Actions ---------------------------------------------------------------------

_EMAIL_PURPOSES_BY_KIND: dict[DocumentKind, list[tuple[str, str]]] = {
    DocumentKind.CUSTOMER_REQUEST: [("reply", "Répondre au client"), ("brochure", "Envoyer une brochure"), ("nda", "Proposer un NDA")],
    DocumentKind.CUSTOMER_QUOTE: [("send_quote", "Envoyer le devis"), ("follow_up", "Préparer une relance")],
    DocumentKind.CUSTOMER_ORDER: [("order_confirmation", "Confirmer la commande au client")],
    DocumentKind.PURCHASE_REQUEST: [("rfq_price", "Demander un prix"), ("rfq_availability", "Demander la disponibilité"), ("rfq_lead_time", "Demander un délai")],
    DocumentKind.SUPPLIER_QUOTE: [("rfq_terms", "Demander les conditions"), ("rfq_documents", "Demander des documents"), ("follow_up", "Relancer le fournisseur")],
    DocumentKind.PURCHASE_ORDER: [("send_purchase_order", "Envoyer la commande au fournisseur")],
    DocumentKind.CUSTOMER_INVOICE: [("payment_reminder", "Préparer une relance de paiement")],
    DocumentKind.CUSTOMER_CREDIT_NOTE: [("credit_note_offer", "Proposer l'avoir au client")],
    DocumentKind.RECEPTION: [("supplier_claim", "Préparer une réclamation fournisseur")],
    DocumentKind.SUPPLIER_CREDIT_NOTE: [("supplier_claim", "Préparer la demande d'avoir")],
}


# Wording of status buttons that record something the OTHER party did:
# the user records it, the software does not claim it happened by itself.
_STATUS_ACTION_LABELS: dict[tuple[DocumentKind, str], str] = {
    (DocumentKind.CUSTOMER_ORDER, "sent"): "Marquer comme transmise au client",
    (DocumentKind.CUSTOMER_ORDER, "acknowledged"): "Enregistrer l'accusé de réception du client",
    (DocumentKind.CUSTOMER_CREDIT_NOTE, "submitted"): "Marquer comme soumis au client",
    (DocumentKind.CUSTOMER_CREDIT_NOTE, "accepted"): "Enregistrer l'acceptation du client",
    (DocumentKind.CUSTOMER_CREDIT_NOTE, "rejected"): "Enregistrer le refus du client",
    (DocumentKind.CUSTOMER_CREDIT_NOTE, "draft"): "Le client demande une modification",
    (DocumentKind.SUPPLIER_CREDIT_NOTE, "confirmed"): "Enregistrer la confirmation du fournisseur",
    (DocumentKind.SUPPLIER_CREDIT_NOTE, "rejected"): "Enregistrer le refus du fournisseur",
}


def _document_actions(user: CurrentUser, doc: CommercialDocument) -> list[ActionItem]:
    actions: list[ActionItem] = []
    can_edit = user.can(KIND_WRITE_PERMISSION[doc.kind])
    no_right = None if can_edit else "Votre rôle ne permet pas de modifier ce document."
    # System-only statuses (settlement, validation, imputation) are not
    # buttons: they follow the billing actions below (app.billing).
    for status in manual_transitions(doc.kind, doc.status):
        actions.append(ActionItem(f"status:{status}", _STATUS_ACTION_LABELS.get((doc.kind, status), f"Passer à « {status_label(doc.kind, status)} »"), "status", can_edit, no_right, {"status": status}))
    for target in DERIVATIONS.get(doc.kind, ()):
        permitted = user.can(KIND_WRITE_PERMISSION[target])
        actions.append(
            ActionItem(
                f"derive:{target.value}", f"Créer {KINDS[target].label.lower()}", "derive", permitted,
                None if permitted else "Votre rôle ne permet pas de créer ce document.",
                {"kind": target.value, "needs_supplier": target in {DocumentKind.SUPPLIER_QUOTE, DocumentKind.PURCHASE_ORDER} and doc.kind == DocumentKind.PURCHASE_REQUEST},
            )
        )  # fmt: skip
    can_draft = user.can(WRITE_COMMUNICATIONS)
    for purpose, label in _EMAIL_PURPOSES_BY_KIND.get(doc.kind, []):
        actions.append(ActionItem(f"email:{purpose}", label, "email", can_draft, None if can_draft else "Votre rôle ne permet pas de préparer des emails.", {"purpose": purpose}))
    if doc.kind == DocumentKind.PURCHASE_REQUEST:
        actions.append(ActionItem("benchmark", "Comparer les fournisseurs", "navigate", True, None, {"anchor": "benchmark"}))
    # V2.2 billing actions live in their panels (anchors) -- the panel checks
    # the rule, the API checks the right (app.billing.router).
    can_finance = user.can(WRITE_FINANCE)
    if doc.kind in {DocumentKind.CUSTOMER_INVOICE, DocumentKind.SUPPLIER_INVOICE} and doc.status in {"issued", "approved", "partially_paid"}:
        actions.append(ActionItem("payment", "Enregistrer un règlement", "navigate", can_finance, None if can_finance else "Réservé à la finance.", {"anchor": "reglements"}))
    if doc.kind in {DocumentKind.CUSTOMER_DELIVERY, DocumentKind.RECEPTION} and doc.status in {"delivered", "received"}:
        can_ops = user.can(WRITE_OPERATIONS)
        actions.append(ActionItem("nonconformity", "Signaler une non-conformité", "navigate", can_ops, None if can_ops else "Réservé aux opérations.", {"anchor": "suivi"}))
    if doc.kind in {DocumentKind.CUSTOMER_CREDIT_NOTE, DocumentKind.SUPPLIER_CREDIT_NOTE} and doc.status in {"accepted", "validated", "confirmed", "applied"}:
        actions.append(ActionItem("credit", "Suivre l'avoir", "navigate", True, None, {"anchor": "avoir"}))
    return actions


def _entity_actions(user: CurrentUser, obj_type: str, obj) -> list[ActionItem]:
    actions: list[ActionItem] = []
    if obj_type == "customer":
        ok = user.can(WRITE_SALES)
        why = None if ok else "Réservé aux rôles commerciaux."
        actions += [
            ActionItem("create:customer_request", "Nouvelle demande client", "create", ok, why, {"kind": "customer_request", "customer_id": str(obj.id)}),
            ActionItem("create:customer_quote", "Nouveau devis", "create", ok, why, {"kind": "customer_quote", "customer_id": str(obj.id)}),
        ]
    if obj_type == "supplier":
        ok = user.can(WRITE_PROCUREMENT)
        actions.append(ActionItem("create:purchase_request", "Nouvelle demande d'achat", "create", ok, None if ok else "Réservé aux achats.", {"kind": "purchase_request"}))
    if obj_type == "product":
        actions += [
            ActionItem("create:customer_quote", "Chiffrer pour un client", "create", user.can(WRITE_SALES), None if user.can(WRITE_SALES) else "Réservé aux rôles commerciaux.", {"kind": "customer_quote", "product_id": str(obj.id)}),
            ActionItem("create:purchase_request", "Lancer une demande d'achat", "create", user.can(WRITE_PROCUREMENT), None if user.can(WRITE_PROCUREMENT) else "Réservé aux achats.", {"kind": "purchase_request", "product_id": str(obj.id)}),
            ActionItem("benchmark", "Comparer les fournisseurs", "navigate", True, None, {"anchor": "benchmark"}),
        ]
    if obj_type in {"customer", "supplier", "contact"}:
        ok = user.can(WRITE_COMMUNICATIONS)
        actions.append(ActionItem("email:reply", "Préparer un email", "email", ok, None if ok else "Votre rôle ne permet pas de préparer des emails.", {"purpose": "generic"}))
    if obj_type == "communication" and obj.status == "draft":
        ok = user.can(ACTION_SUBMIT_EMAIL)
        actions.append(ActionItem("submit", "Soumettre à validation", "status", ok, None if ok else "Votre rôle ne permet pas de soumettre un email."))
    return actions


def build_context(session: Session, user: CurrentUser, obj_type: str, obj_id: uuid.UUID) -> ObjectContext:
    obj = get_object(session, obj_type, obj_id)
    summary = summarize(obj_type, obj)
    described = _describe(session, related_edges(session, obj_type, obj_id))

    if obj_type == "commercial_document":
        breadcrumb = [summarize("commercial_document", d) for d in document_ancestry(session, obj_id)]
        actions = _document_actions(user, obj)
    else:
        breadcrumb = [summary]
        actions = _entity_actions(user, obj_type, obj)

    return ObjectContext(
        object=summary,
        breadcrumb=breadcrumb,
        related=_grouped(described),
        timeline=_timeline(session, obj_type, obj_id),
        intelligence=_intelligence(session, described, obj_type, obj),
        actions=actions,
    )
