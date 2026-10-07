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

from app.core.i18n import text_of, tx
from app.access.deps import CurrentUser
from app.access.policy import WRITE_FINANCE, WRITE_OPERATIONS, ACTION_SUBMIT_EMAIL, WRITE_COMMUNICATIONS, WRITE_PROCUREMENT, WRITE_SALES
from app.core.entities import (
    Task,
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
from app.transactions.lifecycle import DERIVATIONS, KIND_WRITE_PERMISSION, KINDS, kind_label, manual_transitions, status_label

# Group order and labels of the "related objects" panel.
GROUPS: list[tuple[str, tuple[str, str]]] = [  # type, (French, English)
    ("customer", ("Clients", "Customers")),
    ("supplier", ("Fournisseurs", "Suppliers")),
    ("contact", ("Contacts", "Contacts")),
    ("product", ("Produits", "Products")),
    ("commercial_document", ("Documents commerciaux", "Commercial documents")),
    ("communication", ("Communications", "Communications")),
    ("document", ("Fichiers", "Files")),
    ("task", ("Tâches", "Tasks")),
    ("risk", ("Risques", "Risks")),
    ("opportunity", ("Opportunités", "Opportunities")),
    ("employee", ("Employés", "Employees")),
    ("candidate", ("Candidats", "Candidates")),
    ("transaction", ("Écritures", "Entries")),
]

EVENT_LABELS: dict[str, tuple[str, str]] = {  # (French, English)
    "DocumentCreated": ("Document créé", "Document created"),
    "DocumentStatusChanged": ("Changement de statut", "Status change"),
    "ObjectsLinked": ("Objet lié", "Object linked"),
    "EmailDrafted": ("Brouillon d'email préparé", "Email draft prepared"),
    "EmailSubmitted": ("Email soumis à validation", "Email submitted for approval"),
    "EmailSent": ("Email envoyé", "Email sent"),
    "StockUpdated": ("Stock mis à jour", "Stock updated"),
    "TaskCreated": ("Tâche créée", "Task created"),
    "RiskCreated": ("Risque détecté", "Risk detected"),
    "OpportunityCreated": ("Opportunité détectée", "Opportunity detected"),
    "ObservationDetected": ("Signal observé", "Signal observed"),
    "EventInterpreted": ("Signal interprété", "Signal interpreted"),
    "DecisionProposed": ("Décision proposée", "Decision proposed"),
    "ActionProposed": ("Action proposée", "Action proposed"),
    "ActionApproved": ("Action approuvée", "Action approved"),
    "ActionExecuted": ("Action exécutée", "Action executed"),
    "SupplierCostIncreased": ("Hausse de coût fournisseur", "Supplier cost increase"),
    "MarginDeteriorated": ("Dégradation de marge", "Margin deterioration"),
    "SupplierPerformanceDeteriorated": ("Dégradation des délais fournisseur", "Supplier delivery deterioration"),
    "CustomerGrowthDetected": ("Croissance client", "Customer growth"),
    "CustomerDeclineDetected": ("Baisse client", "Customer decline"),
    # V2.1
    "EmployeeCostChanged": ("Coût employé modifié", "Employee cost changed"),
    "EmployeeDecisionApplied": ("Décision RH appliquée", "HR decision applied"),
    "CandidateCreated": ("Fiche candidat créée", "Candidate record created"),
    "SkillGapDetected": ("Compétence manquante détectée", "Missing skill detected"),
    "CashForecastDeteriorated": ("Prévision de trésorerie dégradée", "Cash forecast deteriorated"),
    "SourcingOpportunityFound": ("Source moins chère possible", "Possible cheaper source"),
    "WebsiteAudited": ("Site analysé", "Website analysed"),
    "WebsiteChangeApproved": ("Modification du site approuvée", "Website change approved"),
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
            groups.append({"type": key, "label": tx(*label), "count": len(items), "items": items})
    return groups


def _status(obj_type: str, obj_id: uuid.UUID, session: Session, status: str | None) -> str | None:
    if obj_type != "commercial_document" or status is None:
        return status
    doc = session.get(CommercialDocument, obj_id)
    return status_label(doc.kind, status) if doc is not None else status


def _event_detail(session: Session, event_type: str, payload: dict) -> str | None:
    """The title an event carried when it happened (French, generated), in
    the active language: re-read from its row when it has one, re-rendered
    from the payload otherwise. A person's name stays as written."""

    from app.decision.engine import localize_decision
    from app.interpretation.engine import localize_interpretation

    if event_type == "EventInterpreted":
        return localize_interpretation(payload).get("title")
    if event_type == "DecisionProposed":
        return localize_decision(payload).get("problem")
    for key, model in (("opportunity_id", Opportunity), ("risk_id", Risk), ("task_id", Task)):
        if payload.get(key):
            row = session.get(model, uuid.UUID(payload[key]))
            if row is not None:
                return text_of(row, "title")
    if event_type == "CashForecastDeteriorated":
        return tx("Trésorerie projetée sous le seuil minimum", "Projected cash below the minimum threshold")
    if event_type == "WebsiteAudited":
        return tx(f"Audit du site ({payload.get('mode')})", f"Website audit ({payload.get('mode')})")
    if event_type == "WebsiteChangeApproved":
        return tx("Modification du site approuvée (application manuelle)", "Website change approved (applied manually)")
    if event_type == "SourcingOpportunityFound" and payload.get("lead"):
        return tx(f"Source moins chère possible : {payload['lead']}", f"Possible cheaper source: {payload['lead']}")
    return payload.get("title") or payload.get("problem")


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
            detail = f"{_status(obj_type, obj_id, session, payload.get('from'))} → {_status(obj_type, obj_id, session, payload.get('to'))}"
        elif row.event_type == "ObjectsLinked":
            detail = f"{payload.get('linked_type')} ({payload.get('relation')})"
        elif payload.get("title") or payload.get("problem"):
            detail = _event_detail(session, row.event_type, payload)
        label = EVENT_LABELS.get(row.event_type)
        entries.append(TimelineEntry(row.occurred_at, tx(*label) if label else row.event_type, row.event_type, detail))
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
                signals.append(asdict(summary) | {"via": via, "description": text_of(row, "description"), "severity": getattr(row, "severity", None) and row.severity.value})

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

_EMAIL_PURPOSES_BY_KIND: dict[DocumentKind, list[tuple[str, tuple[str, str]]]] = {
    DocumentKind.CUSTOMER_REQUEST: [("reply", ("Répondre au client", "Reply to the customer")), ("brochure", ("Envoyer une brochure", "Send a brochure")), ("nda", ("Proposer un NDA", "Offer an NDA"))],
    DocumentKind.CUSTOMER_QUOTE: [("send_quote", ("Envoyer le devis", "Send the quote")), ("follow_up", ("Préparer une relance", "Prepare a follow-up"))],
    DocumentKind.CUSTOMER_ORDER: [("order_confirmation", ("Confirmer la commande au client", "Confirm the order to the customer"))],
    DocumentKind.PURCHASE_REQUEST: [("rfq_price", ("Demander un prix", "Ask for a price")), ("rfq_availability", ("Demander la disponibilité", "Ask for availability")), ("rfq_lead_time", ("Demander un délai", "Ask for a lead time"))],
    DocumentKind.SUPPLIER_QUOTE: [("rfq_terms", ("Demander les conditions", "Ask for terms")), ("rfq_documents", ("Demander des documents", "Ask for documents")), ("follow_up", ("Relancer le fournisseur", "Follow up with the supplier"))],
    DocumentKind.PURCHASE_ORDER: [("send_purchase_order", ("Envoyer la commande au fournisseur", "Send the order to the supplier"))],
    DocumentKind.CUSTOMER_INVOICE: [("payment_reminder", ("Préparer une relance de paiement", "Prepare a payment reminder"))],
    DocumentKind.CUSTOMER_CREDIT_NOTE: [("credit_note_offer", ("Proposer l'avoir au client", "Offer the credit note to the customer"))],
    DocumentKind.RECEPTION: [("supplier_claim", ("Préparer une réclamation fournisseur", "Prepare a supplier claim"))],
    DocumentKind.SUPPLIER_CREDIT_NOTE: [("supplier_claim", ("Préparer la demande d'avoir", "Prepare the credit note request"))],
}


# Wording of status buttons that record something the OTHER party did:
# the user records it, the software does not claim it happened by itself.
_STATUS_ACTION_LABELS: dict[tuple[DocumentKind, str], tuple[str, str]] = {
    (DocumentKind.CUSTOMER_ORDER, "sent"): ("Marquer comme transmise au client", "Mark as sent to the customer"),
    (DocumentKind.CUSTOMER_ORDER, "acknowledged"): ("Enregistrer l'accusé de réception du client", "Record the customer's acknowledgement"),
    (DocumentKind.CUSTOMER_CREDIT_NOTE, "submitted"): ("Marquer comme soumis au client", "Mark as sent to the customer"),
    (DocumentKind.CUSTOMER_CREDIT_NOTE, "accepted"): ("Enregistrer l'acceptation du client", "Record the customer's acceptance"),
    (DocumentKind.CUSTOMER_CREDIT_NOTE, "rejected"): ("Enregistrer le refus du client", "Record the customer's refusal"),
    (DocumentKind.CUSTOMER_CREDIT_NOTE, "draft"): ("Le client demande une modification", "The customer asks for a change"),
    (DocumentKind.SUPPLIER_CREDIT_NOTE, "confirmed"): ("Enregistrer la confirmation du fournisseur", "Record the supplier's confirmation"),
    (DocumentKind.SUPPLIER_CREDIT_NOTE, "rejected"): ("Enregistrer le refus du fournisseur", "Record the supplier's refusal"),
}


def _document_actions(user: CurrentUser, doc: CommercialDocument) -> list[ActionItem]:
    actions: list[ActionItem] = []
    can_edit = user.can(KIND_WRITE_PERMISSION[doc.kind])
    no_right = None if can_edit else tx("Votre rôle ne permet pas de modifier ce document.", "Your role does not allow editing this document.")
    # System-only statuses (settlement, validation, imputation) are not
    # buttons: they follow the billing actions below (app.billing).
    for status in manual_transitions(doc.kind, doc.status):
        actions.append(ActionItem(f"status:{status}", tx(*_STATUS_ACTION_LABELS[(doc.kind, status)]) if (doc.kind, status) in _STATUS_ACTION_LABELS else tx(f"Passer à « {status_label(doc.kind, status)} »", f'Move to "{status_label(doc.kind, status)}"'), "status", can_edit, no_right, {"status": status}))
    for target in DERIVATIONS.get(doc.kind, ()):
        permitted = user.can(KIND_WRITE_PERMISSION[target])
        actions.append(
            ActionItem(
                f"derive:{target.value}", tx(f"Créer {KINDS[target].label.lower()}", f"Create {kind_label(target).lower()}"), "derive", permitted,
                None if permitted else tx("Votre rôle ne permet pas de créer ce document.", "Your role does not allow creating this document."),
                {"kind": target.value, "needs_supplier": target in {DocumentKind.SUPPLIER_QUOTE, DocumentKind.PURCHASE_ORDER} and doc.kind == DocumentKind.PURCHASE_REQUEST},
            )
        )  # fmt: skip
    can_draft = user.can(WRITE_COMMUNICATIONS)
    for purpose, label in _EMAIL_PURPOSES_BY_KIND.get(doc.kind, []):
        actions.append(ActionItem(f"email:{purpose}", tx(*label), "email", can_draft, None if can_draft else tx("Votre rôle ne permet pas de préparer des emails.", "Your role does not allow preparing emails."), {"purpose": purpose}))
    if doc.kind == DocumentKind.PURCHASE_REQUEST:
        actions.append(ActionItem("benchmark", tx("Comparer les fournisseurs", "Compare suppliers"), "navigate", True, None, {"anchor": "benchmark"}))
    # V2.2 billing actions live in their panels (anchors) -- the panel checks
    # the rule, the API checks the right (app.billing.router).
    can_finance = user.can(WRITE_FINANCE)
    if doc.kind in {DocumentKind.CUSTOMER_INVOICE, DocumentKind.SUPPLIER_INVOICE} and doc.status in {"issued", "approved", "partially_paid"}:
        actions.append(ActionItem("payment", tx("Enregistrer un règlement", "Record a payment"), "navigate", can_finance, None if can_finance else tx("Réservé à la finance.", "Finance only."), {"anchor": "reglements"}))
    if doc.kind in {DocumentKind.CUSTOMER_DELIVERY, DocumentKind.RECEPTION} and doc.status in {"delivered", "received"}:
        can_ops = user.can(WRITE_OPERATIONS)
        actions.append(ActionItem("nonconformity", tx("Signaler une non-conformité", "Report a non-conformity"), "navigate", can_ops, None if can_ops else tx("Réservé aux opérations.", "Operations only."), {"anchor": "suivi"}))
    if doc.kind in {DocumentKind.CUSTOMER_CREDIT_NOTE, DocumentKind.SUPPLIER_CREDIT_NOTE} and doc.status in {"accepted", "validated", "confirmed", "applied"}:
        actions.append(ActionItem("credit", tx("Suivre l'avoir", "Track the credit note"), "navigate", True, None, {"anchor": "avoir"}))
    return actions


def _entity_actions(user: CurrentUser, obj_type: str, obj) -> list[ActionItem]:
    actions: list[ActionItem] = []
    if obj_type == "customer":
        ok = user.can(WRITE_SALES)
        why = None if ok else tx("Réservé aux rôles commerciaux.", "Sales roles only.")
        actions += [
            ActionItem("create:customer_request", tx("Nouvelle demande client", "New customer request"), "create", ok, why, {"kind": "customer_request", "customer_id": str(obj.id)}),
            ActionItem("create:customer_quote", tx("Nouveau devis", "New quote"), "create", ok, why, {"kind": "customer_quote", "customer_id": str(obj.id)}),
        ]
    if obj_type == "supplier":
        ok = user.can(WRITE_PROCUREMENT)
        actions.append(ActionItem("create:purchase_request", tx("Nouvelle demande d'achat", "New purchase request"), "create", ok, None if ok else tx("Réservé aux achats.", "Procurement only."), {"kind": "purchase_request"}))
    if obj_type == "product":
        actions += [
            ActionItem("create:customer_quote", tx("Chiffrer pour un client", "Quote for a customer"), "create", user.can(WRITE_SALES), None if user.can(WRITE_SALES) else tx("Réservé aux rôles commerciaux.", "Sales roles only."), {"kind": "customer_quote", "product_id": str(obj.id)}),
            ActionItem("create:purchase_request", tx("Lancer une demande d'achat", "Start a purchase request"), "create", user.can(WRITE_PROCUREMENT), None if user.can(WRITE_PROCUREMENT) else tx("Réservé aux achats.", "Procurement only."), {"kind": "purchase_request", "product_id": str(obj.id)}),
            ActionItem("benchmark", tx("Comparer les fournisseurs", "Compare suppliers"), "navigate", True, None, {"anchor": "benchmark"}),
        ]
    if obj_type in {"customer", "supplier", "contact"}:
        ok = user.can(WRITE_COMMUNICATIONS)
        actions.append(ActionItem("email:reply", tx("Préparer un email", "Prepare an email"), "email", ok, None if ok else tx("Votre rôle ne permet pas de préparer des emails.", "Your role does not allow preparing emails."), {"purpose": "generic"}))
    if obj_type == "communication" and obj.status == "draft":
        ok = user.can(ACTION_SUBMIT_EMAIL)
        actions.append(ActionItem("submit", tx("Soumettre à validation", "Submit for approval"), "status", ok, None if ok else tx("Votre rôle ne permet pas de soumettre un email.", "Your role does not allow submitting an email.")))
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
